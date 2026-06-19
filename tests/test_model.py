import pytest
from comroster.services import model


def test_empty_state_shape():
    s = model.empty_state()
    assert s["version"] == 1 and s["groups"] == [] and s["people"] == []
    assert "updated_at" in s


def test_add_person_and_group():
    s = model.empty_state()
    g = model.add_group(s, "Plateau", "#00A8E8")
    p = model.add_person(s, "Jean", "HF", "12", g["id"])
    assert p["group_id"] == g["id"]
    assert len(s["people"]) == 1


def test_beltpack_must_be_unique_on_add():
    s = model.empty_state()
    model.add_person(s, "Jean", "HF", "12")
    with pytest.raises(model.ValidationError) as exc:
        model.add_person(s, "Marie", "Lumière", "12")
    assert exc.value.code == "beltpack_conflict"


def test_beltpack_unique_ignores_whitespace():
    s = model.empty_state()
    model.add_person(s, "Jean", "HF", "12")
    with pytest.raises(model.ValidationError):
        model.add_person(s, "Marie", "Lum", " 12 ")


def test_beltpack_cannot_be_empty():
    s = model.empty_state()
    with pytest.raises(model.ValidationError):
        model.add_person(s, "Jean", "HF", "  ")


def test_update_person_to_taken_beltpack_rejected():
    s = model.empty_state()
    model.add_person(s, "Jean", "HF", "12")
    p2 = model.add_person(s, "Marie", "Lum", "13")
    with pytest.raises(model.ValidationError) as exc:
        model.update_person(s, p2["id"], beltpack="12")
    assert exc.value.code == "beltpack_conflict"


def test_update_person_same_beltpack_allowed():
    s = model.empty_state()
    p = model.add_person(s, "Jean", "HF", "12")
    model.update_person(s, p["id"], name="Jean-Paul")  # garde 12
    assert p["name"] == "Jean-Paul"


def test_delete_group_returns_members_to_pool():
    s = model.empty_state()
    g = model.add_group(s, "Plateau", "#fff")
    p = model.add_person(s, "Jean", "HF", "12", g["id"])
    model.delete_group(s, g["id"])
    assert g not in s["groups"]
    assert p in s["people"] and p["group_id"] is None


def test_validate_state_detects_orphan_group_id():
    s = model.empty_state()
    s["people"].append({"id": "x", "name": "A", "role": "", "beltpack": "1", "group_id": "ghost"})
    with pytest.raises(model.ValidationError):
        model.validate_state(s)


def test_not_found():
    s = model.empty_state()
    with pytest.raises(model.ValidationError) as exc:
        model.update_person(s, "nope", name="X")
    assert exc.value.code == "not_found"
