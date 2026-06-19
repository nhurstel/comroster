import pytest
from comroster.services.storage import Storage
from comroster.services.history import History
from comroster.services import model


def test_archive_and_list(tmp_path):
    h = History(Storage(str(tmp_path)))
    ts = h.archive(model.empty_state())
    items = h.list()
    assert len(items) == 1 and items[0]["timestamp"] == ts


def test_load_snapshot(tmp_path):
    h = History(Storage(str(tmp_path)))
    s = model.empty_state()
    model.add_person(s, "Jean", "HF", "12")
    ts = h.archive(s)
    loaded = h.load(ts)
    assert loaded["people"][0]["name"] == "Jean"


def test_load_unknown_raises(tmp_path):
    h = History(Storage(str(tmp_path)))
    with pytest.raises(KeyError):
        h.load("nope")
