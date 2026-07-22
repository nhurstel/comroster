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


def test_delete_batch_rejects_non_list(auth_client):
    # ids non-liste (string) : 400 propre, pas une itération caractère par caractère.
    r = auth_client.post("/api/people/delete-batch", json={"ids": "abc"})
    assert r.status_code == 400


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
    assert any(p["beltpack"] == "12" for p in state["people"])


def test_patch_person_ignores_unknown_keys(auth_client):
    # un payload avec des clés parasites (state/person_id) ne doit pas faire un 500
    p = auth_client.post("/api/people", json={"role": "A", "beltpack": "5"}).get_json()
    r = auth_client.patch(f"/api/people/{p['id']}", json={"role": "B", "state": "x", "person_id": "y"})
    assert r.status_code == 200 and r.get_json()["role"] == "B"


def test_patch_group_ignores_unknown_keys(auth_client):
    g = auth_client.post("/api/groups", json={"name": "G", "color": "#111111"}).get_json()
    r = auth_client.patch(f"/api/groups/{g['id']}", json={"name": "G2", "state": "x", "group_id": "z"})
    assert r.status_code == 200 and r.get_json()["name"] == "G2"


def test_history_restore_invalid_ts_404(auth_client):
    assert auth_client.post("/api/history/pas-un-timestamp/restore").status_code == 404


def test_delete_batch(auth_client):
    a = auth_client.post("/api/people", json={"name": "A", "role": "", "beltpack": "1"}).get_json()
    b = auth_client.post("/api/people", json={"name": "B", "role": "", "beltpack": "2"}).get_json()
    auth_client.post("/api/people", json={"name": "C", "role": "", "beltpack": "3"})
    r = auth_client.post("/api/people/delete-batch", json={"ids": [a["id"], b["id"]]})
    assert r.get_json() == {"deleted": 2}
    state = auth_client.get("/api/state").get_json()
    assert [p["beltpack"] for p in state["people"]] == ["3"]


def test_put_draft_replaces_and_persists(auth_client):
    payload = {
        "title": "Festival 2026", "subtitle": "Grande scène", "theme": "day",
        "groups": [{"id": "g1", "name": "Régie", "color": "#00A8E8", "order": 0}],
        "people": [{"id": "p1", "name": "Jean", "role": "Régie", "beltpack": "5", "group_id": "g1"}],
    }
    r = auth_client.put("/api/draft", json=payload)
    assert r.status_code == 200
    state = auth_client.get("/api/state").get_json()
    assert state["title"] == "Festival 2026"
    assert state["theme"] == "day"
    assert state["people"][0]["beltpack"] == "5"
    assert state["beltpack_roles"]["5"] == "Régie"


def test_put_draft_duplicate_beltpack_409(auth_client):
    payload = {"title": "x", "groups": [], "people": [
        {"id": "a", "name": "A", "role": "", "beltpack": "5", "group_id": None},
        {"id": "b", "name": "B", "role": "", "beltpack": "5", "group_id": None}]}
    r = auth_client.put("/api/draft", json=payload)
    assert r.status_code == 409


def test_import_invalid_400(auth_client):
    # structure invalide (groups pas une liste) → 400 via build_draft
    r = auth_client.post("/api/import", json={"groups": "pas une liste", "people": [], "version": 1})
    assert r.status_code == 400


def test_import_orphan_group_is_sanitized(auth_client):
    # group_id orphelin : toléré comme partout (→ pool), cohérent avec PUT /api/draft
    r = auth_client.post("/api/import", json={
        "version": 1, "groups": [],
        "people": [{"id": "1", "role": "", "beltpack": "7", "group_id": "ghost"}]})
    assert r.status_code == 200
    assert r.get_json()["people"][0]["group_id"] is None


def test_import_malformed_person_no_500(auth_client):
    # personne sans clé beltpack : erreur métier propre (409), JAMAIS un 500
    r = auth_client.post("/api/import", json={"version": 1, "groups": [], "people": [{"role": "x"}]})
    assert r.status_code in (200, 400, 409)


# --- Robustesse des payloads (durcissement 2026-07-06) ---

def test_non_dict_json_returns_400(auth_client):
    # Un JSON valide mais non-objet (liste) ne doit jamais produire un 500
    r = auth_client.post("/api/groups", json=[1, 2, 3])
    assert r.status_code == 400
    r2 = auth_client.post("/api/people", json="texte")
    assert r2.status_code == 400
    r3 = auth_client.put("/api/settings", json=[["a"]])
    assert r3.status_code == 400


