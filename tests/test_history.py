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
    model.add_person(s, "HF", "12")
    ts = h.archive(s)
    loaded = h.load(ts)
    assert loaded["people"][0]["role"] == "HF"


def test_load_unknown_raises(tmp_path):
    h = History(Storage(str(tmp_path)))
    with pytest.raises(KeyError):
        h.load("nope")


def test_history_caps_snapshots(tmp_path):
    import os
    h = History(Storage(str(tmp_path)))
    # on sème plus de snapshots que la limite (vieux timestamps)
    for i in range(History.MAX_SNAPSHOTS + 15):
        open(os.path.join(h.dir, f"2026010100{i:04d}000000Z.json"), "w").write("{}")
    h.archive(model.empty_state())          # déclenche la purge ; le nouveau est récent
    items = h.list()
    assert len(items) == History.MAX_SNAPSHOTS
    # le snapshot fraîchement archivé (le plus récent) est conservé
    assert items[0]["timestamp"].startswith("202") and items[0]["timestamp"] > "2026010199"


def test_load_corrupt_snapshot_raises(tmp_path):
    import os
    h = History(Storage(str(tmp_path)))
    with open(os.path.join(h.dir, "20260101T000000000000Z.json"), "w") as fh:
        fh.write("{ corrompu")
    with pytest.raises(KeyError):       # corrompu sans sauvegarde → traité comme absent
        h.load("20260101T000000000000Z")
