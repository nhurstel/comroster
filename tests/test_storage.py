import json
import os
from comroster.services.storage import Storage
from comroster.services import model


def test_save_and_load_draft(tmp_path):
    st = Storage(str(tmp_path))
    state = model.empty_state()
    model.add_person(state, "HF", "12")
    st.save_draft(state)
    loaded = st.load_draft()
    assert loaded["people"][0]["role"] == "HF"
    assert loaded["people"][0]["beltpack"] == "12"


def test_load_draft_creates_empty_when_absent(tmp_path):
    st = Storage(str(tmp_path))
    state = st.load_draft()
    assert state["groups"] == [] and state["people"] == []


def test_load_published_none_when_never_published(tmp_path):
    st = Storage(str(tmp_path))
    assert st.load_published() is None


def test_atomic_write_no_partial_file(tmp_path):
    st = Storage(str(tmp_path))
    st.atomic_write(st.draft_path, {"a": 1})
    leftovers = [f for f in os.listdir(tmp_path) if f.endswith(".tmp")]
    assert leftovers == []
    with open(st.draft_path) as fh:
        assert json.load(fh) == {"a": 1}


def test_atomic_write_overwrites(tmp_path):
    st = Storage(str(tmp_path))
    st.atomic_write(st.draft_path, {"a": 1})
    st.atomic_write(st.draft_path, {"a": 2})
    with open(st.draft_path) as fh:
        assert json.load(fh)["a"] == 2


def test_write_keeps_backup_of_previous(tmp_path):
    st = Storage(str(tmp_path))
    st.atomic_write(st.draft_path, {"v": 1})
    st.atomic_write(st.draft_path, {"v": 2})
    with open(st.draft_path + ".bak") as fh:
        assert json.load(fh)["v"] == 1          # .bak = version précédente


def test_load_recovers_from_backup_on_corruption(tmp_path):
    st = Storage(str(tmp_path))
    st.save_draft({"people": ["good"], "v": 1})
    st.save_draft({"people": ["good"], "v": 2})   # crée le .bak
    with open(st.draft_path, "w") as fh:
        fh.write("{ corrompu !!!")                 # simule une coupure / corruption
    state = st.load_draft()
    assert state["v"] == 1                          # récupéré depuis .bak, pas de crash


def test_load_corrupt_without_backup_returns_empty(tmp_path):
    st = Storage(str(tmp_path))
    with open(st.draft_path, "w") as fh:
        fh.write("pas du json")
    state = st.load_draft()                          # ne doit pas planter
    assert state["people"] == [] and state["groups"] == []


def test_load_published_corrupt_returns_none_without_backup(tmp_path):
    st = Storage(str(tmp_path))
    with open(st.published_path, "w") as fh:
        fh.write("{{{")
    assert st.load_published() is None