def test_missing_required_keys_return_4xx(auth_client):
    # Clé obligatoire absente → erreur client (4xx), pas un KeyError → 500
    r = auth_client.post("/api/groups", json={"color": "#fff"})
    assert r.status_code == 400
    r2 = auth_client.post("/api/people", json={"role": "HF"})
    assert r2.status_code in (400, 409)   # beltpack manquant = beltpack vide


def test_concurrent_mutations_are_not_lost(app, auth_client):
    # Deux mutations simultanées ne doivent pas s'écraser (read-modify-write sous lock)
    import threading
    import time as _time

    storage = app.extensions["storage"]
    original = storage.load_draft
    def slow_load(*a, **k):
        state = original(*a, **k)
        _time.sleep(0.05)   # élargit la fenêtre load→save pour rendre la course certaine
        return state
    storage.load_draft = slow_load
    try:
        def post(bp):
            with app.test_client() as c:
                c.post("/admin/login", data={"password": "motdepasse8"})
                c.post("/api/people", json={"role": "X", "beltpack": bp})
        t1 = threading.Thread(target=post, args=("101",))
        t2 = threading.Thread(target=post, args=("102",))
        t1.start()
        t2.start()
        t1.join()
        t2.join()
    finally:
        storage.load_draft = original
    people = auth_client.get("/api/state").get_json()["people"]
    assert {p["beltpack"] for p in people} == {"101", "102"}


def test_reboot_route_simulated_under_tests(auth_client):
    r = auth_client.post("/api/reboot")
    assert r.status_code == 200
    assert r.get_json().get("simulated") is True


# --- _trigger_reboot : l'échec ne doit JAMAIS être avalé (bug du Popen fire-and-forget) ---

def _fake_run(returncode=0, stderr=""):
    import subprocess

    class Proc:
        pass

    def run(cmd, **kwargs):
        assert cmd[:2] == ["sudo", "-n"], "sudo doit être non-interactif (sinon il bloque sans TTY)"
        p = Proc()
        p.returncode = returncode
        p.stderr = stderr
        return p
    return run, subprocess


def test_trigger_reboot_ok(monkeypatch):
    from comroster import api
    run, subprocess = _fake_run(returncode=0)
    monkeypatch.setattr(subprocess, "run", run)
    assert api._trigger_reboot() == (True, None)


def test_trigger_reboot_reports_sudo_refusal(monkeypatch):
    """Droit sudo manquant (Pi installé avant l'ajout de /etc/sudoers.d/comroster-reboot)."""
    from comroster import api
    run, subprocess = _fake_run(returncode=1, stderr="sudo: a password is required\n")
    monkeypatch.setattr(subprocess, "run", run)
    ok, error = api._trigger_reboot()
    assert ok is False
    assert "password is required" in error


def test_trigger_reboot_timeout_is_not_an_error(monkeypatch):
    """Pas de retour = la machine est en train de partir : on ne crie pas à l'erreur."""
    import subprocess
    from comroster import api

    def run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, 10)
    monkeypatch.setattr(subprocess, "run", run)
    assert api._trigger_reboot() == (True, None)


def test_trigger_reboot_missing_binary(monkeypatch):
    import subprocess
    from comroster import api

    def run(cmd, **kwargs):
        raise OSError("sudo introuvable")
    monkeypatch.setattr(subprocess, "run", run)
    ok, error = api._trigger_reboot()
    assert ok is False and "introuvable" in error


# --- Application réseau à chaud (sans redémarrage) ---

def test_apply_network_restarts_the_network_service(monkeypatch):
    import subprocess
    from comroster import api
    seen = {}

    class Proc:
        returncode = 0
        stderr = ""

    def run(cmd, **kwargs):
        seen["cmd"] = cmd
        return Proc()
    monkeypatch.setattr(subprocess, "run", run)

    assert api._apply_network() == (True, None)
    # C'est bien le service d'application réseau qui est rejoué, via sudo non-interactif.
    assert seen["cmd"] == ["sudo", "-n", "systemctl", "restart", "comroster-network.service"]


def test_apply_network_reports_refusal(monkeypatch):
    import subprocess
    from comroster import api

    class Proc:
        returncode = 1
        stderr = "sudo: a password is required\n"

    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: Proc())
    ok, error = api._apply_network()
    assert ok is False and "password is required" in error


def test_apply_network_route_simulated_under_tests(auth_client):
    r = auth_client.post("/api/network/apply")
    assert r.status_code == 200
    assert r.get_json().get("simulated") is True


def test_apply_network_route_requires_login(client):
    assert client.post("/api/network/apply").status_code in (302, 401, 403)
