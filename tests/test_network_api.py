import pytest


@pytest.fixture
def auth_client(client):
    client.post("/admin/setup", data={"password": "motdepasse8"})
    return client


def test_network_requires_auth(client):
    assert client.get("/api/network").status_code in (302, 401, 403)


def test_network_default(auth_client):
    assert auth_client.get("/api/network").get_json() == {"mode": "link-local", "link": "ethernet"}


def test_network_set_static(auth_client):
    r = auth_client.put("/api/network", json={"mode": "static", "address": "192.168.1.50", "prefix": 24})
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True and body["reboot_required"] is True
    assert auth_client.get("/api/network").get_json()["address"] == "192.168.1.50"


def test_network_rejects_invalid(auth_client):
    r = auth_client.put("/api/network", json={"mode": "static", "address": "999.0.0.1", "prefix": 24})
    assert r.status_code == 400 and "error" in r.get_json()


# --- Wi-Fi (design 2026-07-06) : le psk est write-only côté API ---

def test_network_set_wifi_and_psk_never_returned(auth_client):
    r = auth_client.put("/api/network", json={
        "link": "wifi", "mode": "static", "address": "192.168.42.10", "prefix": 24,
        "wifi": {"ssid": "REGIE-INTERCOM", "psk": "supermotdepasse"}})
    assert r.status_code == 200
    body = r.get_json()
    assert "psk" not in body["config"]["wifi"]           # clé psk absente (psk_set seulement)
    assert "supermotdepasse" not in str(body)            # le secret ne fuit nulle part
    got = auth_client.get("/api/network").get_json()
    assert got["link"] == "wifi"
    assert got["wifi"]["ssid"] == "REGIE-INTERCOM"
    assert got["wifi"]["psk_set"] is True
    assert "psk" not in got["wifi"]

def test_network_update_wifi_ip_without_retyping_psk(app, auth_client):
    auth_client.put("/api/network", json={
        "link": "wifi", "mode": "dhcp",
        "wifi": {"ssid": "REGIE", "psk": "supermotdepasse"}})
    r = auth_client.put("/api/network", json={
        "link": "wifi", "mode": "static", "address": "192.168.42.10", "prefix": 24,
        "wifi": {"ssid": "REGIE"}})                # pas de psk : on garde l'existant
    assert r.status_code == 200
    assert app.extensions["netconfig"].load()["wifi"]["psk"] == "supermotdepasse"

def test_network_wifi_short_psk_rejected(auth_client):
    r = auth_client.put("/api/network", json={
        "link": "wifi", "mode": "dhcp", "wifi": {"ssid": "REGIE", "psk": "court"}})
    assert r.status_code == 400
