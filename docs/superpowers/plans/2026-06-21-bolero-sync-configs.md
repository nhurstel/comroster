# Sync miroir + plages + configs nommées + suppression multiple — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Faire évoluer la gestion des beltpacks de ComRoster vers un tableau unique synchronisé en miroir avec l'antenne (filtré par plages d'ID, avec récap), une bibliothèque de configs nommées, et la suppression multiple.

**Architecture:** Pas de second brouillon : la connexion/déconnexion antenne ne change pas le tableau. La synchro est un miroir (`mirror_beltpacks`) filtré par plages (`filter_by_ranges`), appliqué après un récap (`diff_beltpacks`, existant). Un service `configs.py` gère des configurations nommées persistées ; charger une config remplace le brouillon et déconnecte l'antenne. Suppression multiple via `delete_people` + endpoint batch.

**Tech Stack:** Python 3.12, Flask, pytest, JS vanilla. (Aucune nouvelle dépendance.)

**Spec de référence :** `docs/superpowers/specs/2026-06-21-bolero-sync-configs-design.md`.

## Global Constraints

- **Un seul brouillon** `data_draft.json`. Connexion/déconnexion antenne **ne le remplacent pas**.
- **Sync = miroir** : `mirror_beltpacks` ajoute les nouveaux, met à jour le rôle, **retire** les beltpacks absents de l'antenne (dans les plages), **préserve nom et groupe** des conservés.
- **Plages** `antenna_ranges` = liste d'intervalles `[lo,hi]` (entiers, `lo<=hi`) dans `settings.json`. Vide ⇒ tous. Filtre **avant** miroir.
- **Configs nommées** : `configs/<slug>.json` dans `DATA_DIR` (**gitignored**). Charger ⇒ `save_draft` + `client.disconnect()`.
- **Récap avant application**, y compris à la première connexion (l'UI enchaîne `preview` après `connect`).
- **Garde flag** : `/api/antenna/*` → 409 si `bolero_enabled` faux. Les endpoints **configs** et **delete-batch** ne sont **pas** gardés par le flag.
- **Sécurité** : tous `login_required` + CSRF. Validation des plages côté serveur (400 sinon).
- **TDD** sur le backend (`filter_by_ranges`, `mirror_beltpacks`, `delete_people`, `Configs`, endpoints). Commits atomiques.

---

## File Structure

| Fichier | Responsabilité |
|---------|----------------|
| `comroster/services/model.py` | + `filter_by_ranges`, `mirror_beltpacks`, `delete_people` |
| `comroster/services/configs.py` | Bibliothèque de configs nommées (CRUD) |
| `comroster/antenna.py` | Sync miroir + plages ; endpoints configs ; delete-batch |
| `comroster/__init__.py` | Instancier `Configs` |
| `templates/admin.html` | Éditeur de plages, dialog Configurations, mode sélection, ligne « à retirer » |
| `static/js/admin.js` | Plages, configs, sélection multiple |
| `static/css/admin.css` | Styles (plages, configs, sélection) |
| `.gitignore` | + `configs/` |
| `tests/test_mirror_beltpacks.py`, `tests/test_configs.py` | nouveaux |
| `tests/test_antenna_api.py` | ajouts (miroir, plages, configs, delete-batch) |

---

## Task 1: Modèle — `filter_by_ranges`, `mirror_beltpacks`, `delete_people`

**Files:**
- Modify: `comroster/services/model.py`
- Test: `tests/test_mirror_beltpacks.py`

**Interfaces:**
- Consumes: `normalize_beltpack`, `new_id`, `touch`, `_person_by_beltpack` (déjà dans `model.py`).
- Produces:
  - `filter_by_ranges(items, ranges) -> list` — `ranges=[]` ⇒ tout ; sinon garde `int(number)` ∈ un `[lo,hi]`.
  - `mirror_beltpacks(state, items) -> dict` → `{"created","updated","removed"}`. Mute `state`. Retire les fiches dont le numéro n'est pas dans `items`.
  - `delete_people(state, ids) -> int`. Mute `state`.

- [ ] **Step 1: Écrire les tests (échouent)**

`tests/test_mirror_beltpacks.py` :
```python
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
    keep = model.add_person(s, "Jean", "Ancien", "5", g["id"])   # rôle change, conservé
    model.add_person(s, "Marie", "X", "9")                       # absent antenne → retiré
    res = model.mirror_beltpacks(s, [
        {"number": "5", "name": "Régie Son", "online": True},
        {"number": "7", "name": "Lumière", "online": False},
    ])
    assert res == {"created": 1, "updated": 1, "removed": 1}
    nums = sorted(p["beltpack"] for p in s["people"])
    assert nums == ["5", "7"]                       # 9 retiré, 7 créé
    assert keep["role"] == "Régie Son" and keep["name"] == "Jean" and keep["group_id"] == g["id"]
    assert s["beltpack_roles"]["7"] == "Lumière"


def test_mirror_empty_items_clears_all():
    s = model.empty_state()
    model.add_person(s, "Jean", "R", "5")
    res = model.mirror_beltpacks(s, [])
    assert res["removed"] == 1 and s["people"] == []


def test_delete_people_by_ids():
    s = model.empty_state()
    a = model.add_person(s, "A", "", "1")
    b = model.add_person(s, "B", "", "2")
    n = model.delete_people(s, [a["id"], "ghost"])
    assert n == 1 and [p["id"] for p in s["people"]] == [b["id"]]
```

- [ ] **Step 2: Lancer (échoue)** — `.venv/bin/pytest tests/test_mirror_beltpacks.py -q` → FAIL.

- [ ] **Step 3: Implémenter dans `model.py`** (ajouter après `diff_beltpacks`)

```python
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
    created = updated = removed = 0
    roles = state.setdefault("beltpack_roles", {})
    wanted = {normalize_beltpack(it.get("number")) for it in items if normalize_beltpack(it.get("number"))}
    for item in items:
        num = normalize_beltpack(item.get("number"))
        if not num:
            continue
        name = (item.get("name") or "").strip()
        person = _person_by_beltpack(state, num)
        if person is None:
            state["people"].append({"id": new_id(), "name": "", "role": name,
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
```

- [ ] **Step 4: Lancer (passe)** — `.venv/bin/pytest tests/test_mirror_beltpacks.py -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add comroster/services/model.py tests/test_mirror_beltpacks.py
git commit -m "feat(bolero): modèle — filter_by_ranges, mirror_beltpacks, delete_people"
```

---

## Task 2: Bibliothèque de configs nommées (`configs.py`)

**Files:**
- Create: `comroster/services/configs.py`
- Modify: `.gitignore`
- Test: `tests/test_configs.py`

**Interfaces:**
- Consumes: `Storage` (`.data_dir`, `.atomic_write(path, data)`).
- Produces:
  - `Configs(storage)`.
  - `.list() -> list[dict]` → `[{"name","updated_at"}]` trié par nom (insensible casse).
  - `.save(name, state) -> None` ; `name` vide ⇒ `ValueError`.
  - `.load(name) -> dict` (le `state`) ; absent ⇒ `KeyError`.
  - `.delete(name) -> None` ; absent ⇒ `KeyError`.

- [ ] **Step 1: Ajouter l'ignore**

`.gitignore` — ajouter sous `antenna.json` :
```
configs/
```

- [ ] **Step 2: Écrire les tests (échouent)**

`tests/test_configs.py` :
```python
import pytest
from comroster.services.storage import Storage
from comroster.services.configs import Configs
from comroster.services import model


def test_save_list_load(tmp_path):
    c = Configs(Storage(str(tmp_path)))
    s = model.empty_state()
    model.add_person(s, "Jean", "Régie", "5")
    c.save("Jour 2", s)
    items = c.list()
    assert [i["name"] for i in items] == ["Jour 2"]
    loaded = c.load("Jour 2")
    assert loaded["people"][0]["name"] == "Jean"


def test_save_empty_name_raises(tmp_path):
    c = Configs(Storage(str(tmp_path)))
    with pytest.raises(ValueError):
        c.save("  ", model.empty_state())


def test_overwrite_same_name(tmp_path):
    c = Configs(Storage(str(tmp_path)))
    c.save("Base", model.empty_state())
    s2 = model.empty_state()
    model.add_person(s2, "X", "", "1")
    c.save("Base", s2)
    assert len(c.list()) == 1
    assert len(c.load("Base")["people"]) == 1


def test_delete(tmp_path):
    c = Configs(Storage(str(tmp_path)))
    c.save("Base", model.empty_state())
    c.delete("Base")
    assert c.list() == []


def test_load_missing_raises(tmp_path):
    c = Configs(Storage(str(tmp_path)))
    with pytest.raises(KeyError):
        c.load("Nope")
```

- [ ] **Step 3: Lancer (échoue)** — `.venv/bin/pytest tests/test_configs.py -q` → FAIL.

- [ ] **Step 4: Implémenter `configs.py`**

```python
import json
import os
import re
from datetime import datetime, timezone


def _slug(name):
    s = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return s or "config"


class Configs:
    def __init__(self, storage):
        self.storage = storage
        self.dir = os.path.join(storage.data_dir, "configs")
        os.makedirs(self.dir, exist_ok=True)

    def _path(self, name):
        return os.path.join(self.dir, f"{_slug(name)}.json")

    def list(self):
        items = []
        for fname in os.listdir(self.dir):
            if not fname.endswith(".json"):
                continue
            try:
                with open(os.path.join(self.dir, fname), encoding="utf-8") as fh:
                    data = json.load(fh)
            except (OSError, json.JSONDecodeError):
                continue
            items.append({"name": data.get("name", fname[:-5]),
                          "updated_at": data.get("updated_at", "")})
        return sorted(items, key=lambda x: x["name"].lower())

    def save(self, name, state):
        if not name or not name.strip():
            raise ValueError("Nom de configuration requis")
        payload = {"name": name.strip(),
                   "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                   "state": state}
        self.storage.atomic_write(self._path(name), payload)

    def load(self, name):
        path = self._path(name)
        if not os.path.exists(path):
            raise KeyError(name)
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)["state"]

    def delete(self, name):
        path = self._path(name)
        if not os.path.exists(path):
            raise KeyError(name)
        os.unlink(path)
```

- [ ] **Step 5: Lancer (passe)** — `.venv/bin/pytest tests/test_configs.py -q` → PASS.

- [ ] **Step 6: Commit**

```bash
git add comroster/services/configs.py tests/test_configs.py .gitignore
git commit -m "feat(bolero): bibliothèque de configs nommées (save/list/load/delete)"
```

---

## Task 3: Endpoints — sync miroir + plages, configs, delete-batch + factory

**Files:**
- Modify: `comroster/antenna.py` (settings étendus, sync miroir, endpoints configs)
- Modify: `comroster/api.py` (endpoint `/api/people/delete-batch`)
- Modify: `comroster/__init__.py` (instancier `Configs`)
- Test: `tests/test_antenna_api.py` (ajouts), `tests/test_api.py` (ajout delete-batch)

**Interfaces:**
- Consumes: `model.filter_by_ranges`, `model.mirror_beltpacks`, `model.diff_beltpacks`, `model.delete_people`, `Configs.list/save/load/delete`, `AntennaClient.fetch_beltpacks/disconnect`, `Settings.get/set`, `Storage.load_draft/save_draft`.
- Produces : voir tableau API du spec. `app.extensions["configs"]`.

- [ ] **Step 1: Écrire les tests (échouent)**

Ajouter à `tests/test_antenna_api.py` (le helper `_fake_ok` y existe déjà ; on en ajoute un avec un BP de plus pour tester plages/miroir) :
```python
def _fake_three(method, path, body=None, timeout=5):
    if path == "/rest/nodeStatus":
        return True, {"nodeStatus": [{"nodeId": 1, "isLocal": True}]}
    if path == "/rest/firmware":
        return True, {"firmware": {"version": "3.4.1-15"}}
    if path == "/rest/bp":
        return True, {"bp": [
            {"registered": True, "id": 1, "connectedNodeId": 1, "bpConfig": {"bpNumber": 5, "bpName": "Régie"}},
            {"registered": True, "id": 2, "connectedNodeId": 0, "bpConfig": {"bpNumber": 7, "bpName": "Lumière"}},
            {"registered": True, "id": 3, "connectedNodeId": 0, "bpConfig": {"bpNumber": 52, "bpName": "HF B"}},
        ]}
    return False, {"error": "x"}


def test_ranges_filter_import(auth_client, app, monkeypatch):
    auth_client.put("/api/settings", json={"bolero_enabled": True, "antenna_ranges": [[1, 25]]})
    monkeypatch.setattr(app.extensions["antenna"], "_request", _fake_three)
    auth_client.post("/api/antenna/connect", json={"ip": "1.1.1.1", "password": ""})
    applied = auth_client.post("/api/antenna/import/apply").get_json()
    assert applied["created"] == 2          # 5 et 7 ; 52 hors plage
    state = auth_client.get("/api/state").get_json()
    assert sorted(p["beltpack"] for p in state["people"]) == ["5", "7"]


def test_invalid_ranges_400(auth_client):
    r = auth_client.put("/api/settings", json={"antenna_ranges": [[25, 1]]})  # lo>hi
    assert r.status_code == 400


def test_apply_mirror_removes_absent(auth_client, app, monkeypatch):
    auth_client.put("/api/settings", json={"bolero_enabled": True})
    monkeypatch.setattr(app.extensions["antenna"], "_request", _fake_three)
    auth_client.post("/api/antenna/connect", json={"ip": "1.1.1.1", "password": ""})
    auth_client.post("/api/antenna/import/apply")
    # l'antenne ne renvoie plus que le BP 5 → 7 et 52 doivent disparaître
    def only5(method, path, body=None, timeout=5):
        if path == "/rest/bp":
            return True, {"bp": [{"registered": True, "id": 1, "connectedNodeId": 1, "bpConfig": {"bpNumber": 5, "bpName": "Régie"}}]}
        return _fake_three(method, path, body, timeout)
    monkeypatch.setattr(app.extensions["antenna"], "_request", only5)
    res = auth_client.post("/api/antenna/import/apply").get_json()
    assert res["removed"] == 2
    state = auth_client.get("/api/state").get_json()
    assert [p["beltpack"] for p in state["people"]] == ["5"]


def test_configs_save_load_disconnects(auth_client, app, monkeypatch):
    auth_client.put("/api/settings", json={"bolero_enabled": True})
    monkeypatch.setattr(app.extensions["antenna"], "_request", _fake_three)
    auth_client.post("/api/antenna/connect", json={"ip": "1.1.1.1", "password": ""})
    auth_client.post("/api/antenna/import/apply")
    auth_client.post("/api/configs", json={"name": "Base"})
    assert [c["name"] for c in auth_client.get("/api/configs").get_json()] == ["Base"]
    # charger déconnecte l'antenne
    r = auth_client.post("/api/configs/Base/load")
    assert r.status_code == 200
    assert app.extensions["antenna"].connected is False
```

Ajouter à `tests/test_api.py` :
```python
def test_delete_batch(auth_client):
    a = auth_client.post("/api/people", json={"name": "A", "role": "", "beltpack": "1"}).get_json()
    b = auth_client.post("/api/people", json={"name": "B", "role": "", "beltpack": "2"}).get_json()
    auth_client.post("/api/people", json={"name": "C", "role": "", "beltpack": "3"})
    r = auth_client.post("/api/people/delete-batch", json={"ids": [a["id"], b["id"]]})
    assert r.get_json() == {"deleted": 2}
    state = auth_client.get("/api/state").get_json()
    assert [p["beltpack"] for p in state["people"]] == ["3"]
```

- [ ] **Step 2: Lancer (échoue)** — `.venv/bin/pytest tests/test_antenna_api.py tests/test_api.py -q` → FAIL.

- [ ] **Step 3: Étendre `comroster/antenna.py`**

Ajouter le helper de validation et l'accès configs, en tête (après les autres `_xxx()`) :
```python
def _configs():
    return current_app.extensions["configs"]


def _valid_ranges(ranges):
    if not isinstance(ranges, list):
        return None
    out = []
    for r in ranges:
        if not (isinstance(r, (list, tuple)) and len(r) == 2):
            return None
        lo, hi = r
        if not (isinstance(lo, int) and isinstance(hi, int) and lo <= hi):
            return None
        out.append([lo, hi])
    return out
```
Remplacer `get_settings` et `put_settings` par :
```python
@bp.get("/api/settings")
@login_required
def get_settings():
    return jsonify({"bolero_enabled": _enabled(),
                    "antenna_ranges": _settings().get("antenna_ranges", [])})


@bp.put("/api/settings")
@login_required
def put_settings():
    data = request.get_json(force=True)
    if "bolero_enabled" in data:
        enabled = bool(data.get("bolero_enabled"))
        _settings().set("bolero_enabled", enabled)
        if not enabled:
            _client().disconnect()
    if "antenna_ranges" in data:
        ranges = _valid_ranges(data.get("antenna_ranges"))
        if ranges is None:
            return jsonify({"error": "Plages invalides"}), 400
        _settings().set("antenna_ranges", ranges)
    return jsonify({"bolero_enabled": _enabled(),
                    "antenna_ranges": _settings().get("antenna_ranges", [])})
```
Remplacer `antenna_import_preview` et `antenna_import_apply` par :
```python
@bp.post("/api/antenna/import/preview")
@login_required
def antenna_import_preview():
    guard = _guard()
    if guard:
        return guard
    try:
        items = _client().fetch_beltpacks()
    except AntennaError as exc:
        return jsonify({"error": str(exc)}), 502
    items = model.filter_by_ranges(items, _settings().get("antenna_ranges", []))
    return jsonify(model.diff_beltpacks(_storage().load_draft(), items))


@bp.post("/api/antenna/import/apply")
@login_required
def antenna_import_apply():
    guard = _guard()
    if guard:
        return guard
    try:
        items = _client().fetch_beltpacks()
    except AntennaError as exc:
        return jsonify({"error": str(exc)}), 502
    items = model.filter_by_ranges(items, _settings().get("antenna_ranges", []))
    state = _storage().load_draft()
    result = model.mirror_beltpacks(state, items)
    _storage().save_draft(state)
    return jsonify(result)
```
Ajouter les endpoints configs à la fin du fichier :
```python
@bp.get("/api/configs")
@login_required
def list_configs():
    return jsonify(_configs().list())


@bp.post("/api/configs")
@login_required
def save_config():
    data = request.get_json(force=True)
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Nom requis"}), 400
    _configs().save(name, _storage().load_draft())
    return jsonify({"ok": True})


@bp.post("/api/configs/<name>/load")
@login_required
def load_config(name):
    try:
        state = _configs().load(name)
    except KeyError:
        return jsonify({"error": "not_found"}), 404
    _storage().save_draft(state)
    _client().disconnect()      # charger une config déconnecte l'antenne
    return jsonify({"ok": True})


@bp.delete("/api/configs/<name>")
@login_required
def delete_config(name):
    try:
        _configs().delete(name)
    except KeyError:
        return jsonify({"error": "not_found"}), 404
    return jsonify({"ok": True})
```

- [ ] **Step 4: Ajouter `/api/people/delete-batch` dans `comroster/api.py`**

Après `delete_person` :
```python
@bp.post("/api/people/delete-batch")
@login_required
def delete_people_batch():
    data = request.get_json(force=True)
    ids = data.get("ids") or []
    state = _storage().load_draft()
    deleted = model.delete_people(state, ids)
    _storage().save_draft(state)
    return jsonify({"deleted": deleted})
```

- [ ] **Step 5: Instancier `Configs` dans la factory**

Dans `comroster/__init__.py`, après `app.extensions["antenna"] = ...` :
```python
    from .services.configs import Configs
    app.extensions["configs"] = Configs(app.extensions["storage"])
```

- [ ] **Step 6: Lancer (passe)**

Run: `.venv/bin/pytest tests/test_antenna_api.py tests/test_api.py -q` → PASS.

- [ ] **Step 7: Suite complète + commit**

```bash
.venv/bin/pytest -q
git add comroster/antenna.py comroster/api.py comroster/__init__.py tests/test_antenna_api.py tests/test_api.py
git commit -m "feat(bolero): sync miroir + plages, endpoints configs, delete-batch"
```

---

## Task 4: UI — plages, récap « à retirer », configs, mode sélection

**Files:**
- Modify: `templates/admin.html`, `static/js/admin.js`, `static/css/admin.css`
- Test: `tests/test_ui.py` (ajout), vérification manuelle

**Interfaces:**
- Consomme l'API des Tasks 3. Réutilise les helpers de `admin.js` : `apiSend`, `toast`, `esc`, `load`, `setUnpublished`, `render`, `personCard`, `state`.

- [ ] **Step 1: HTML — éditeur de plages + bouton Actualiser dans le bloc antenne connecté**

Dans `templates/admin.html`, à l'intérieur de `#antenna-block`, juste après `<hr class="dlg-sep">`, insérer l'éditeur de plages :
```html
        <div class="ranges-editor">
          <span class="dlg-label">Plages de beltpacks à charger (vide = toutes)</span>
          <div id="ranges-list"></div>
          <button type="button" id="add-range-btn">+ Plage</button>
        </div>
        <hr class="dlg-sep">
```
Dans `#antenna-connected`, ajouter le bouton Actualiser avant le bouton Déconnecter :
```html
          <div class="dialog-actions" style="justify-content:flex-start">
            <button type="button" id="antenna-refresh-btn" class="primary">Actualiser depuis l'antenne</button>
            <button type="button" id="antenna-disconnect-btn">Déconnecter</button>
          </div>
```
> Remplace le bloc `dialog-actions` existant de `#antenna-connected` (qui contenait `antenna-import-btn`). L'ancien `antenna-import-btn` disparaît au profit de `antenna-refresh-btn`.

- [ ] **Step 2: HTML — ligne « à retirer » dans le récap, bouton Configs, dialog Configs, barre de sélection**

Le dialog `#import-dialog` reste ; son contenu est rempli par le JS (incluant la ligne « à retirer »).

Dans la toolbar, groupe *Données*, après le label Importer :
```html
        <button type="button" id="configs-btn">Configs</button>
```
Dans le groupe *Édition*, après `+ Personne` :
```html
        <button type="button" id="select-btn">Sélectionner</button>
```
Avant `<footer>`, ajouter le dialog Configs et la barre de sélection :
```html
  <dialog id="configs-dialog" class="admin-dialog">
    <form method="dialog">
      <h2>Configurations</h2>
      <div class="save-row">
        <input type="text" id="config-name" placeholder="Nom (ex. Jour 2)" maxlength="60">
        <button type="button" id="config-save-btn" class="primary">Sauvegarder</button>
      </div>
      <ul id="configs-list" class="configs-list"></ul>
      <div class="dialog-actions"><button type="button" data-close="configs-dialog">Fermer</button></div>
    </form>
  </dialog>

  <div id="selection-bar" class="selection-bar" hidden>
    <span id="selection-count">0 sélectionné(s)</span>
    <button type="button" id="selection-delete" class="danger-btn">Supprimer</button>
    <button type="button" id="selection-cancel">Annuler</button>
  </div>
```

- [ ] **Step 3: CSS**

Ajouter à la fin de `static/css/admin.css` :
```css
/* ---------- Éditeur de plages ---------- */
.ranges-editor { display: flex; flex-direction: column; gap: 0.4rem; }
.dlg-label { font-size: 0.82rem; font-weight: 600; color: #aab6cc; }
.range-row { display: flex; align-items: center; gap: 0.4rem; }
.range-row input { width: 5rem; }
.range-row .range-del { color: #ff8d8d; border-color: #50313a; }

/* ---------- Configurations ---------- */
.save-row { display: flex; gap: 0.5rem; }
.save-row input { flex: 1; }
.configs-list { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 0.4rem; max-height: 50vh; overflow-y: auto; }
.configs-list li { display: flex; justify-content: space-between; align-items: center; gap: 0.6rem; padding: 0.5rem 0.6rem; background: #0c111d; border: 1px solid #243049; border-radius: 7px; font-size: 0.85rem; }
.configs-list .cfg-actions { display: flex; gap: 0.35rem; }

/* ---------- Mode sélection ---------- */
.person.selectable { cursor: pointer; }
.person.selected { border-color: var(--primary); background: #14304a; }
.person .sel-check { margin-right: 0.2rem; }
.selection-bar { position: fixed; bottom: 4.2rem; left: 50%; transform: translateX(-50%); display: flex; align-items: center; gap: 0.8rem; padding: 0.5rem 0.9rem; background: #131a2a; border: 1px solid #3a4868; border-radius: 9px; box-shadow: 0 8px 24px rgba(0,0,0,.5); z-index: 60; }
.selection-bar .danger-btn { background: var(--error); color: #fff; border: none; border-radius: 7px; padding: 0.35rem 0.7rem; cursor: pointer; }
```

- [ ] **Step 4: JS — mode sélection (modifier `personCard` et `render`)**

Dans `static/js/admin.js`, ajouter au `state` initial les champs sélection (dans l'objet `state = {…}`) :
```javascript
    selectionMode: false,
    selection: new Set(),
```
Dans `personCard`, au tout début (après `card.dataset…`), gérer le mode sélection :
```javascript
    if (state.selectionMode) {
      card.classList.add("selectable");
      card.draggable = false;
      if (state.selection.has(person.id)) card.classList.add("selected");
      const chk = document.createElement("input");
      chk.type = "checkbox";
      chk.className = "sel-check";
      chk.checked = state.selection.has(person.id);
      card.prepend(chk);
      card.addEventListener("click", (e) => {
        e.preventDefault();
        if (state.selection.has(person.id)) state.selection.delete(person.id);
        else state.selection.add(person.id);
        updateSelectionBar();
        render();
      });
      return card;   // pas de drag/contextmenu/dblclick en mode sélection
    }
```

- [ ] **Step 5: JS — barre de sélection, plages, configs, connexion→preview**

Ajouter dans `admin.js`, juste avant le bloc `/* ---------- Init ---------- */` (à la suite du code Bolero existant) :
```javascript
  /* ---------- Mode sélection ---------- */
  function updateSelectionBar() {
    const bar = document.getElementById("selection-bar");
    document.getElementById("selection-count").textContent = `${state.selection.size} sélectionné(s)`;
    bar.hidden = !state.selectionMode;
  }
  document.getElementById("select-btn").addEventListener("click", () => {
    state.selectionMode = !state.selectionMode;
    state.selection.clear();
    document.getElementById("select-btn").textContent = state.selectionMode ? "Quitter la sélection" : "Sélectionner";
    updateSelectionBar();
    render();
  });
  document.getElementById("selection-cancel").addEventListener("click", () => {
    state.selectionMode = false; state.selection.clear();
    document.getElementById("select-btn").textContent = "Sélectionner";
    updateSelectionBar(); render();
  });
  document.getElementById("selection-delete").addEventListener("click", async () => {
    if (!state.selection.size) return;
    if (!confirm(`Supprimer ${state.selection.size} fiche(s) ?`)) return;
    const ids = [...state.selection];
    try {
      const res = await apiSend("POST", "/api/people/delete-batch", { ids });
      state.selectionMode = false; state.selection.clear();
      document.getElementById("select-btn").textContent = "Sélectionner";
      setUnpublished(true);
      await load();
      updateSelectionBar();
      toast(`${res.deleted} fiche(s) supprimée(s)`);
    } catch { toast("Suppression impossible", true); }
  });

  /* ---------- Éditeur de plages ---------- */
  let currentRanges = [];
  function renderRanges() {
    const list = document.getElementById("ranges-list");
    list.innerHTML = "";
    currentRanges.forEach((r, i) => {
      const row = document.createElement("div");
      row.className = "range-row";
      row.innerHTML = `de <input type="number" min="1" value="${r[0]}" data-i="${i}" data-k="0"> à `
        + `<input type="number" min="1" value="${r[1]}" data-i="${i}" data-k="1">`;
      const del = document.createElement("button");
      del.type = "button"; del.className = "range-del"; del.textContent = "✕";
      del.addEventListener("click", () => { currentRanges.splice(i, 1); renderRanges(); saveRanges(); });
      row.appendChild(del);
      list.appendChild(row);
    });
    list.querySelectorAll("input").forEach((inp) => inp.addEventListener("change", () => {
      currentRanges[+inp.dataset.i][+inp.dataset.k] = parseInt(inp.value || "0", 10);
      saveRanges();
    }));
  }
  async function saveRanges() {
    const clean = currentRanges
      .map((r) => [parseInt(r[0] || 0, 10), parseInt(r[1] || 0, 10)])
      .filter((r) => r[0] >= 1 && r[1] >= r[0]);
    try { await apiSend("PUT", "/api/settings", { antenna_ranges: clean }); }
    catch { toast("Plages invalides", true); }
  }
  document.getElementById("add-range-btn").addEventListener("click", () => {
    currentRanges.push([1, 25]); renderRanges(); saveRanges();
  });

  /* ---------- Connexion → récap, Actualiser ---------- */
  async function openImportPreview() {
    let p;
    try { p = await apiSend("POST", "/api/antenna/import/preview"); }
    catch { toast("Lecture des beltpacks impossible", true); return; }
    const li = [];
    li.push(`<li><b>${p.new.length}</b> à ajouter${p.new.length ? " : " + p.new.map((n) => esc(`#${n.number} ${n.name}`)).join(", ") : ""}</li>`);
    li.push(`<li><b>${p.changed.length}</b> rôle(s) mis à jour${p.changed.length ? " : " + p.changed.map((c) => esc(`#${c.number} ${c.old_role}→${c.new_role}`)).join(", ") : ""}</li>`);
    li.push(`<li><b>${p.unchanged}</b> inchangé(s)</li>`);
    li.push(`<li><b>${p.missing.length}</b> à retirer${p.missing.length ? " : " + p.missing.map((m) => esc(`#${m.number} ${m.role}`)).join(", ") : ""}</li>`);
    document.getElementById("import-summary").innerHTML = li.join("");
    document.getElementById("import-dialog").showModal();
  }
  document.getElementById("antenna-refresh-btn").addEventListener("click", openImportPreview);

  /* ---------- Configurations ---------- */
  async function openConfigs() {
    const items = await apiSend("GET", "/api/configs");
    const ul = document.getElementById("configs-list");
    ul.innerHTML = items.length
      ? items.map((c) => `<li><span>${esc(c.name)}</span><span class="cfg-actions">`
          + `<button type="button" data-load="${esc(c.name)}">Charger</button>`
          + `<button type="button" data-del="${esc(c.name)}" class="chip-btn danger">Supprimer</button></span></li>`).join("")
      : "<li class='empty-hint'>Aucune configuration enregistrée.</li>";
    ul.querySelectorAll("[data-load]").forEach((b) => b.addEventListener("click", async () => {
      if (!confirm(`Charger « ${b.dataset.load} » ? Le tableau actuel sera remplacé et l'antenne déconnectée.`)) return;
      await apiSend("POST", `/api/configs/${encodeURIComponent(b.dataset.load)}/load`);
      document.getElementById("configs-dialog").close();
      setUnpublished(true);
      await load();
      toast("Configuration chargée");
    }));
    ul.querySelectorAll("[data-del]").forEach((b) => b.addEventListener("click", async () => {
      if (!confirm(`Supprimer « ${b.dataset.del} » ?`)) return;
      await apiSend("DELETE", `/api/configs/${encodeURIComponent(b.dataset.del)}`);
      openConfigs();
    }));
    document.getElementById("configs-dialog").showModal();
  }
  document.getElementById("configs-btn").addEventListener("click", openConfigs);
  document.getElementById("config-save-btn").addEventListener("click", async () => {
    const name = document.getElementById("config-name").value.trim();
    if (!name) return;
    await apiSend("POST", "/api/configs", { name });
    document.getElementById("config-name").value = "";
    openConfigs();
    toast("Configuration sauvegardée");
  });
