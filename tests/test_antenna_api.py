import pytest


def _fake_ok(method, path, body=None, timeout=5):
    if path == "/rest/nodeStatus":
        return True, {"nodeStatus": [{"nodeId": 1, "isLocal": True}]}
    if path == "/rest/firmware":
        return True, {"firmware": {"version": "3.4.1-15"}}
    if path == "/rest/bp":
        return True, {"bp": [
            {"registered": True, "id": 1, "connectedNodeId": 1,
             "bpConfig": {"bpNumber": 5, "bpName": "Régie Son"}},
            {"registered": True, "id": 2, "connectedNodeId": 0,
             "bpConfig": {"bpNumber": 7, "bpName": "Lumière"}},
        ]}
    return False, {"error": "unexpected"}


@pytest.fixture
def auth_client(client):
    client.post("/admin/setup", data={"password": "motdepasse8"})
    return client


def test_disabled_by_default_returns_409(auth_client):
    assert auth_client.get("/api/settings").get_json() == {"bolero_enabled": False}
    assert auth_client.get("/api/antenna/status").status_code == 409
    assert auth_client.post("/api/antenna/connect", json={"ip": "x", "password": "y"}).status_code == 409


def test_enable_connect_import_flow(auth_client, app, monkeypatch):
    auth_client.put("/api/settings", json={"bolero_enabled": True})
    monkeypatch.setattr(app.extensions["antenna"], "_request", _fake_ok)

    r = auth_client.post("/api/antenna/connect", json={"ip": "192.168.1.11", "password": "pw"})
    assert r.status_code == 200 and r.get_json()["connected"] is True

    preview = auth_client.post("/api/antenna/import/preview").get_json()
    assert len(preview["new"]) == 2 and preview["unchanged"] == 0

    applied = auth_client.post("/api/antenna/import/apply").get_json()
    assert applied == {"created": 2, "updated": 0}

    state = auth_client.get("/api/state").get_json()
    assert sorted(p["beltpack"] for p in state["people"]) == ["5", "7"]


def test_connect_failure_502(auth_client, app, monkeypatch):
    auth_client.put("/api/settings", json={"bolero_enabled": True})
    monkeypatch.setattr(app.extensions["antenna"], "_request", lambda *a, **k: (False, {"error": "timeout"}))
    r = auth_client.post("/api/antenna/connect", json={"ip": "10.0.0.9", "password": "x"})
    assert r.status_code == 502


def test_disable_disconnects(auth_client, app, monkeypatch):
    auth_client.put("/api/settings", json={"bolero_enabled": True})
    monkeypatch.setattr(app.extensions["antenna"], "_request", _fake_ok)
    auth_client.post("/api/antenna/connect", json={"ip": "192.168.1.11", "password": "pw"})
    auth_client.put("/api/settings", json={"bolero_enabled": False})
    assert app.extensions["antenna"].connected is False
