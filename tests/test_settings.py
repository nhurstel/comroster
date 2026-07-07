from comroster.services.storage import Storage
from comroster.services.settings import Settings


def test_default_empty(tmp_path):
    s = Settings(Storage(str(tmp_path)))
    assert s.get("bolero_enabled", False) is False
    assert s.all() == {}


def test_set_and_persist(tmp_path):
    st = Storage(str(tmp_path))
    Settings(st).set("bolero_enabled", True)
    # nouvelle instance relit le disque
    assert Settings(st).get("bolero_enabled") is True


def test_set_overwrites(tmp_path):
    st = Storage(str(tmp_path))
    s = Settings(st)
    s.set("bolero_enabled", True)
    s.set("bolero_enabled", False)
    assert s.get("bolero_enabled") is False


def test_corrupt_settings_does_not_crash(tmp_path):
    st = Storage(str(tmp_path))
    s = Settings(st)
    with open(s.path, "w") as fh:
        fh.write("{ pas du json")
    assert s.all() == {}                 # lecture défensive : pas de 500
    assert s.get("antenna_ranges", []) == []


def test_ranges_reject_booleans(app, client):
    # True/False sont des int en Python : ils ne sont pas des bornes valides
    client.post("/admin/setup", data={"password": "motdepasse8"})
    r = client.put("/api/settings", json={"antenna_ranges": [[True, 5]]})
    assert r.status_code == 400
