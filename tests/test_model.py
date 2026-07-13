import pytest
from comroster.services import model


def test_empty_state_shape():
    s = model.empty_state()
    assert s["version"] == 1 and s["groups"] == [] and s["people"] == []
    assert "updated_at" in s
    assert "scale" not in s          # taille du texte retirée


def test_empty_state_indicators_default_on():
    assert model.empty_state()["indicators"] == {"online": True, "battery": True}


def test_build_draft_indicators_partial():
    s = model.build_draft({"groups": [], "people": [], "indicators": {"battery": False}})
    assert s["indicators"] == {"online": True, "battery": False}


def test_build_draft_indicators_invalid_defaults_on():
    s = model.build_draft({"groups": [], "people": [], "indicators": "nope"})
    assert s["indicators"] == {"online": True, "battery": True}


def test_add_person_and_group():
    s = model.empty_state()
    g = model.add_group(s, "Plateau", "#00A8E8")
    p = model.add_person(s, "HF", "12", g["id"])
    assert p["group_id"] == g["id"]
    assert "name" not in p          # plus de nom de personne
    assert len(s["people"]) == 1


def test_beltpack_must_be_unique_on_add():
    s = model.empty_state()
    model.add_person(s, "HF", "12")
    with pytest.raises(model.ValidationError) as exc:
        model.add_person(s, "Lumière", "12")
    assert exc.value.code == "beltpack_conflict"


def test_beltpack_unique_ignores_whitespace():
    s = model.empty_state()
    model.add_person(s, "HF", "12")
    with pytest.raises(model.ValidationError):
        model.add_person(s, "Lum", " 12 ")


def test_beltpack_cannot_be_empty():
    s = model.empty_state()
    with pytest.raises(model.ValidationError):
        model.add_person(s, "HF", "  ")


def test_update_person_to_taken_beltpack_rejected():
    s = model.empty_state()
    model.add_person(s, "HF", "12")
    p2 = model.add_person(s, "Lum", "13")
    with pytest.raises(model.ValidationError) as exc:
        model.update_person(s, p2["id"], beltpack="12")
    assert exc.value.code == "beltpack_conflict"


def test_update_person_role():
    s = model.empty_state()
    p = model.add_person(s, "HF", "12")
    model.update_person(s, p["id"], role="Régie")
    assert p["role"] == "Régie"


def test_delete_group_returns_members_to_pool():
    s = model.empty_state()
    g = model.add_group(s, "Plateau", "#fff")
    p = model.add_person(s, "HF", "12", g["id"])
    model.delete_group(s, g["id"])
    assert g not in s["groups"]
    assert p in s["people"] and p["group_id"] is None


def test_validate_state_detects_orphan_group_id():
    s = model.empty_state()
    s["people"].append({"id": "x", "role": "", "beltpack": "1", "group_id": "ghost"})
    with pytest.raises(model.ValidationError):
        model.validate_state(s)


def test_not_found():
    s = model.empty_state()
    with pytest.raises(model.ValidationError) as exc:
        model.update_person(s, "nope", role="X")
    assert exc.value.code == "not_found"


def test_role_remembered_per_beltpack():
    s = model.empty_state()
    model.add_person(s, "Régie", "5")
    assert model.role_for_beltpack(s, "5") == "Régie"
    assert s["beltpack_roles"]["5"] == "Régie"


def test_role_inherited_when_absent_after_release():
    s = model.empty_state()
    p = model.add_person(s, "Régie", "5")
    model.delete_person(s, p["id"])  # beltpack 5 libéré, correspondance conservée
    again = model.add_person(s, "", "5")
    assert again["role"] == "Régie"


def test_role_update_reflected_in_memory():
    s = model.empty_state()
    p = model.add_person(s, "Régie", "5")
    model.update_person(s, p["id"], role="Lumière")
    assert model.role_for_beltpack(s, "5") == "Lumière"


def test_role_for_unknown_beltpack_is_none():
    s = model.empty_state()
    assert model.role_for_beltpack(s, "99") is None


def test_empty_state_has_meta():
    s = model.empty_state()
    assert s["title"]
    assert s["subtitle"] == ""
    assert s["theme"] == "night"


def test_sanitize_theme():
    assert model.sanitize_theme("day") == "day"
    assert model.sanitize_theme("night") == "night"
    assert model.sanitize_theme("nimporte") == "night"


def test_build_draft_basic():
    payload = {
        "title": "Festival", "subtitle": "Scène A", "theme": "day",
        "groups": [{"id": "g1", "name": "Régie", "color": "#ffffff", "order": 0}],
        "people": [{"id": "p1", "role": "Régie", "beltpack": "5", "group_id": "g1"}],
    }
    s = model.build_draft(payload)
    assert s["title"] == "Festival" and s["subtitle"] == "Scène A" and s["theme"] == "day"
    assert s["groups"][0]["name"] == "Régie"
    assert s["people"][0]["beltpack"] == "5"
    assert "name" not in s["people"][0]
    assert s["beltpack_roles"]["5"] == "Régie"


def test_build_draft_rejects_duplicate_beltpack():
    payload = {"title": "x", "groups": [], "people": [
        {"id": "a", "role": "", "beltpack": "5", "group_id": None},
        {"id": "b", "role": "", "beltpack": "5", "group_id": None}]}
    with pytest.raises(model.ValidationError) as exc:
        model.build_draft(payload)
    assert exc.value.code == "beltpack_conflict"


def test_build_draft_orphan_group_goes_to_pool():
    payload = {"title": "x", "groups": [], "people": [
        {"id": "a", "role": "R", "beltpack": "5", "group_id": "ghost"}]}
    s = model.build_draft(payload)
    assert s["people"][0]["group_id"] is None


def test_build_draft_generates_missing_ids():
    payload = {"title": "x",
               "groups": [{"name": "G", "color": "#fff"}],
               "people": [{"role": "R", "beltpack": "1"}]}
    s = model.build_draft(payload)
    assert s["groups"][0]["id"]
    assert s["people"][0]["id"]


# --- Mode performance (Raspberry Pi bas de gamme : désactive le flou GPU) ---

def test_empty_state_perf_default_off():
    assert model.empty_state()["perf"] is False

def test_build_draft_perf_on():
    s = model.build_draft({"groups": [], "people": [], "perf": True})
    assert s["perf"] is True

def test_build_draft_perf_absent_defaults_off():
    s = model.build_draft({"groups": [], "people": []})
    assert s["perf"] is False

def test_build_draft_perf_coerces_to_bool():
    s = model.build_draft({"groups": [], "people": [], "perf": "nope"})
    assert s["perf"] is True   # chaîne non vide → activé (cohérent avec bool())
    s2 = model.build_draft({"groups": [], "people": [], "perf": 0})
    assert s2["perf"] is False


def test_columns_default_auto():
    assert model.empty_state()["columns"] == 0


def test_build_draft_columns():
    assert model.build_draft({"groups": [], "people": [], "columns": 3})["columns"] == 3


def test_build_draft_columns_invalid_defaults_auto():
    assert model.build_draft({"groups": [], "people": [], "columns": "nope"})["columns"] == 0
    assert model.build_draft({"groups": [], "people": [], "columns": 99})["columns"] == 0
