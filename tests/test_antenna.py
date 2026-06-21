import json
import os
import pytest
from comroster.services.antenna import AntennaClient, AntennaError


def _fake_ok(method, path, body=None, timeout=5):
    if path == "/rest/nodeStatus":
        return True, {"nodeStatus": [{"nodeId": 1, "isLocal": True, "ip": "192.168.1.11"}]}
    if path == "/rest/firmware":
        return True, {"firmware": {"version": "3.4.1-15"}}
    if path == "/rest/bp":
        return True, {"bp": [
            {"registered": True, "id": 1, "connectedNodeId": 1,
             "bpConfig": {"bpNumber": 5, "bpName": "Régie Son"}},
            {"registered": True, "id": 2, "connectedNodeId": 0,
             "bpConfig": {"bpNumber": 7, "bpName": "Lumière"}},
            {"registered": False, "id": 3, "bpConfig": {"bpNumber": 9, "bpName": "x"}},
        ]}
    return False, {"error": "unexpected"}


def test_connect_persists_encrypted(tmp_path, monkeypatch):
    c = AntennaClient(str(tmp_path), "secret-key")
    monkeypatch.setattr(c, "_request", _fake_ok)
    info = c.connect("192.168.1.11", "motdepasse")
    assert c.connected is True and c.ip == "192.168.1.11"
    assert info["firmware"]["version"] == "3.4.1-15"
    raw = open(os.path.join(str(tmp_path), "antenna.json")).read()
    assert "motdepasse" not in raw                  # mot de passe chiffré
    assert json.loads(raw)["ip"] == "192.168.1.11"


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


def test_fetch_beltpacks_parses_registered_only(tmp_path, monkeypatch):
    c = AntennaClient(str(tmp_path), "secret-key")
    monkeypatch.setattr(c, "_request", _fake_ok)
    c.connect("192.168.1.11", "")
    bps = c.fetch_beltpacks()
    assert bps == [
        {"number": "5", "name": "Régie Son", "online": True},
        {"number": "7", "name": "Lumière", "online": False},
    ]
