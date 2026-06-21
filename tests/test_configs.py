import pytest
from comroster.services.storage import Storage
from comroster.services.configs import Configs
from comroster.services import model


def test_save_list_load(tmp_path):
    c = Configs(Storage(str(tmp_path)))
    s = model.empty_state()
    model.add_person(s, "Régie", "5")
    c.save("Jour 2", s)
    items = c.list()
    assert [i["name"] for i in items] == ["Jour 2"]
    loaded = c.load("Jour 2")
    assert loaded["people"][0]["role"] == "Régie"


def test_save_empty_name_raises(tmp_path):
    c = Configs(Storage(str(tmp_path)))
    with pytest.raises(ValueError):
        c.save("  ", model.empty_state())


def test_overwrite_same_name(tmp_path):
    c = Configs(Storage(str(tmp_path)))
    c.save("Base", model.empty_state())
    s2 = model.empty_state()
    model.add_person(s2, "X", "1")
    c.save("Base", s2)
    assert len(c.list()) == 1
    assert len(c.load("Base")["people"]) == 1


def test_delete(tmp_path):
    c = Configs(Storage(str(tmp_path)))
    c.save("Base", model.empty_state())
    c.delete("Base")
    assert c.list() == []


def test_load_missing_raises(tmp_path):
    c = Configs(Storage(str(tmp_path)))
    with pytest.raises(KeyError):
        c.load("Nope")
