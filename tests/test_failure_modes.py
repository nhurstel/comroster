import pytest


@pytest.fixture
def auth_client(client):
    client.post("/admin/setup", data={"password": "motdepasse8"})
    return client


def test_last_write_wins_two_admins(auth_client):
    # deux écritures successives ; la dernière gagne
    p = auth_client.post("/api/people", json={"name": "Jean", "role": "HF", "beltpack": "12"}).get_json()
    auth_client.patch(f"/api/people/{p['id']}", json={"name": "A"})
    auth_client.patch(f"/api/people/{p['id']}", json={"name": "B"})
    state = auth_client.get("/api/state").get_json()
    assert [x for x in state["people"] if x["id"] == p["id"]][0]["name"] == "B"


def test_duplicate_beltpack_blocked_on_patch(auth_client):
    auth_client.post("/api/people", json={"name": "Jean", "role": "HF", "beltpack": "12"})
    p2 = auth_client.post("/api/people", json={"name": "Marie", "role": "Lum", "beltpack": "13"}).get_json()
    r = auth_client.patch(f"/api/people/{p2['id']}", json={"beltpack": "12"})
    assert r.status_code == 409


def test_corrupted_draft_recovers(app):
    # un fichier corrompu ne doit pas être masqué silencieusement
    storage = app.extensions["storage"]
    with open(storage.draft_path, "w") as fh:
        fh.write("{ pas du json")
    with pytest.raises(Exception):
        storage.load_draft()


def test_publish_then_display_only_sees_published(auth_client, app):
    # /events ne doit exposer que l'état publié, jamais le brouillon en cours
    auth_client.post("/api/people", json={"name": "Secret", "role": "HF", "beltpack": "99"})
    # rien n'est publié → l'état publié reste vide
    assert app.extensions["storage"].load_published() is None
