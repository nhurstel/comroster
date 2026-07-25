"""État réseau courant : parseurs terse nmcli (sans matériel) + endpoint."""
import pytest

from comroster.services import netstatus


def test_parse_device_status_garde_les_liens_geres_connectes():
    out = "\n".join([
        "lo:loopback:unmanaged:",
        "eth0:ethernet:connected:Wired connection 1",
        "wlan0:wifi:connected:comroster-wifi",
        "wlan1:wifi:disconnected:",
    ])
    links = netstatus.parse_device_status(out)
    assert [(x["device"], x["type"]) for x in links] == [("eth0", "ethernet"), ("wlan0", "wifi")]


def test_parse_ip4_prend_la_premiere_sans_prefixe():
    out = "IP4.ADDRESS[1]:192.168.1.42/24\nIP4.ADDRESS[2]:10.0.0.9/8\nIP4.GATEWAY:192.168.1.1"
    assert netstatus.parse_ip4(out) == "192.168.1.42"


def test_parse_ip4_absente():
    assert netstatus.parse_ip4("IP4.GATEWAY:--") is None


def test_parse_active_ssid():
    out = "no:AutreReseau\nyes:Intercom-AP\nno:Voisin"
    assert netstatus.parse_active_ssid(out) == "Intercom-AP"
    assert netstatus.parse_active_ssid("no:X\nno:Y") is None


def test_current_sans_nmcli_ne_leve_pas(monkeypatch):
    def boom(*a, **k):
        raise FileNotFoundError("nmcli")
    monkeypatch.setattr(netstatus.subprocess, "run", boom)
    assert netstatus.current() == {"available": False, "links": []}


@pytest.fixture
def auth_client(client):
    client.post("/admin/setup", data={"password": "motdepasse8"})
    return client


def test_network_status_requiert_session(client):
    assert client.get("/api/network/status").status_code in (302, 401, 403)


def test_network_status_simule_en_dev(auth_client):
    res = auth_client.get("/api/network/status").get_json()
    assert res["available"] is True and res["simulated"] is True
    wifi = next(x for x in res["links"] if x["type"] == "wifi")
    assert wifi["ssid"] == "Intercom-AP" and wifi["ip"] == "192.168.1.42"
