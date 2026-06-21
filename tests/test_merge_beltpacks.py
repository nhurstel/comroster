from comroster.services import model


def _items():
    return [
        {"number": "5", "name": "Régie Son", "online": True},
        {"number": "7", "name": "Lumière", "online": False},
    ]


def test_merge_creates_in_pool():
    s = model.empty_state()
    res = model.merge_beltpacks(s, _items())
    assert res == {"created": 2, "updated": 0}
    p5 = [p for p in s["people"] if p["beltpack"] == "5"][0]
    assert p5["name"] == "" and p5["role"] == "Régie Son" and p5["group_id"] is None
    assert s["beltpack_roles"]["5"] == "Régie Son"


def test_merge_updates_role_preserves_name_and_group():
    s = model.empty_state()
    g = model.add_group(s, "Plateau", "#fff")
    p = model.add_person(s, "Jean", "Ancien", "5", g["id"])
    res = model.merge_beltpacks(s, [{"number": "5", "name": "Régie Son", "online": True}])
    assert res == {"created": 0, "updated": 1}
    assert p["role"] == "Régie Son"        # rôle mis à jour
    assert p["name"] == "Jean"             # nom préservé
    assert p["group_id"] == g["id"]        # groupe préservé


def test_merge_no_duplicate_and_no_delete():
    s = model.empty_state()
    model.add_person(s, "Marie", "X", "9")   # fiche manuelle absente de l'antenne
    model.merge_beltpacks(s, _items())
    numbers = sorted(p["beltpack"] for p in s["people"])
    assert numbers == ["5", "7", "9"]        # 9 conservée, pas de doublon


def test_merge_skips_empty_number():
    s = model.empty_state()
    res = model.merge_beltpacks(s, [{"number": "  ", "name": "X", "online": True}])
    assert res == {"created": 0, "updated": 0} and s["people"] == []


def test_diff_reports_new_changed_unchanged_missing():
    s = model.empty_state()
    model.add_person(s, "Jean", "Régie Son", "5")   # identique
    model.add_person(s, "Paul", "Ancien", "7")      # rôle change
    model.add_person(s, "Marie", "X", "9")          # absente de l'antenne
    d = model.diff_beltpacks(s, [
        {"number": "5", "name": "Régie Son", "online": True},
        {"number": "7", "name": "Lumière", "online": True},
        {"number": "12", "name": "HF 2", "online": True},
    ])
    assert d["new"] == [{"number": "12", "name": "HF 2"}]
    assert d["changed"] == [{"number": "7", "old_role": "Ancien", "new_role": "Lumière"}]
    assert d["unchanged"] == 1
    assert d["missing"] == [{"number": "9", "role": "X"}]
