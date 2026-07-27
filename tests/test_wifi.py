"""Scan Wi-Fi : parseur pur (testable sans nmcli) + endpoint."""
import pytest

from comroster.services import wifi

# ---------- parse_scan (sortie terse nmcli) ----------

def test_parse_trie_par_signal_et_marque_securite():
    out = "\n".join([
        "72:WPA2:Régie-5G",
        "40::Public-Salle",        # sécurité vide → réseau ouvert
        "88:WPA1 WPA2:Intercom-AP",
    ])
    nets = wifi.parse_scan(out)
    assert [n["ssid"] for n in nets] == ["Intercom-AP", "Régie-5G", "Public-Salle"]
    assert nets[0]["secured"] is True
    assert nets[-1]["secured"] is False       # Public-Salle : ouvert


def test_parse_fusionne_doublons_garde_meilleur_signal():
    out = "45:WPA2:Loge\n78:WPA2:Loge\n30:WPA2:Loge"
    nets = wifi.parse_scan(out)
    assert len(nets) == 1
    assert nets[0]["signal"] == 78


def test_parse_ignore_ssid_masque_et_deséchappe_les_colonnes():
    out = "\n".join([
        "50:WPA2:",                # SSID vide (réseau masqué) → ignoré
        "60:WPA2:Salle\\:2",       # « : » échappé par nmcli
    ])
    nets = wifi.parse_scan(out)
    assert [n["ssid"] for n in nets] == ["Salle:2"]


def test_parse_assainit_les_caracteres_de_controle_et_borne_la_longueur():
    out = "50:WPA2:Bon\x07Réseau\n50:WPA2:" + "X" * 40   # SSID > 32 → rejeté
    nets = wifi.parse_scan(out)
    assert [n["ssid"] for n in nets] == ["BonRéseau"]


def test_parse_tolere_les_lignes_incompletes():
    assert wifi.parse_scan("garbage\n\n42:WPA2:OK") == [{"ssid": "OK", "signal": 42, "secured": True}]


def test_scan_sans_nmcli_ne_leve_pas(monkeypatch):
    def boom(*a, **k):
        raise FileNotFoundError("nmcli")
    monkeypatch.setattr(wifi.subprocess, "run", boom)
    assert wifi.scan() == {"available": False, "networks": []}


# ---------- endpoint ----------

@pytest.fixture
def auth_client(client):
    client.post("/admin/setup", data={"password": "motdepasse8"})
    return client


def test_wifi_scan_requiert_session(client):
    assert client.get("/api/network/wifi-scan").status_code in (302, 401, 403)


def test_wifi_scan_simule_en_dev(auth_client):
    res = auth_client.get("/api/network/wifi-scan").get_json()
    assert res["available"] is True and res["simulated"] is True
    assert any(n["ssid"] == "Intercom-AP" for n in res["networks"])
