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


def test_settings_has_only_ranges(auth_client):
    assert auth_client.get("/api/settings").get_json() == {"antenna_ranges": []}


def test_antenna_status_ok_without_config(auth_client):
    # plus de garde 409 : status répond 200 même rien configuré
    r = auth_client.get("/api/antenna/status")
    assert r.status_code == 200 and r.get_json()["connected"] is False


def test_enable_connect_import_flow(auth_client, app, monkeypatch):
    monkeypatch.setattr(app.extensions["antenna"], "_request", _fake_ok)

    r = auth_client.post("/api/antenna/connect", json={"ip": "192.168.1.11", "password": "pw"})
    assert r.status_code == 200 and r.get_json()["connected"] is True

    preview = auth_client.post("/api/antenna/import/preview").get_json()
    assert len(preview["new"]) == 2 and preview["unchanged"] == 0

    applied = auth_client.post("/api/antenna/import/apply").get_json()
    assert applied == {"created": 2, "updated": 0, "removed": 0}

    state = auth_client.get("/api/state").get_json()
    assert sorted(p["beltpack"] for p in state["people"]) == ["5", "7"]


def test_connect_failure_502(auth_client, app, monkeypatch):
    monkeypatch.setattr(app.extensions["antenna"], "_request", lambda *a, **k: (False, {"error": "timeout"}))
    r = auth_client.post("/api/antenna/connect", json={"ip": "10.0.0.9", "password": "x"})
    assert r.status_code == 502


def _fake_three(method, path, body=None, timeout=5):
    if path == "/rest/nodeStatus":
        return True, {"nodeStatus": [{"nodeId": 1, "isLocal": True}]}
    if path == "/rest/firmware":
        return True, {"firmware": {"version": "3.4.1-15"}}
    if path == "/rest/bp":
        return True, {"bp": [
            {"registered": True, "id": 1, "connectedNodeId": 1, "bpConfig": {"bpNumber": 5, "bpName": "Régie"}},
            {"registered": True, "id": 2, "connectedNodeId": 0, "bpConfig": {"bpNumber": 7, "bpName": "Lumière"}},
            {"registered": True, "id": 3, "connectedNodeId": 0, "bpConfig": {"bpNumber": 52, "bpName": "HF B"}},
        ]}
    return False, {"error": "x"}


def test_ranges_filter_import(auth_client, app, monkeypatch):
    auth_client.put("/api/settings", json={"antenna_ranges": [[1, 25]]})
    monkeypatch.setattr(app.extensions["antenna"], "_request", _fake_three)
    auth_client.post("/api/antenna/connect", json={"ip": "1.1.1.1", "password": ""})
    applied = auth_client.post("/api/antenna/import/apply").get_json()
    assert applied["created"] == 2          # 5 et 7 ; 52 hors plage
    state = auth_client.get("/api/state").get_json()
    assert sorted(p["beltpack"] for p in state["people"]) == ["5", "7"]


def test_invalid_ranges_400(auth_client):
    r = auth_client.put("/api/settings", json={"antenna_ranges": [[25, 1]]})  # lo>hi
    assert r.status_code == 400


def test_apply_mirror_removes_absent(auth_client, app, monkeypatch):
    monkeypatch.setattr(app.extensions["antenna"], "_request", _fake_three)
    auth_client.post("/api/antenna/connect", json={"ip": "1.1.1.1", "password": ""})
    auth_client.post("/api/antenna/import/apply")

    def only5(method, path, body=None, timeout=5):
        if path == "/rest/bp":
            return True, {"bp": [{"registered": True, "id": 1, "connectedNodeId": 1, "bpConfig": {"bpNumber": 5, "bpName": "Régie"}}]}
        return _fake_three(method, path, body, timeout)
    monkeypatch.setattr(app.extensions["antenna"], "_request", only5)
    res = auth_client.post("/api/antenna/import/apply").get_json()
    assert res["removed"] == 2
    state = auth_client.get("/api/state").get_json()
    assert [p["beltpack"] for p in state["people"]] == ["5"]


def test_configs_save_load_disconnects(auth_client, app, monkeypatch):
    monkeypatch.setattr(app.extensions["antenna"], "_request", _fake_three)
    auth_client.post("/api/antenna/connect", json={"ip": "1.1.1.1", "password": ""})
    auth_client.post("/api/antenna/import/apply")
    auth_client.post("/api/configs", json={"name": "Base"})
    assert [c["name"] for c in auth_client.get("/api/configs").get_json()] == ["Base"]
    r = auth_client.post("/api/configs/Base/load")
    assert r.status_code == 200
    assert app.extensions["antenna"].connected is False
