import json
import os
import socket
import urllib.error
import pytest
from comroster.services.antenna import AntennaClient, AntennaError, _battery_percent


def test_battery_percent():
    assert _battery_percent({"currentCharge": 2400, "maxCharge": 4800}) == 50
    assert _battery_percent({"currentCharge": 4800, "maxCharge": 4800}) == 100
    assert _battery_percent({}) is None                       # données absentes
    assert _battery_percent({"currentCharge": 100, "maxCharge": 0}) is None


def _fake_ok(method, path, body=None, timeout=5):
    # Calqué sur la vraie antenne : nodeStatus[].bp[].id = beltpacks connectés (ici id 1),
    # /rest/bp = config (id ↔ bpNumber/bpName, sans état de connexion).
    if path == "/rest/nodeStatus":
        return True, {"nodeStatus": [
            {"isLocal": True, "ip": "192.168.1.11", "bp": [   # id 1 connecté
                {"id": 1, "signalLevel": 0,
                 "battery": {"currentCharge": 3120, "maxCharge": 4800, "usbPower": 0}},
            ]},
            {"isLocal": False, "bp": []},
        ]}
    if path == "/rest/firmware":
        return True, {"firmware": {"version": "3.4.1-15"}}
    if path == "/rest/bp":
        return True, {"bp": [
            {"registered": True, "id": 1, "bpConfig": {"bpNumber": 5, "bpName": "Régie Son"}},
            {"registered": True, "id": 2, "bpConfig": {"bpNumber": 7, "bpName": "Lumière"}},
            {"registered": False, "id": 3, "bpConfig": {"bpNumber": 9, "bpName": "x"}},
        ]}
    return False, {"error": "unexpected"}


def test_connect_persists_encrypted(tmp_path, monkeypatch):
    c = AntennaClient(str(tmp_path), "secret-key")
    monkeypatch.setattr(c, "_request", _fake_ok)
    info = c.connect("192.168.1.11", "motdepasse")
    assert c.connected is True and c.ip == "192.168.1.11"
    assert info["firmware"]["version"] == "3.4.1-15"
    with open(os.path.join(str(tmp_path), "antenna.json")) as fh:
        raw = fh.read()
    assert "motdepasse" not in raw                  # mot de passe chiffré
    assert json.loads(raw)["ip"] == "192.168.1.11"


def test_live_status_all_offline_when_none_connected(tmp_path, monkeypatch):
    # Régression : si nodeStatus ne liste aucun bp connecté, tout doit être hors ligne
    # (et non « tout en ligne » comme l'ancien bug, ni l'inverse).
    def fake(method, path, body=None, timeout=5):
        if path == "/rest/nodeStatus":
            return True, {"nodeStatus": [{"isLocal": True, "bp": []}]}
        return _fake_ok(method, path, body, timeout)
    c = AntennaClient(str(tmp_path), "secret-key")
    monkeypatch.setattr(c, "_request", _fake_ok)
    c.connect("192.168.1.11", "")
    monkeypatch.setattr(c, "_request", fake)
    assert c.live_status() == {"connected": True, "beltpacks": {
        "5": {"online": False}, "7": {"online": False},
    }}


def test_status_never_leaks_password(tmp_path, monkeypatch):
    c = AntennaClient(str(tmp_path), "secret-key")
    monkeypatch.setattr(c, "_request", _fake_ok)
    c.connect("192.168.1.11", "motdepasse")
    st = c.status()
    assert "password" not in json.dumps(st) and "motdepasse" not in json.dumps(st)


def test_connect_failure_writes_nothing(tmp_path, monkeypatch):
    c = AntennaClient(str(tmp_path), "secret-key")
    monkeypatch.setattr(c, "_request", lambda *a, **k: (False, {"error": "timeout"}))
    with pytest.raises(AntennaError):
        c.connect("10.0.0.9", "x")
    assert not os.path.exists(os.path.join(str(tmp_path), "antenna.json"))
    assert c.connected is False


def test_persisted_creds_reloaded(tmp_path, monkeypatch):
    c = AntennaClient(str(tmp_path), "secret-key")
    monkeypatch.setattr(c, "_request", _fake_ok)
    c.connect("192.168.1.11", "motdepasse")
    c2 = AntennaClient(str(tmp_path), "secret-key")
    c2.load_persisted()
    assert c2.ip == "192.168.1.11"
    monkeypatch.setattr(c2, "_request", _fake_ok)
    assert len(c2.fetch_beltpacks()) == 2          # prouve que le mdp déchiffré marche


def test_wrong_key_ignores_creds(tmp_path, monkeypatch):
    c = AntennaClient(str(tmp_path), "secret-key")
    monkeypatch.setattr(c, "_request", _fake_ok)
    c.connect("192.168.1.11", "motdepasse")
    other = AntennaClient(str(tmp_path), "AUTRE-CLE")
    other.load_persisted()
    assert other.ip is None                         # creds illisibles → ignorés


def test_live_status_not_connected(tmp_path):
    c = AntennaClient(str(tmp_path), "secret-key")
    assert c.live_status() == {"connected": False, "beltpacks": {}}


