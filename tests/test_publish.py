import pytest


def _drain(q, event=None):
    """Vide la file en écartant les annonces d'INTENDANCE du broker (`displays`).

    Depuis l'audit 2026-07-28, s'abonner/se désabonner pousse le nombre d'écrans à tout le
    monde : ces tests ne peuvent donc plus supposer « le premier évènement de la file est
    le mien ». On saute donc l'intendance — et, si `event` est donné, on va chercher CE
    type-là plutôt que le premier venu.
    """
    import queue as _q
    while True:
        try:
            item = q.get_nowait()
        except _q.Empty:
            return None
        if item[0] == "displays":
            continue
        if event is None or item[0] == event:
            return item


def _is_empty(q):
    """La file ne contient plus que de l'intendance ?"""
    return _drain(q) is None


@pytest.fixture
def auth_client(client):
    client.post("/admin/setup", data={"password": "motdepasse8"})
    return client


def test_publish_copies_draft_to_published(auth_client, app):
    auth_client.post("/api/people", json={"role": "HF", "beltpack": "12"})
    r = auth_client.post("/api/publish")
    assert r.status_code == 200
    published = app.extensions["storage"].load_published()
    assert any(p["beltpack"] == "12" for p in published["people"])


def test_publish_invalid_draft_409(auth_client, app):
    bad = {"version": 1, "updated_at": "x", "groups": [], "beltpack_roles": {},
           "people": [{"id": "1", "role": "", "beltpack": "1", "group_id": "ghost"}]}
    app.extensions["storage"].save_draft(bad)
    r = auth_client.post("/api/publish")
    assert r.status_code == 409


def test_publish_archives_history(auth_client, app):
    auth_client.post("/api/publish")
    assert len(app.extensions["history"].list()) >= 1


def test_publish_notifies_sse_subscriber(auth_client, app):
    broker = app.extensions["broker"]
    q = broker.subscribe()
    auth_client.post("/api/people", json={"role": "HF", "beltpack": "12"})
    auth_client.post("/api/publish")
    event, data = _drain(q)
    assert event == "published"
    assert any(p["beltpack"] == "12" for p in data["people"])


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
    auth_client.post("/api/people", json={"role": "HF", "beltpack": "12"})
    auth_client.post("/api/publish")
    ts = app.extensions["history"].list()[0]["timestamp"]
    r = auth_client.post(f"/api/history/{ts}/restore")
    assert r.status_code == 200


def test_events_rejects_when_at_capacity(app, client):
    # Protection du pool de threads : au-delà du cap, /events répond 503 (le client
    # display retentera 4 s plus tard) au lieu de bloquer tout le serveur.
    broker = app.extensions["broker"]
    cap = app.config["SSE_MAX_CLIENTS"]
    queues = [broker.subscribe() for _ in range(cap)]
    try:
        resp = client.get("/events")
        assert resp.status_code == 503
        assert resp.headers.get("Retry-After")
    finally:
        for q in queues:
            broker.unsubscribe(q)
    # Une fois une place libérée, le flux repasse
    resp2 = client.get("/events")
    assert resp2.status_code == 200
    resp2.close()


def test_status_reports_displays_and_published(auth_client, app):
    """La barre d'état de l'admin lit /api/status : afficheurs abonnés + résumé publié."""
    # Rien de publié au départ.
    r = auth_client.get("/api/status")
    assert r.status_code == 200
    body = r.get_json()
    assert body["published"] is None
    assert body["displays"] == 0

    # Un abonné SSE (écran de régie) est compté ; la publication remplit le résumé.
    q = app.extensions["broker"].subscribe()
    auth_client.post("/api/people", json={"role": "HF", "beltpack": "12"})
    auth_client.post("/api/publish")
    body = auth_client.get("/api/status").get_json()
    assert body["displays"] == 1
    assert body["published"]["people"] == 1
    assert body["published"]["updated_at"]
    del q


def test_status_requires_auth(client):
    assert client.get("/api/status").status_code in (302, 401, 403)
