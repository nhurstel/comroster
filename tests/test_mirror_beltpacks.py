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


# --- Plages = périmètre de gestion du miroir (durcissement 2026-07-06) ---

def test_mirror_with_ranges_preserves_out_of_scope_people():
    # Un beltpack ajouté à la main HORS plage ne doit pas être supprimé par le miroir
    state = model.empty_state()
    model.add_person(state, "Régie", "42", None)      # hors plage 1-10
    model.add_person(state, "HF", "5", None)          # dans la plage, absent de l'antenne
    items = [{"number": "3", "name": "Plateau"}]      # l'antenne ne voit que le 3
    result = model.mirror_beltpacks(state, items, ranges=[[1, 10]])
    nums = {p["beltpack"] for p in state["people"]}
    assert "42" in nums          # hors périmètre → intouchable
    assert "5" not in nums       # dans le périmètre et absent → retiré
    assert "3" in nums           # créé
    assert result["removed"] == 1


def test_mirror_without_ranges_removes_everything_absent():
    # Sans plage configurée : comportement historique (l'antenne fait foi partout)
    state = model.empty_state()
    model.add_person(state, "Régie", "42", None)
    result = model.mirror_beltpacks(state, [{"number": "3", "name": "P"}], ranges=[])
    assert {p["beltpack"] for p in state["people"]} == {"3"}
    assert result["removed"] == 1


def test_diff_with_ranges_ignores_out_of_scope_missing():
    # La préview doit être cohérente avec l'apply : 42 hors plage n'est pas "à retirer"
    state = model.empty_state()
    model.add_person(state, "Régie", "42", None)
    model.add_person(state, "HF", "5", None)
    diff = model.diff_beltpacks(state, [{"number": "3", "name": "P"}], ranges=[[1, 10]])
    missing_nums = {m["number"] for m in diff["missing"]}
    assert missing_nums == {"5"}
