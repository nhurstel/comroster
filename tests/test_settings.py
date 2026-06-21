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
