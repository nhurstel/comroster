import uuid
from datetime import datetime, timezone


class ValidationError(Exception):
    def __init__(self, message, code="invalid"):
        super().__init__(message)
        self.code = code


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_id():
    return str(uuid.uuid4())


DEFAULT_TITLE = "Affectation Intercom"


def sanitize_theme(value):
    return "day" if value == "day" else "night"


def sanitize_scale(value):
    return value if value in ("normal", "large", "xlarge") else "normal"


def sanitize_indicators(value):
    """Préférences d'affichage des indicateurs beltpack (statut/batterie/réception)."""
    v = value if isinstance(value, dict) else {}
    return {k: bool(v.get(k, True)) for k in ("online", "battery", "signal")}


def empty_state():
    return {
        "version": 1,
        "updated_at": now_iso(),
        "title": DEFAULT_TITLE,
        "subtitle": "",
        "theme": "night",
        "scale": "normal",
        "indicators": {"online": True, "battery": True, "signal": True},
        "groups": [],
        "people": [],
        "beltpack_roles": {},
    }


def build_draft(payload):
    """Construit un brouillon valide à partir d'un payload client complet.

    Tolérant sur les détails de présentation (ids manquants → générés, group_id
    orphelin → pool), mais strict sur les invariants métier : unicité du beltpack
    et beltpack non vide (validés via validate_state, qui lève ValidationError).
    """
    if not isinstance(payload, dict):
        raise ValidationError("Payload invalide", code="invalid")

    state = empty_state()
    state["title"] = (payload.get("title") or "").strip() or DEFAULT_TITLE
    state["subtitle"] = (payload.get("subtitle") or "").strip()
    state["theme"] = sanitize_theme(payload.get("theme"))
    state["scale"] = sanitize_scale(payload.get("scale"))
    state["indicators"] = sanitize_indicators(payload.get("indicators"))

    groups = payload.get("groups")
    if not isinstance(groups, list):
        raise ValidationError("groups doit être une liste", code="invalid")
    group_ids = set()
    for index, g in enumerate(groups):
        if not isinstance(g, dict):
            raise ValidationError("Groupe invalide", code="invalid")
        gid = g.get("id") or new_id()
        order = g.get("order")
        state["groups"].append({
            "id": gid,
            "name": (g.get("name") or "").strip() or "Groupe",
            "color": g.get("color") or "#3AAFA9",
            "order": order if isinstance(order, int) else index,
        })
        group_ids.add(gid)

    people = payload.get("people")
    if not isinstance(people, list):
        raise ValidationError("people doit être une liste", code="invalid")
    for p in people:
        if not isinstance(p, dict):
            raise ValidationError("Personne invalide", code="invalid")
        gid = p.get("group_id")
        if gid is not None and gid not in group_ids:
            gid = None  # group_id orphelin → retour au pool
        state["people"].append({
            "id": p.get("id") or new_id(),
            "role": (p.get("role") or "").strip(),
            "beltpack": normalize_beltpack(p.get("beltpack")),
            "group_id": gid,
        })

    validate_state(state)  # unicité beltpack + beltpack non vide

    roles = {}
    incoming = payload.get("beltpack_roles")
    if isinstance(incoming, dict):
        for key, value in incoming.items():
            if value:
                roles[normalize_beltpack(key)] = value
    for person in state["people"]:
        if person["role"]:
            roles[person["beltpack"]] = person["role"]
    state["beltpack_roles"] = roles

    touch(state)
    return state


def role_for_beltpack(state, beltpack):
    """Rôle mémorisé pour ce numéro de beltpack, ou None."""
    return state.get("beltpack_roles", {}).get(normalize_beltpack(beltpack))


def _remember_role(state, beltpack, role):
    """Mémorise la correspondance numéro → rôle (le rôle suit le beltpack)."""
    if role:
        state.setdefault("beltpack_roles", {})[normalize_beltpack(beltpack)] = role


def touch(state):
    state["updated_at"] = now_iso()


def normalize_beltpack(value):
    return (value or "").strip()


def _find(items, item_id):
    for item in items:
        if item["id"] == item_id:
            return item
    return None


def _assert_beltpack_free(state, beltpack, ignore_id=None):
    norm = normalize_beltpack(beltpack)
    if not norm:
        raise ValidationError("Le numéro de beltpack est obligatoire", code="beltpack_empty")
    for person in state["people"]:
        if person["id"] == ignore_id:
            continue
        if normalize_beltpack(person["beltpack"]) == norm:
            raise ValidationError(f"Beltpack {norm} déjà attribué", code="beltpack_conflict")


def add_group(state, name, color, order=None):
    group = {
        "id": new_id(),
        "name": name,
        "color": color,
        "order": order if order is not None else len(state["groups"]),
    }
    state["groups"].append(group)
    touch(state)
    return group


def update_group(state, group_id, **fields):
    group = _find(state["groups"], group_id)
    if group is None:
        raise ValidationError("Groupe introuvable", code="not_found")
    for key in ("name", "color", "order"):
        if key in fields and fields[key] is not None:
            group[key] = fields[key]
    touch(state)
    return group


def delete_group(state, group_id):
    group = _find(state["groups"], group_id)
    if group is None:
        raise ValidationError("Groupe introuvable", code="not_found")
    for person in state["people"]:
        if person["group_id"] == group_id:
            person["group_id"] = None
    state["groups"].remove(group)
    touch(state)