def test_live_status_returns_online_map(tmp_path, monkeypatch):
    c = AntennaClient(str(tmp_path), "secret-key")
    monkeypatch.setattr(c, "_request", _fake_ok)
    c.connect("192.168.1.11", "")
    assert c.live_status() == {"connected": True, "beltpacks": {
        # raw_signal = signalLevel BRUT de l'antenne (pour le calibrage des barres)
        "5": {"online": True, "battery": 65, "charging": False},
        "7": {"online": False},
    }}


def test_live_status_caches_within_ttl(tmp_path, monkeypatch):
    c = AntennaClient(str(tmp_path), "secret-key")
    monkeypatch.setattr(c, "_request", _fake_ok)
    c.connect("192.168.1.11", "")
    n = []
    orig = c._beltpack_config
    monkeypatch.setattr(c, "_beltpack_config", lambda: (n.append(1), orig())[1])
    a = c.live_status(ttl=60)
    b = c.live_status(ttl=60)
    assert a == b and len(n) == 1            # 2e appel servi par le cache


def test_live_status_disconnect_clears_cache(tmp_path, monkeypatch):
    c = AntennaClient(str(tmp_path), "secret-key")
    monkeypatch.setattr(c, "_request", _fake_ok)
    c.connect("192.168.1.11", "")
    c.live_status(ttl=60)
    c.disconnect()
    assert c.live_status() == {"connected": False, "beltpacks": {}}


def _client_with_ip(tmp_path):
    c = AntennaClient(str(tmp_path), "secret-key")
    c._ip = "10.0.0.5"
    return c


def test_timeout_configurable_via_env(tmp_path, monkeypatch):
    monkeypatch.setenv("COMROSTER_ANTENNA_TIMEOUT", "9")
    c = AntennaClient(str(tmp_path), "secret-key")
    assert c.timeout == 9


def test_timeout_default_when_no_env(tmp_path, monkeypatch):
    monkeypatch.delenv("COMROSTER_ANTENNA_TIMEOUT", raising=False)
    c = AntennaClient(str(tmp_path), "secret-key")
    assert c.timeout == 5


def test_request_uses_instance_timeout(tmp_path, monkeypatch):
    monkeypatch.setenv("COMROSTER_ANTENNA_TIMEOUT", "9")
    c = _client_with_ip(tmp_path)
    seen = {}

    def fake_urlopen(req, timeout=None):
        seen["timeout"] = timeout
        raise urllib.error.URLError(ConnectionRefusedError("refused"))
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    c._request("GET", "/rest/bp")
    assert seen["timeout"] == 9


def test_request_auth_error_on_401(tmp_path, monkeypatch):
    c = _client_with_ip(tmp_path)

    def boom(req, timeout=5):
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, None)
    monkeypatch.setattr("urllib.request.urlopen", boom)
    ok, data = c._request("GET", "/rest/nodeStatus")
    assert ok is False and data["code"] == "auth"
    assert "mot de passe" in data["error"].lower()


def test_request_auth_error_on_403(tmp_path, monkeypatch):
    c = _client_with_ip(tmp_path)

    def boom(req, timeout=5):
        raise urllib.error.HTTPError(req.full_url, 403, "Forbidden", {}, None)
    monkeypatch.setattr("urllib.request.urlopen", boom)
    ok, data = c._request("GET", "/rest/nodeStatus")
    assert ok is False and data["code"] == "auth"


def test_request_other_http_error(tmp_path, monkeypatch):
    c = _client_with_ip(tmp_path)

    def boom(req, timeout=5):
        raise urllib.error.HTTPError(req.full_url, 500, "Server Error", {}, None)
    monkeypatch.setattr("urllib.request.urlopen", boom)
    ok, data = c._request("GET", "/rest/nodeStatus")
    assert ok is False and data["code"] == "http" and "500" in data["error"]


def test_request_timeout(tmp_path, monkeypatch):
    c = _client_with_ip(tmp_path)

    def boom(req, timeout=5):
        raise urllib.error.URLError(socket.timeout("timed out"))
    monkeypatch.setattr("urllib.request.urlopen", boom)
    ok, data = c._request("GET", "/rest/nodeStatus")
    assert ok is False and data["code"] == "timeout"


def test_request_bare_timeout(tmp_path, monkeypatch):
    c = _client_with_ip(tmp_path)

    def boom(req, timeout=5):
        raise TimeoutError("timed out")
    monkeypatch.setattr("urllib.request.urlopen", boom)
    ok, data = c._request("GET", "/rest/nodeStatus")
    assert ok is False and data["code"] == "timeout"


def test_request_network_error(tmp_path, monkeypatch):
    c = _client_with_ip(tmp_path)

    def boom(req, timeout=5):
        raise urllib.error.URLError(ConnectionRefusedError("refused"))
    monkeypatch.setattr("urllib.request.urlopen", boom)
    ok, data = c._request("GET", "/rest/nodeStatus")
    assert ok is False and data["code"] == "network"
    assert "réseau" in data["error"].lower() or "ip" in data["error"].lower()


def test_fetch_beltpacks_parses_registered_only(tmp_path, monkeypatch):
    c = AntennaClient(str(tmp_path), "secret-key")
    monkeypatch.setattr(c, "_request", _fake_ok)
    c.connect("192.168.1.11", "")
    bps = c.fetch_beltpacks()
    assert bps == [
        {"number": "5", "name": "Régie Son"},
        {"number": "7", "name": "Lumière"},
    ]
