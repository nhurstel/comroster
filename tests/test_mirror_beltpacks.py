from comroster.services import model


def test_filter_by_ranges_empty_keeps_all():
    items = [{"number": "5", "name": "A", "online": True}]
    assert model.filter_by_ranges(items, []) == items


def test_filter_by_ranges_multiple_intervals():
    items = [{"number": str(n), "name": "x", "online": True} for n in (3, 12, 30, 52)]
    out = model.filter_by_ranges(items, [[1, 25], [50, 54]])
    assert [i["number"] for i in out] == ["3", "12", "52"]


def test_filter_by_ranges_excludes_non_integer_when_ranged():
    items = [{"number": "REG", "name": "x", "online": True}]
    assert model.filter_by_ranges(items, [[1, 25]]) == []


def test_mirror_creates_updates_removes():
    s = model.empty_state()
    g = model.add_group(s, "Plateau", "#fff")
    keep = model.add_person(s, "Ancien", "5", g["id"])   # nom change, conservé
    model.add_person(s, "X", "9")                         # absent antenne → retiré
    res = model.mirror_beltpacks(s, [
        {"number": "5", "name": "Régie Son", "online": True},
        {"number": "7", "name": "Lumière", "online": False},
    ])
    assert res == {"created": 1, "updated": 1, "removed": 1}
    nums = sorted(p["beltpack"] for p in s["people"])
    assert nums == ["5", "7"]                       # 9 retiré, 7 créé
    assert keep["role"] == "Régie Son" and keep["group_id"] == g["id"]  # groupe préservé
    assert s["beltpack_roles"]["7"] == "Lumière"


def test_mirror_empty_items_clears_all():
    s = model.empty_state()
    model.add_person(s, "R", "5")
    res = model.mirror_beltpacks(s, [])
    assert res["removed"] == 1 and s["people"] == []


def test_delete_people_by_ids():
    s = model.empty_state()
    a = model.add_person(s, "Rôle A", "1")
    b = model.add_person(s, "Rôle B", "2")
    n = model.delete_people(s, [a["id"], "ghost"])
    assert n == 1 and [p["id"] for p in s["people"]] == [b["id"]]
