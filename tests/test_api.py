import pytest


@pytest.fixture
def auth_client(client):
    client.post("/admin/setup", data={"password": "motdepasse8"})
    return client


def test_crud_group(auth_client):
    r = auth_client.post("/api/groups", json={"name": "Plateau", "color": "#00A8E8"})
    assert r.status_code == 200
    gid = r.get_json()["id"]
    r2 = auth_client.patch(f"/api/groups/{gid}", json={"name": "Plateau 2"})
    assert r2.get_json()["name"] == "Plateau 2"
    r3 = auth_client.delete(f"/api/groups/{gid}")
    assert r3.status_code == 200


def test_create_person(auth_client):
    r = auth_client.post("/api/people", json={"name": "Jean", "role": "HF", "beltpack": "12"})
    assert r.status_code == 200
    assert r.get_json()["beltpack"] == "12"


def test_duplicate_beltpack_409(auth_client):
    auth_client.post("/api/people", json={"name": "Jean", "role": "HF", "beltpack": "12"})
    r = auth_client.post("/api/people", json={"name": "Marie", "role": "Lum", "beltpack": "12"})
    assert r.status_code == 409


def test_delete_group_moves_people_to_pool(auth_client):
    g = auth_client.post("/api/groups", json={"name": "P", "color": "#fff"}).get_json()
    p = auth_client.post("/api/people", json={"name": "Jean", "role": "HF", "beltpack": "12", "group_id": g["id"]}).get_json()
    auth_client.delete(f"/api/groups/{g['id']}")
    state = auth_client.get("/api/state").get_json()
    person = [x for x in state["people"] if x["id"] == p["id"]][0]
    assert person["group_id"] is None


def test_patch_person_group_assignment(auth_client):
    g = auth_client.post("/api/groups", json={"name": "P", "color": "#fff"}).get_json()
    p = auth_client.post("/api/people", json={"name": "Jean", "role": "HF", "beltpack": "12"}).get_json()
    r = auth_client.patch(f"/api/people/{p['id']}", json={"group_id": g["id"]})
    assert r.get_json()["group_id"] == g["id"]


def test_404_unknown_person(auth_client):
    r = auth_client.patch("/api/people/ghost", json={"name": "X"})
    assert r.status_code == 404


def test_role_inherited_from_beltpack_via_api(auth_client):
    # Jean définit BP5=Régie ; après son départ, Marie sur BP5 hérite "Régie"
    p = auth_client.post("/api/people", json={"name": "Jean", "role": "Régie", "beltpack": "5"}).get_json()
    auth_client.delete(f"/api/people/{p['id']}")
    marie = auth_client.post("/api/people", json={"name": "Marie", "beltpack": "5"}).get_json()
    assert marie["role"] == "Régie"


def test_export_import_roundtrip(auth_client):
    auth_client.post("/api/people", json={"name": "Jean", "role": "HF", "beltpack": "12"})
    exported = auth_client.get("/api/export").get_json()
    auth_client.post("/api/import", json=exported)
    state = auth_client.get("/api/state").get_json()
    assert any(p["name"] == "Jean" for p in state["people"])


def test_import_invalid_400(auth_client):
    r = auth_client.post("/api/import", json={"people": [{"id": "1", "name": "A", "role": "", "beltpack": "1", "group_id": "ghost"}], "groups": [], "version": 1})
    assert r.status_code == 400