```

- [ ] **Step 6: JS — charger les plages à l'ouverture des réglages + connexion enchaîne le récap**

Dans `openSettings` (existant), après `if (s.bolero_enabled) await refreshAntenna();`, ajouter le chargement des plages :
```javascript
    currentRanges = (s.antenna_ranges || []).map((r) => [r[0], r[1]]);
    renderRanges();
```
> `GET /api/settings` renvoie désormais `antenna_ranges` (Task 3).

Dans le handler `antenna-connect-btn` (existant), après `await refreshAntenna();` en cas de succès, enchaîner le récap :
```javascript
      await refreshAntenna();
      await openImportPreview();
```
> Retirer l'ancien handler `antenna-import-btn` (le bouton n'existe plus ; `openImportPreview` le remplace).

- [ ] **Step 7: Test de rendu**

Ajouter à `tests/test_ui.py` :
```python
def test_admin_has_configs_and_selection(auth_client):
    html = auth_client.get("/admin").get_data(as_text=True)
    assert "configs-dialog" in html
    assert 'id="configs-btn"' in html
    assert 'id="select-btn"' in html
    assert "ranges-list" in html
    assert "selection-bar" in html
```
Run: `.venv/bin/pytest tests/test_ui.py -q` → PASS.

- [ ] **Step 8: Vérification manuelle (faux serveur antenne)**

`./run-dev.sh`, puis dans `/admin` :
- ⚙ Réglages → activer Bolero → ajouter une plage (ex. 1–25) → Connecter (IP du faux serveur) → le **récap** s'ouvre (à ajouter / à retirer) → Appliquer → les fiches apparaissent (seulement la plage).
- « Actualiser depuis l'antenne » → récap de nouveau.
- Toolbar « Configs » → Sauvegarder « Base » → Charger (confirme, déconnecte l'antenne).
- Toolbar « Sélectionner » → cocher des fiches → barre « Supprimer (N) » → supprimer.

- [ ] **Step 9: Commit**

```bash
git add templates/admin.html static/js/admin.js static/css/admin.css tests/test_ui.py
git commit -m "feat(bolero): UI — éditeur de plages, récap miroir, configs nommées, sélection multiple"
```

---

## Self-review (couverture du spec)

- Un seul brouillon (pas de swap) → architecture conservée, aucune route CRUD modifiée sauf ajout `delete-batch`. ✓
- Sync miroir (retire les absents) → Task 1 (`mirror_beltpacks`) + Task 3 (`import/apply`). ✓
- Récap avant application, incl. 1ère connexion → Task 4 (connexion enchaîne `openImportPreview`) + ligne « à retirer ». ✓
- Plages `antenna_ranges` (intervalles, validation, filtre avant miroir) → Task 1 (`filter_by_ranges`) + Task 3 (settings + preview/apply) + Task 4 (éditeur). ✓
- Configs nommées (save/list/load/delete ; load déconnecte) → Task 2 (`Configs`) + Task 3 (endpoints) + Task 4 (dialog). ✓
- Suppression multiple → Task 1 (`delete_people`) + Task 3 (endpoint) + Task 4 (mode sélection). ✓
- Garde flag sur `/api/antenna/*` uniquement ; configs/delete-batch non gardés → Task 3. ✓
- `configs/` gitignored → Task 2. ✓

**Cohérence vérifiée :** `mirror_beltpacks` renvoie `{created,updated,removed}` (Task 1 = Task 3 tests = UI) ; `filter_by_ranges(items, ranges)` signature identique ; `Configs.load` renvoie le `state` (pas l'enveloppe) ; helpers JS (`apiSend`, `personCard`, `render`, `state`, `setUnpublished`) déjà présents depuis la première intégration.


