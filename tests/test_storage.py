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