def add_person(state, role, beltpack, group_id=None):
    """Ajoute un beltpack : ID (beltpack) + Nom (role). Pas de nom de personne."""
    _assert_beltpack_free(state, beltpack)
    if group_id is not None and _find(state["groups"], group_id) is None:
        raise ValidationError("Groupe cible introuvable", code="not_found")
    # Le nom suit le beltpack : s'il n'est pas fourni, on hérite du nom mémorisé.
    if not role:
        role = role_for_beltpack(state, beltpack) or ""
    person = {
        "id": new_id(),
        "role": role,
        "beltpack": normalize_beltpack(beltpack),
        "group_id": group_id,
    }
    state["people"].append(person)
    _remember_role(state, person["beltpack"], role)
    touch(state)
    return person


def update_person(state, person_id, **fields):
    person = _find(state["people"], person_id)
    if person is None:
        raise ValidationError("Personne introuvable", code="not_found")
    if "beltpack" in fields and fields["beltpack"] is not None:
        _assert_beltpack_free(state, fields["beltpack"], ignore_id=person_id)
        person["beltpack"] = normalize_beltpack(fields["beltpack"])
    if "group_id" in fields:
        gid = fields["group_id"]
        if gid is not None and _find(state["groups"], gid) is None:
            raise ValidationError("Groupe cible introuvable", code="not_found")
        person["group_id"] = gid
    if "role" in fields and fields["role"] is not None:
        person["role"] = fields["role"]
    _remember_role(state, person["beltpack"], person["role"])
    touch(state)
    return person


def delete_person(state, person_id):
    person = _find(state["people"], person_id)
    if person is None:
        raise ValidationError("Personne introuvable", code="not_found")
    state["people"].remove(person)
    touch(state)


def validate_state(state):
    seen = set()
    group_ids = {g["id"] for g in state["groups"]}
    for person in state["people"]:
        norm = normalize_beltpack(person["beltpack"])
        if not norm:
            raise ValidationError("Beltpack vide détecté", code="beltpack_empty")
        if norm in seen:
            raise ValidationError(f"Beltpack {norm} en double", code="beltpack_conflict")
        seen.add(norm)
        if person["group_id"] is not None and person["group_id"] not in group_ids:
            raise ValidationError("group_id orphelin", code="orphan_group")


def _person_by_beltpack(state, number):
    norm = normalize_beltpack(number)
    for person in state["people"]:
        if normalize_beltpack(person["beltpack"]) == norm:
            return person
    return None


def merge_beltpacks(state, items):
    """Synchronise les beltpacks de l'antenne dans l'état (antenne fait foi).

    Crée les numéros absents (au pool, nom vide), met à jour le rôle des
    existants, préserve nom et groupe, ne supprime jamais.
    """
    created = updated = 0
    roles = state.setdefault("beltpack_roles", {})
    for item in items:
        num = normalize_beltpack(item.get("number"))
        if not num:
            continue
        name = (item.get("name") or "").strip()
        person = _person_by_beltpack(state, num)
        if person is None:
            state["people"].append({
                "id": new_id(), "role": name,
                "beltpack": num, "group_id": None,
            })
            created += 1
        elif name and person["role"] != name:
            person["role"] = name
            updated += 1
        if name:
            roles[num] = name
    touch(state)
    return {"created": created, "updated": updated}


def diff_beltpacks(state, items):
    """Récap d'un import sans muter l'état."""
    by_num = {normalize_beltpack(p["beltpack"]): p for p in state["people"]}
    seen = set()
    new, changed, unchanged = [], [], 0
    for item in items:
        num = normalize_beltpack(item.get("number"))
        if not num:
            continue
        seen.add(num)
        name = (item.get("name") or "").strip()
        person = by_num.get(num)
        if person is None:
            new.append({"number": num, "name": name})
        elif name and person["role"] != name:
            changed.append({"number": num, "old_role": person["role"], "new_role": name})
        else:
            unchanged += 1
    missing = [
        {"number": normalize_beltpack(p["beltpack"]), "role": p["role"]}
        for p in state["people"]
        if normalize_beltpack(p["beltpack"]) not in seen
    ]
    return {"new": new, "changed": changed, "unchanged": unchanged, "missing": missing}


def filter_by_ranges(items, ranges):
    if not ranges:
        return list(items)
    out = []
    for item in items:
        try:
            n = int(item.get("number"))
        except (TypeError, ValueError):
            continue
        if any(lo <= n <= hi for lo, hi in ranges):
            out.append(item)
    return out


def mirror_beltpacks(state, items):
    """Miroir : l'antenne fait foi. Ajoute/maj, retire les absents, préserve nom+groupe."""
    created = updated = 0
    roles = state.setdefault("beltpack_roles", {})
    wanted = {normalize_beltpack(it.get("number")) for it in items if normalize_beltpack(it.get("number"))}
    for item in items:
        num = normalize_beltpack(item.get("number"))
        if not num:
            continue
        name = (item.get("name") or "").strip()
        person = _person_by_beltpack(state, num)
        if person is None:
            state["people"].append({"id": new_id(), "role": name,
                                    "beltpack": num, "group_id": None})
            created += 1
        elif name and person["role"] != name:
            person["role"] = name
            updated += 1
        if name:
            roles[num] = name
    before = len(state["people"])
    state["people"] = [p for p in state["people"] if normalize_beltpack(p["beltpack"]) in wanted]
    removed = before - len(state["people"])
    touch(state)
    return {"created": created, "updated": updated, "removed": removed}


def delete_people(state, ids):
    idset = set(ids)
    before = len(state["people"])
    state["people"] = [p for p in state["people"] if p["id"] not in idset]
    deleted = before - len(state["people"])
    touch(state)
    return deleted
