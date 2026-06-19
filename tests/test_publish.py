import pytest


@pytest.fixture
def auth_client(client):
    client.post("/admin/setup", data={"password": "motdepasse8"})
    return client


def test_publish_copies_draft_to_published(auth_client, app):
    auth_client.post("/api/people", json={"name": "Jean", "role": "HF", "beltpack": "12"})
    r = auth_client.post("/api/publish")
    assert r.status_code == 200
    published = app.extensions["storage"].load_published()
    assert any(p["name"] == "Jean" for p in published["people"])


def test_publish_invalid_draft_409(auth_client, app):
    bad = {"version": 1, "updated_at": "x", "groups": [], "beltpack_roles": {},
           "people": [{"id": "1", "name": "A", "role": "", "beltpack": "1", "group_id": "ghost"}]}
    app.extensions["storage"].save_draft(bad)
    r = auth_client.post("/api/publish")
    assert r.status_code == 409


def test_publish_archives_history(auth_client, app):
    auth_client.post("/api/publish")
    assert len(app.extensions["history"].list()) >= 1


def test_publish_notifies_sse_subscriber(auth_client, app):
    broker = app.extensions["broker"]
    q = broker.subscribe()
    auth_client.post("/api/people", json={"name": "Jean", "role": "HF", "beltpack": "12"})
    auth_client.post("/api/publish")
    event, data = q.get_nowait()
    assert event == "published"
    assert any(p["name"] == "Jean" for p in data["people"])


def test_events_endpoint_sends_snapshot(client):
    # Flux infini : on ne lit QUE le premier chunk, sans bufferiser toute la réponse.
    resp = client.get("/events")
    assert resp.status_code == 200
    assert resp.mimetype == "text/event-stream"
    chunk = next(iter(resp.response))
    if isinstance(chunk, bytes):
        chunk = chunk.decode()
    assert "retry: 3000" in chunk
    resp.close()


def test_restore_history(auth_client, app):
    auth_client.post("/api/people", json={"name": "Jean", "role": "HF", "beltpack": "12"})
    auth_client.post("/api/publish")
    ts = app.extensions["history"].list()[0]["timestamp"]
    r = auth_client.post(f"/api/history/{ts}/restore")
    assert r.status_code == 200
