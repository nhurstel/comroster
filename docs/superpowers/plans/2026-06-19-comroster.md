# ComRoster Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construire ComRoster, une app web Flask qui sépare une admin (édition d'un brouillon d'affectation de beltpacks intercom) d'un affichage TV temps réel (état publié, diffusé par SSE).

**Architecture:** Application factory + blueprints (`auth`, `api`, `display`) + services (`storage`, `model`, `pubsub`, `history`). Deux fichiers d'état JSON (brouillon / publié), écriture atomique sous lock. L'admin n'écrit que le brouillon ; « Publier » copie le brouillon vers le publié, archive un snapshot, et diffuse l'état complet à tous les clients SSE. Le display reçoit un `snapshot` complet à chaque (re)connexion → la reconnexion est résolue par construction.

**Tech Stack:** Python 3.12, Flask, Flask-WTF (CSRF), Flask-Limiter (anti-bruteforce login), Werkzeug (hashing), pytest (tests), JS vanilla + SortableJS (drag-and-drop admin) + EventSource (display).

## Global Constraints

- **Python 3.12** ; backend Flask uniquement.
- **Dépendances runtime** : `Flask`, `Flask-WTF`, `Flask-Limiter`. Dev : `pytest`. Pas de SGBD, pas d'ORM, pas de framework JS.
- **Persistance fichiers plats** : `data_draft.json`, `data_published.json`, `admin_secret.json`, `history/`. Tous **gitignored** dès P0.
- **Écriture atomique imposée** : sérialiser → fichier temporaire dans le même répertoire → `flush()` + `os.fsync()` → `os.replace(tmp, cible)`, le tout sous un `threading.Lock` global de process.
- **IDs = UUID4** (str), générés serveur.
- **Unicité beltpack = blocage dur** : validée serveur dans `model.py` ; conflit ⇒ **409**, aucune écriture. Beltpack comparé en chaîne normalisée (strip). Beltpack vide interdit.
- **Suppression de groupe** ⇒ ses membres repassent `group_id = null` (pool), jamais supprimés.
- **Concurrence** : last-write-wins, pas de verrou logique.
- **Un seul worker en prod** (broker SSE en mémoire) : `gunicorn --workers 1 --threads 8 --worker-class gthread`.
- **Schéma d'état** : `{ "version": 1, "updated_at": <ISO8601 UTC>, "groups": [...], "people": [...], "beltpack_roles": {<n°>: <role>} }`. Groupe : `{id,name,color,order}`. Personne : `{id,name,role,beltpack,group_id}`.
- **Rôle lié au beltpack** : le rôle (« Régie », « Lumière »…) caractérise le **numéro de beltpack**, pas la personne. La map `beltpack_roles` (n° normalisé → rôle) mémorise la correspondance : à la saisie, si le rôle est absent il est hérité de la map ; toute saisie de rôle met la map à jour. Pré-remplissage UI à partir de cette map.
- **SSE** : en-têtes `text/event-stream`, `Cache-Control: no-cache`, `X-Accel-Buffering: no` ; `retry: 3000` + event `snapshot` à la connexion ; event `published` à chaque publication ; heartbeat `: keepalive` ~15 s.
- **Sécurité** : `FLASK_SECRET_KEY` obligatoire en prod (refus de démarrer sinon) ; cookie `HttpOnly`, `SameSite=Lax`, `Secure` ; CSRF sur toute requête mutative ; `/display` et `/events` n'exposent **que** l'état publié.
- **TDD** sur le backend critique (`storage`, `model`, `publish`, `pubsub`). Commits atomiques.

---

## File Structure

| Fichier | Responsabilité |
|---------|----------------|
| `app.py` | Point d'entrée : `from comroster import create_app; app = create_app()` |
| `comroster/__init__.py` | `create_app()` : config, extensions (CSRF, Limiter), enregistrement blueprints, garde prod |
| `comroster/config.py` | Lecture des variables d'environnement → objet config |
| `comroster/security.py` | `login_required`, init CSRF/Limiter, helper session |
| `comroster/auth.py` | Blueprint : setup, login, logout, recover |
| `comroster/api.py` | Blueprint : `/api/state`, CRUD groups/people, publish, history, import/export |
| `comroster/display.py` | Blueprint : `/display` (page), `/events` (SSE) |
| `comroster/services/storage.py` | Lecture/écriture atomique des fichiers d'état + lock |
| `comroster/services/model.py` | Schéma, normalisation, validation (unicité beltpack, intégrité group_id), mutations pures |
| `comroster/services/pubsub.py` | Broker SSE en mémoire (files par client) |
| `comroster/services/history.py` | Snapshots horodatés : archive, list, restore |
| `comroster/services/secret.py` | Lecture/écriture/hash du secret admin + code de récup |
| `templates/{setup,login,admin,display}.html` | Vues |
| `static/css/main.css` | Styles (glassmorphism display, admin) |
| `static/js/{admin.js,display.js}` | Logique front |
| `static/vendor/sortable.min.js` | SortableJS vendored |
| `tests/` | pytest |

---

## Phase 0 — Socle

### Task 0: Bootstrap du projet & application factory

**Files:**
- Create: `requirements.txt`, `.gitignore`, `app.py`, `comroster/__init__.py`, `comroster/config.py`
- Test: `tests/test_app.py`, `tests/conftest.py`

**Interfaces:**
- Produces: `create_app(config_overrides: dict | None = None) -> Flask`. Route santé `GET /healthz` → `{"status":"ok"}`. `Config` lit `FLASK_SECRET_KEY`, `DATA_DIR`, `PORT`, `FLASK_DEBUG` depuis l'env.

- [ ] **Step 1: Écrire requirements.txt et .gitignore**

`requirements.txt` :
```
Flask>=3.0
Flask-WTF>=1.2
Flask-Limiter>=3.5
```
`.gitignore` :
```
__pycache__/
*.pyc
.venv/
venv/
.pytest_cache/
data_draft.json
data_published.json
admin_secret.json
history/
instance/
```

- [ ] **Step 2: Créer le venv et installer**

Run: `python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt pytest`
Expected: installation sans erreur.

- [ ] **Step 3: Écrire le test de la factory (échoue)**

`tests/conftest.py` :
```python
import pytest
from comroster import create_app


@pytest.fixture
def app(tmp_path):
    app = create_app({"TESTING": True, "DATA_DIR": str(tmp_path), "SECRET_KEY": "test-secret"})
    return app


@pytest.fixture
def client(app):
    return app.test_client()
```
`tests/test_app.py` :
```python
def test_healthz(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok"}
```

- [ ] **Step 4: Lancer le test (échoue)**

Run: `.venv/bin/pytest tests/test_app.py -v`
Expected: FAIL (ImportError : `create_app` introuvable).

- [ ] **Step 5: Écrire config.py**

`comroster/config.py` :
```python
import os


class Config:
    def __init__(self, overrides=None):
        self.SECRET_KEY = os.environ.get("FLASK_SECRET_KEY")
        self.DATA_DIR = os.environ.get("DATA_DIR", os.getcwd())
        self.PORT = int(os.environ.get("PORT", "8080"))
        self.DEBUG = os.environ.get("FLASK_DEBUG", "").lower() in ("1", "true", "yes")
        self.TESTING = False
        if overrides:
            for key, value in overrides.items():
                setattr(self, key, value)

    def as_dict(self):
        return {k: v for k, v in self.__dict__.items()}
```

- [ ] **Step 6: Écrire la factory**

`comroster/__init__.py` :
```python
from flask import Flask, jsonify

from .config import Config


def create_app(config_overrides=None):
    app = Flask(__name__)
    config = Config(config_overrides)
    app.config.from_mapping(config.as_dict())

    if not app.config.get("TESTING") and not app.config.get("DEBUG"):
        if not app.config.get("SECRET_KEY"):
            raise RuntimeError("FLASK_SECRET_KEY est obligatoire en production")
    if not app.config.get("SECRET_KEY"):
        app.config["SECRET_KEY"] = "dev-insecure-key"

    @app.get("/healthz")
    def healthz():
        return jsonify({"status": "ok"})

    return app
```
`app.py` :
```python
from comroster import create_app

app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=app.config["PORT"], debug=app.config["DEBUG"])
```

- [ ] **Step 7: Lancer le test (passe)**

Run: `.venv/bin/pytest tests/test_app.py -v`
Expected: PASS.

- [ ] **Step 8: Vérifier la garde prod**

Run: `.venv/bin/python -c "import os; os.environ.clear(); from comroster import create_app; create_app()"`
Expected: démarre (pas de SECRET_KEY mais pas en prod → clé dev). Test additionnel :
```python
def test_prod_requires_secret_key():
    import pytest
    from comroster import create_app
    with pytest.raises(RuntimeError):
        create_app({"TESTING": False, "DEBUG": False, "SECRET_KEY": None})
```
Ajouter à `tests/test_app.py`, relancer `pytest`, attendu PASS.

- [ ] **Step 9: Commit**

```bash
git init && git add -A && git commit -m "feat(p0): application factory, config env, route santé"
```

---

## Phase 1 — Données & validation (TDD strict)

### Task 1: Schéma, normalisation et validation (`model.py`)

**Files:**
- Create: `comroster/services/__init__.py`, `comroster/services/model.py`
- Test: `tests/test_model.py`

**Interfaces:**
- Produces :
  - `empty_state() -> dict` → `{"version":1,"updated_at":<iso>,"groups":[],"people":[]}`
  - `new_id() -> str` (UUID4)
  - `normalize_beltpack(value) -> str` (strip)
  - `ValidationError(Exception)` avec attribut `.code` (str) et message.
  - `validate_state(state: dict) -> None` (lève `ValidationError` si beltpack dupliqué/vide ou group_id orphelin).
  - `add_group(state, name, color, order=None) -> dict` (retourne le groupe créé, mute state).
  - `update_group(state, group_id, **fields) -> dict`
  - `delete_group(state, group_id) -> None` (membres → group_id=None).
  - `add_person(state, name, role, beltpack, group_id=None) -> dict` (rôle hérité de `beltpack_roles` si vide)
  - `update_person(state, person_id, **fields) -> dict`
  - `delete_person(state, person_id) -> None`
  - `role_for_beltpack(state, beltpack) -> str | None` (rôle mémorisé pour ce n°)
  - `touch(state) -> None` (met `updated_at` à maintenant UTC ISO).
  Toutes les mutations valident l'unicité beltpack et lèvent `ValidationError(code="beltpack_conflict")` ou `code="not_found"`.

- [ ] **Step 1: Écrire les tests (échouent)**

`tests/test_model.py` :
```python
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
```

- [ ] **Step 2: Lancer (échoue)**

Run: `.venv/bin/pytest tests/test_model.py -v`
Expected: FAIL (module `model` incomplet).

- [ ] **Step 3: Implémenter model.py**

`comroster/services/__init__.py` : (vide)
`comroster/services/model.py` :
```python
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


def empty_state():
    return {"version": 1, "updated_at": now_iso(), "groups": [], "people": []}


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


def add_person(state, name, role, beltpack, group_id=None):
    _assert_beltpack_free(state, beltpack)
    if group_id is not None and _find(state["groups"], group_id) is None:
        raise ValidationError("Groupe cible introuvable", code="not_found")
    person = {
        "id": new_id(),
        "name": name,
        "role": role,
        "beltpack": normalize_beltpack(beltpack),
        "group_id": group_id,
    }
    state["people"].append(person)
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
    for key in ("name", "role"):
        if key in fields and fields[key] is not None:
            person[key] = fields[key]
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
```

- [ ] **Step 4: Lancer (passe)**

Run: `.venv/bin/pytest tests/test_model.py -v`
Expected: PASS (tous).

- [ ] **Step 5: Commit**

```bash
git add comroster/services tests/test_model.py && git commit -m "feat(p1): model — schéma, mutations, unicité beltpack, validation"
```

### Task 2: Écriture atomique sous lock (`storage.py`)

**Files:**
- Create: `comroster/services/storage.py`
- Test: `tests/test_storage.py`

**Interfaces:**
- Consumes: `model.empty_state`.
- Produces:
  - `Storage(data_dir: str)` avec attributs de chemins.
  - `.load_draft() -> dict` (crée un état vide si absent).
  - `.save_draft(state: dict) -> None` (atomique).
  - `.load_published() -> dict | None` (None si jamais publié).
  - `.save_published(state: dict) -> None` (atomique).
  - `.atomic_write(path: str, data: dict) -> None` (tmp + fsync + os.replace, sous lock).

- [ ] **Step 1: Écrire les tests (échouent)**

`tests/test_storage.py` :
```python
import json
import os
from comroster.services.storage import Storage
from comroster.services import model


def test_save_and_load_draft(tmp_path):
    st = Storage(str(tmp_path))
    state = model.empty_state()
    model.add_person(state, "Jean", "HF", "12")
    st.save_draft(state)
    loaded = st.load_draft()
    assert loaded["people"][0]["name"] == "Jean"


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
    # pas de fichier temporaire résiduel
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
```

- [ ] **Step 2: Lancer (échoue)**

Run: `.venv/bin/pytest tests/test_storage.py -v`
Expected: FAIL (module absent).

- [ ] **Step 3: Implémenter storage.py**

```python
import json
import os
import threading

from . import model

_WRITE_LOCK = threading.Lock()


class Storage:
    def __init__(self, data_dir):
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
        self.draft_path = os.path.join(data_dir, "data_draft.json")
        self.published_path = os.path.join(data_dir, "data_published.json")
        self.history_dir = os.path.join(data_dir, "history")

    def atomic_write(self, path, data):
        payload = json.dumps(data, ensure_ascii=False, indent=2)
        directory = os.path.dirname(path) or "."
        with _WRITE_LOCK:
            fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    fh.write(payload)
                    fh.flush()
                    os.fsync(fh.fileno())
                os.replace(tmp, path)
            except BaseException:
                if os.path.exists(tmp):
                    os.unlink(tmp)
                raise

    def _load(self, path):
        if not os.path.exists(path):
            return None
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)

    def load_draft(self):
        state = self._load(self.draft_path)
        return state if state is not None else model.empty_state()

    def save_draft(self, state):
        self.atomic_write(self.draft_path, state)

    def load_published(self):
        return self._load(self.published_path)

    def save_published(self, state):
        self.atomic_write(self.published_path, state)
```
Ajouter en tête : `import tempfile`.

- [ ] **Step 4: Lancer (passe)**

Run: `.venv/bin/pytest tests/test_storage.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add comroster/services/storage.py tests/test_storage.py && git commit -m "feat(p1): storage — écriture atomique sous lock, draft/published"
```

---

## Phase 2 — Auth & sécurité

### Task 3: Service secret admin (`secret.py`)

**Files:**
- Create: `comroster/services/secret.py`
- Test: `tests/test_secret.py`

**Interfaces:**
- Consumes: `Storage` (réutilise `atomic_write`), `werkzeug.security`.
- Produces:
  - `SecretStore(data_dir)` ; `.secret_path`.
  - `.is_configured() -> bool`
  - `.setup(password) -> str` (hash le mot de passe, génère + retourne un **code de récupération en clair une seule fois**, stocke son hash, écrit `admin_secret.json` permissions 600). Lève `RuntimeError` si déjà configuré.
  - `.verify_password(password) -> bool`
  - `.recover(recovery_code, new_password) -> str` (vérifie le code, régénère mot de passe + nouveau code, retourne le nouveau code). Lève `ValueError` si code invalide.

- [ ] **Step 1: Tests (échouent)**

`tests/test_secret.py` :
```python
import os
import pytest
from comroster.services.secret import SecretStore


def test_setup_and_verify(tmp_path):
    s = SecretStore(str(tmp_path))
    assert not s.is_configured()
    code = s.setup("motdepasse8")
    assert s.is_configured()
    assert isinstance(code, str) and len(code) >= 8
    assert s.verify_password("motdepasse8")
    assert not s.verify_password("mauvais")


def test_setup_twice_refused(tmp_path):
    s = SecretStore(str(tmp_path))
    s.setup("motdepasse8")
    with pytest.raises(RuntimeError):
        s.setup("autre1234")


def test_recover_resets_password(tmp_path):
    s = SecretStore(str(tmp_path))
    code = s.setup("motdepasse8")
    new_code = s.recover(code, "nouveaupass1")
    assert s.verify_password("nouveaupass1")
    assert not s.verify_password("motdepasse8")
    assert new_code != code


def test_recover_wrong_code(tmp_path):
    s = SecretStore(str(tmp_path))
    s.setup("motdepasse8")
    with pytest.raises(ValueError):
        s.recover("mauvais-code", "nouveaupass1")


def test_secret_file_permissions(tmp_path):
    s = SecretStore(str(tmp_path))
    s.setup("motdepasse8")
    mode = os.stat(s.secret_path).st_mode & 0o777
    assert mode == 0o600
```

- [ ] **Step 2: Lancer (échoue)** — Run: `.venv/bin/pytest tests/test_secret.py -v` → FAIL.

- [ ] **Step 3: Implémenter secret.py**

```python
import json
import os
import secrets

from werkzeug.security import generate_password_hash, check_password_hash


def _gen_recovery_code():
    # 4 groupes de 4 caractères base32-ish, lisibles
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "-".join(
        "".join(secrets.choice(alphabet) for _ in range(4)) for _ in range(4)
    )


class SecretStore:
    def __init__(self, data_dir):
        os.makedirs(data_dir, exist_ok=True)
        self.secret_path = os.path.join(data_dir, "admin_secret.json")

    def is_configured(self):
        return os.path.exists(self.secret_path)

    def _write(self, data):
        payload = json.dumps(data, ensure_ascii=False, indent=2)
        fd = os.open(self.secret_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(payload)
        os.chmod(self.secret_path, 0o600)

    def _read(self):
        with open(self.secret_path, encoding="utf-8") as fh:
            return json.load(fh)

    def setup(self, password):
        if self.is_configured():
            raise RuntimeError("Admin déjà configuré")
        code = _gen_recovery_code()
        self._write({
            "password_hash": generate_password_hash(password),
            "recovery_hash": generate_password_hash(code),
        })
        return code

    def verify_password(self, password):
        if not self.is_configured():
            return False
        return check_password_hash(self._read()["password_hash"], password)

    def recover(self, recovery_code, new_password):
        if not self.is_configured():
            raise ValueError("Non configuré")
        data = self._read()
        if not check_password_hash(data["recovery_hash"], recovery_code):
            raise ValueError("Code de récupération invalide")
        new_code = _gen_recovery_code()
        self._write({
            "password_hash": generate_password_hash(new_password),
            "recovery_hash": generate_password_hash(new_code),
        })
        return new_code
```

- [ ] **Step 4: Lancer (passe)** — `.venv/bin/pytest tests/test_secret.py -v` → PASS.

- [ ] **Step 5: Commit**

```bash
git add comroster/services/secret.py tests/test_secret.py && git commit -m "feat(p2): secret store — hash mot de passe + code de récupération, perms 600"
```

### Task 4: Sécurité (CSRF, Limiter, login_required) + blueprint auth

**Files:**
- Create: `comroster/security.py`, `comroster/auth.py`
- Modify: `comroster/__init__.py` (init extensions, enregistrer blueprint, instancier `Storage`/`SecretStore` sur `app.extensions`)
- Create: `templates/setup.html`, `templates/login.html`
- Test: `tests/test_auth.py`

**Interfaces:**
- Consumes: `SecretStore`.
- Produces:
  - `comroster/security.py` : `csrf = CSRFProtect()`, `limiter = Limiter(...)`, décorateur `login_required(view)` (401 JSON ou redirect login selon Accept), helpers `current_is_authenticated()`, `log_in()`, `log_out()`.
  - `auth` blueprint : `GET/POST /admin/setup`, `GET/POST /admin/login`, `POST /admin/logout`, `POST /admin/recover`.
  - `app.extensions["storage"]`, `app.extensions["secret"]`.

- [ ] **Step 1: Tests (échouent)**

`tests/test_auth.py` :
```python
def test_setup_required_first(client):
    resp = client.get("/admin/login")
    # redirige vers setup tant que non configuré
    assert resp.status_code in (302, 303)
    assert "/admin/setup" in resp.headers["Location"]


def test_setup_creates_admin(client):
    resp = client.post("/admin/setup", data={"password": "motdepasse8"})
    assert resp.status_code in (200, 201, 302)
    # 2e setup interdit
    resp2 = client.post("/admin/setup", data={"password": "autre1234"})
    assert resp2.status_code in (409, 302)


def test_login_logout_flow(client):
    client.post("/admin/setup", data={"password": "motdepasse8"})
    bad = client.post("/admin/login", data={"password": "faux"})
    assert bad.status_code in (401, 200)  # 200 + message si form re-render
    ok = client.post("/admin/login", data={"password": "motdepasse8"})
    assert ok.status_code in (302, 200)
    protected = client.get("/api/state")
    assert protected.status_code == 200
    client.post("/admin/logout")
    after = client.get("/api/state")
    assert after.status_code in (401, 302)


def test_protected_route_without_login(client):
    client.post("/admin/setup", data={"password": "motdepasse8"})
    resp = client.get("/api/state")
    assert resp.status_code in (401, 302)
```
> Note : ces tests supposent CSRF désactivé en `TESTING` (`WTF_CSRF_ENABLED=False`) et un endpoint `/api/state` minimal (ajouté en P3, mais on stub un `/api/state` protégé ici pour valider la garde — il sera étoffé en P3).

- [ ] **Step 2: Lancer (échoue)** — FAIL.

- [ ] **Step 3: Implémenter security.py**

```python
from functools import wraps

from flask import session, redirect, url_for, jsonify, request
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

csrf = CSRFProtect()
limiter = Limiter(key_func=get_remote_address, default_limits=[])


def log_in():
    session["authenticated"] = True


def log_out():
    session.pop("authenticated", None)


def current_is_authenticated():
    return bool(session.get("authenticated"))


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_is_authenticated():
            if request.path.startswith("/api/") or request.accept_mimetypes.best == "application/json":
                return jsonify({"error": "unauthorized"}), 401
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)
    return wrapped
```

- [ ] **Step 4: Implémenter auth.py**

```python
from flask import (
    Blueprint, request, session, redirect, url_for,
    render_template, current_app, flash, jsonify,
)

from .security import limiter, log_in, log_out

bp = Blueprint("auth", __name__)


def _secret():
    return current_app.extensions["secret"]


@bp.route("/admin/setup", methods=["GET", "POST"])
def setup():
    secret = _secret()
    if secret.is_configured():
        if request.method == "POST":
            return jsonify({"error": "already_configured"}), 409
        return redirect(url_for("auth.login"))
    if request.method == "POST":
        password = request.form.get("password", "")
        if len(password) < 8:
            flash("Mot de passe : 8 caractères minimum.")
            return render_template("setup.html"), 400
        code = secret.setup(password)
        log_in()
        return render_template("setup.html", recovery_code=code)
    return render_template("setup.html")


@bp.route("/admin/login", methods=["GET", "POST"])
@limiter.limit("5 per 5 minutes", methods=["POST"])
def login():
    secret = _secret()
    if not secret.is_configured():
        return redirect(url_for("auth.setup"))
    if request.method == "POST":
        if secret.verify_password(request.form.get("password", "")):
            log_in()
            return redirect(url_for("api.admin_page"))
        flash("Mot de passe incorrect.")
        return render_template("login.html"), 401
    return render_template("login.html")


@bp.post("/admin/logout")
def logout():
    log_out()
    return redirect(url_for("auth.login"))


@bp.route("/admin/recover", methods=["GET", "POST"])
def recover():
    secret = _secret()
    if request.method == "POST":
        try:
            new_code = secret.recover(
                request.form.get("recovery_code", ""),
                request.form.get("password", ""),
            )
        except ValueError:
            flash("Code de récupération invalide.")
            return render_template("login.html", recover=True), 401
        return render_template("login.html", recovery_code=new_code)
    return render_template("login.html", recover=True)
```
> `url_for("api.admin_page")` est fourni en P3 (route `GET /admin`). Pour que les tests P2 passent avant P3, enregistrer en P2 un blueprint `api` minimal exposant `GET /admin` (stub) et `GET /api/state` protégé (renvoie le draft). Ces stubs sont étoffés en P3.

- [ ] **Step 5: Câbler la factory + stubs + templates**

Dans `comroster/__init__.py`, après la config :
```python
    from .services.storage import Storage
    from .services.secret import SecretStore
    from .security import csrf, limiter, login_required

    app.extensions["storage"] = Storage(app.config["DATA_DIR"])
    app.extensions["secret"] = SecretStore(app.config["DATA_DIR"])

    if app.config.get("TESTING"):
        app.config["WTF_CSRF_ENABLED"] = False
    csrf.init_app(app)
    limiter.init_app(app)

    from .auth import bp as auth_bp
    app.register_blueprint(auth_bp)

    # stub api (étoffé en P3)
    from flask import Blueprint, jsonify, render_template
    api_stub = Blueprint("api", __name__)

    @api_stub.get("/admin")
    @login_required
    def admin_page():
        return render_template("admin.html") if False else "ADMIN OK"

    @api_stub.get("/api/state")
    @login_required
    def get_state():
        return jsonify(app.extensions["storage"].load_draft())

    app.register_blueprint(api_stub)
```
`templates/setup.html` :
```html
<!doctype html><meta charset="utf-8"><title>ComRoster — Setup</title>
{% if recovery_code %}
  <h1>Compte créé</h1>
  <p>Code de récupération (affiché une seule fois) : <strong>{{ recovery_code }}</strong></p>
  <a href="{{ url_for('api.admin_page') }}">Aller à l'admin</a>
{% else %}
  <h1>Configuration initiale</h1>
  {% for m in get_flashed_messages() %}<p>{{ m }}</p>{% endfor %}
  <form method="post">
    <input type="password" name="password" placeholder="Mot de passe (8+)" required>
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
    <button>Créer</button>
  </form>
{% endif %}
```
`templates/login.html` :
```html
<!doctype html><meta charset="utf-8"><title>ComRoster — Connexion</title>
{% for m in get_flashed_messages() %}<p>{{ m }}</p>{% endfor %}
{% if recovery_code %}
  <p>Nouveau code de récupération : <strong>{{ recovery_code }}</strong></p>
{% endif %}
{% if recover %}
  <h1>Réinitialiser</h1>
  <form method="post" action="{{ url_for('auth.recover') }}">
    <input name="recovery_code" placeholder="Code de récupération" required>
    <input type="password" name="password" placeholder="Nouveau mot de passe (8+)" required>
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
    <button>Réinitialiser</button>
  </form>
{% else %}
  <h1>Connexion</h1>
  <form method="post">
    <input type="password" name="password" required>
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
    <button>Se connecter</button>
  </form>
  <a href="{{ url_for('auth.recover') }}">Mot de passe oublié ?</a>
{% endif %}
```

- [ ] **Step 6: Lancer (passe)** — `.venv/bin/pytest tests/test_auth.py -v` → PASS.

- [ ] **Step 7: Commit**

```bash
git add comroster/security.py comroster/auth.py comroster/__init__.py templates/ tests/test_auth.py
git commit -m "feat(p2): auth — setup/login/logout/recover, CSRF, rate-limit, garde de session"
```

---

## Phase 3 — API CRUD (sur le brouillon)

### Task 5: Blueprint api — CRUD groupes & personnes + import/export

**Files:**
- Modify/Create: `comroster/api.py` (remplace le stub par le vrai blueprint)
- Modify: `comroster/__init__.py` (retirer le stub, enregistrer `api.py`)
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: `Storage`, `model`, `login_required`.
- Produces (toutes protégées par `login_required`, JSON in/out) :
  - `GET /admin` → page admin (`admin.html`, ajoutée en P5 ; stub texte avant).
  - `GET /api/state` → brouillon.
  - `POST /api/groups` `{name,color,order?}` → 200 groupe ; `PATCH /api/groups/<id>` ; `DELETE /api/groups/<id>` (membres → pool).
  - `POST /api/people` `{name,role,beltpack,group_id?}` → 200 ; 409 si beltpack pris. `PATCH /api/people/<id>` ; `DELETE /api/people/<id>`.
  - `GET /api/export` → JSON complet (téléchargement). `POST /api/import` → remplace le brouillon (valide d'abord ; 400 si invalide).
  - Helper interne `_save(state)` = `storage.save_draft(state)`.
  - Mapping `ValidationError.code` → HTTP : `beltpack_conflict|beltpack_empty` → 409, `not_found` → 404, autres → 400.

- [ ] **Step 1: Tests (échouent)**

`tests/test_api.py` :
```python
import pytest


@pytest.fixture
def auth_client(client):
    client.post("/admin/setup", data={"password": "motdepasse8"})
    return client


def test_crud_group(auth_client):
    r = auth_client.post("/api/groups", json={"name": "Plateau", "color": "#00A8E8"})
    assert r.status_code == 200
    gid = r.get_json()["id"]
    r2 = auth_client.patch(f"/api/groups/{gid}", json={"name": "Plateau 2"})
    assert r2.get_json()["name"] == "Plateau 2"
    r3 = auth_client.delete(f"/api/groups/{gid}")
    assert r3.status_code == 200


def test_create_person(auth_client):
    r = auth_client.post("/api/people", json={"name": "Jean", "role": "HF", "beltpack": "12"})
    assert r.status_code == 200
    assert r.get_json()["beltpack"] == "12"


def test_duplicate_beltpack_409(auth_client):
    auth_client.post("/api/people", json={"name": "Jean", "role": "HF", "beltpack": "12"})
    r = auth_client.post("/api/people", json={"name": "Marie", "role": "Lum", "beltpack": "12"})
    assert r.status_code == 409


def test_delete_group_moves_people_to_pool(auth_client):
    g = auth_client.post("/api/groups", json={"name": "P", "color": "#fff"}).get_json()
    p = auth_client.post("/api/people", json={"name": "Jean", "role": "HF", "beltpack": "12", "group_id": g["id"]}).get_json()
    auth_client.delete(f"/api/groups/{g['id']}")
    state = auth_client.get("/api/state").get_json()
    person = [x for x in state["people"] if x["id"] == p["id"]][0]
    assert person["group_id"] is None


def test_patch_person_group_assignment(auth_client):
    g = auth_client.post("/api/groups", json={"name": "P", "color": "#fff"}).get_json()
    p = auth_client.post("/api/people", json={"name": "Jean", "role": "HF", "beltpack": "12"}).get_json()
    r = auth_client.patch(f"/api/people/{p['id']}", json={"group_id": g["id"]})
    assert r.get_json()["group_id"] == g["id"]


def test_404_unknown_person(auth_client):
    r = auth_client.patch("/api/people/ghost", json={"name": "X"})
    assert r.status_code == 404


def test_export_import_roundtrip(auth_client):
    auth_client.post("/api/people", json={"name": "Jean", "role": "HF", "beltpack": "12"})
    exported = auth_client.get("/api/export").get_json()
    auth_client.post("/api/import", json=exported)
    state = auth_client.get("/api/state").get_json()
    assert any(p["name"] == "Jean" for p in state["people"])


def test_import_invalid_400(auth_client):
    r = auth_client.post("/api/import", json={"people": [{"id": "1", "name": "A", "role": "", "beltpack": "1", "group_id": "ghost"}], "groups": [], "version": 1})
    assert r.status_code == 400
```

- [ ] **Step 2: Lancer (échoue)** — FAIL.

- [ ] **Step 3: Implémenter api.py**

```python
from flask import Blueprint, request, jsonify, current_app, render_template

from .security import login_required
from .services import model

bp = Blueprint("api", __name__)

_CODE_TO_HTTP = {
    "beltpack_conflict": 409,
    "beltpack_empty": 409,
    "not_found": 404,
}


def _storage():
    return current_app.extensions["storage"]


def _error(exc):
    return jsonify({"error": str(exc), "code": exc.code}), _CODE_TO_HTTP.get(exc.code, 400)


@bp.get("/admin")
@login_required
def admin_page():
    try:
        return render_template("admin.html")
    except Exception:
        return "ADMIN OK"


@bp.get("/api/state")
@login_required
def get_state():
    return jsonify(_storage().load_draft())


@bp.post("/api/groups")
@login_required
def create_group():
    data = request.get_json(force=True)
    state = _storage().load_draft()
    try:
        g = model.add_group(state, data["name"], data.get("color", "#888888"), data.get("order"))
    except model.ValidationError as exc:
        return _error(exc)
    _storage().save_draft(state)
    return jsonify(g)


@bp.patch("/api/groups/<gid>")
@login_required
def patch_group(gid):
    data = request.get_json(force=True)
    state = _storage().load_draft()
    try:
        g = model.update_group(state, gid, **data)
    except model.ValidationError as exc:
        return _error(exc)
    _storage().save_draft(state)
    return jsonify(g)


@bp.delete("/api/groups/<gid>")
@login_required
def delete_group(gid):
    state = _storage().load_draft()
    try:
        model.delete_group(state, gid)
    except model.ValidationError as exc:
        return _error(exc)
    _storage().save_draft(state)
    return jsonify({"ok": True})


@bp.post("/api/people")
@login_required
def create_person():
    data = request.get_json(force=True)
    state = _storage().load_draft()
    try:
        p = model.add_person(state, data["name"], data.get("role", ""), data["beltpack"], data.get("group_id"))
    except model.ValidationError as exc:
        return _error(exc)
    _storage().save_draft(state)
    return jsonify(p)


@bp.patch("/api/people/<pid>")
@login_required
def patch_person(pid):
    data = request.get_json(force=True)
    state = _storage().load_draft()
    try:
        p = model.update_person(state, pid, **data)
    except model.ValidationError as exc:
        return _error(exc)
    _storage().save_draft(state)
    return jsonify(p)


@bp.delete("/api/people/<pid>")
@login_required
def delete_person(pid):
    state = _storage().load_draft()
    try:
        model.delete_person(state, pid)
    except model.ValidationError as exc:
        return _error(exc)
    _storage().save_draft(state)
    return jsonify({"ok": True})


@bp.get("/api/export")
@login_required
def export_state():
    resp = jsonify(_storage().load_draft())
    resp.headers["Content-Disposition"] = "attachment; filename=comroster.json"
    return resp


@bp.post("/api/import")
@login_required
def import_state():
    data = request.get_json(force=True)
    try:
        if not all(k in data for k in ("version", "groups", "people")):
            raise model.ValidationError("Structure invalide", code="invalid")
        model.validate_state(data)
    except model.ValidationError as exc:
        return jsonify({"error": str(exc), "code": exc.code}), 400
    model.touch(data)
    _storage().save_draft(data)
    return jsonify(data)
```

- [ ] **Step 4: Retirer le stub api de la factory**

Dans `comroster/__init__.py`, supprimer le bloc `api_stub` et remplacer par :
```python
    from .api import bp as api_bp
    app.register_blueprint(api_bp)
```
(garder l'enregistrement de `auth_bp` avant.)

- [ ] **Step 5: Lancer (passe)** — `.venv/bin/pytest tests/test_api.py tests/test_auth.py -v` → PASS.

- [ ] **Step 6: Commit**

```bash
git add comroster/api.py comroster/__init__.py tests/test_api.py
git commit -m "feat(p3): API CRUD groupes/personnes, import/export, mapping erreurs 404/409"
```

---

## Phase 4 — Publication & temps réel

### Task 6: Broker pub/sub en mémoire (`pubsub.py`)

**Files:**
- Create: `comroster/services/pubsub.py`
- Test: `tests/test_pubsub.py`

**Interfaces:**
- Produces:
  - `Broker()` ; `.subscribe() -> queue.Queue` (enregistre un abonné) ; `.unsubscribe(q)` ; `.publish(event: str, data: dict)` (pousse `(event, data)` à tous les abonnés) ; `.subscriber_count -> int`.

- [ ] **Step 1: Tests (échouent)**

`tests/test_pubsub.py` :
```python
from comroster.services.pubsub import Broker


def test_subscribe_receives_published_event():
    b = Broker()
    q = b.subscribe()
    b.publish("published", {"x": 1})
    event, data = q.get_nowait()
    assert event == "published" and data == {"x": 1}


def test_unsubscribe_stops_delivery():
    b = Broker()
    q = b.subscribe()
    assert b.subscriber_count == 1
    b.unsubscribe(q)
    assert b.subscriber_count == 0
    b.publish("published", {"x": 1})
    assert q.empty()


def test_multiple_subscribers():
    b = Broker()
    q1, q2 = b.subscribe(), b.subscribe()
    b.publish("published", {"v": 2})
    assert q1.get_nowait()[1] == {"v": 2}
    assert q2.get_nowait()[1] == {"v": 2}
```

- [ ] **Step 2: Lancer (échoue)** — FAIL.

- [ ] **Step 3: Implémenter pubsub.py**

```python
import queue
import threading


class Broker:
    def __init__(self):
        self._subscribers = []
        self._lock = threading.Lock()

    def subscribe(self):
        q = queue.Queue(maxsize=100)
        with self._lock:
            self._subscribers.append(q)
        return q

    def unsubscribe(self, q):
        with self._lock:
            if q in self._subscribers:
                self._subscribers.remove(q)

    def publish(self, event, data):
        with self._lock:
            targets = list(self._subscribers)
        for q in targets:
            try:
                q.put_nowait((event, data))
            except queue.Full:
                pass

    @property
    def subscriber_count(self):
        with self._lock:
            return len(self._subscribers)
```

- [ ] **Step 4: Lancer (passe)** — PASS.

- [ ] **Step 5: Commit**

```bash
git add comroster/services/pubsub.py tests/test_pubsub.py && git commit -m "feat(p4): broker pub/sub SSE en mémoire"
```

### Task 7: Historique (`history.py`)

**Files:**
- Create: `comroster/services/history.py`
- Test: `tests/test_history.py`

**Interfaces:**
- Consumes: `Storage.atomic_write`, `Storage.history_dir`.
- Produces:
  - `History(storage)` ; `.archive(state) -> str` (écrit `history/<timestamp>.json`, retourne le timestamp) ; `.list() -> list[dict]` (`[{"timestamp","datetime"}]` trié récent→ancien) ; `.load(timestamp) -> dict` (lève `KeyError` si absent).

- [ ] **Step 1: Tests (échouent)**

`tests/test_history.py` :
```python
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
    model.add_person(s, "Jean", "HF", "12")
    ts = h.archive(s)
    loaded = h.load(ts)
    assert loaded["people"][0]["name"] == "Jean"


def test_load_unknown_raises(tmp_path):
    h = History(Storage(str(tmp_path)))
    with pytest.raises(KeyError):
        h.load("nope")
```

- [ ] **Step 2: Lancer (échoue)** — FAIL.

- [ ] **Step 3: Implémenter history.py**

```python
import json
import os
from datetime import datetime, timezone


class History:
    def __init__(self, storage):
        self.storage = storage
        self.dir = storage.history_dir
        os.makedirs(self.dir, exist_ok=True)

    def archive(self, state):
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        self.storage.atomic_write(os.path.join(self.dir, f"{ts}.json"), state)
        return ts

    def list(self):
        items = []
        for fname in os.listdir(self.dir):
            if fname.endswith(".json"):
                ts = fname[:-5]
                items.append({"timestamp": ts, "datetime": self._humanize(ts)})
        return sorted(items, key=lambda x: x["timestamp"], reverse=True)

    def load(self, timestamp):
        path = os.path.join(self.dir, f"{timestamp}.json")
        if not os.path.exists(path):
            raise KeyError(timestamp)
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)

    @staticmethod
    def _humanize(ts):
        try:
            dt = datetime.strptime(ts, "%Y%m%dT%H%M%S%fZ")
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            return ts
```

- [ ] **Step 4: Lancer (passe)** — PASS.

- [ ] **Step 5: Commit**

```bash
git add comroster/services/history.py tests/test_history.py && git commit -m "feat(p4): historique — archive, list, load"
```

### Task 8: Séquence de publication + blueprint display (SSE)

**Files:**
- Create: `comroster/display.py`
- Modify: `comroster/__init__.py` (instancier `Broker`/`History` sur `app.extensions`, enregistrer `display_bp`)
- Modify: `comroster/api.py` (ajouter `POST /api/publish`, `GET /api/history`, `POST /api/history/<ts>/restore`)
- Test: `tests/test_publish.py`

**Interfaces:**
- Consumes: `Storage`, `model.validate_state`, `History.archive`, `Broker.publish/subscribe`.
- Produces:
  - `POST /api/publish` : valide le brouillon → 409 si invalide ; sinon `save_published`, `history.archive`, `broker.publish("published", state)` → 200.
  - `GET /api/history` → liste ; `POST /api/history/<ts>/restore` → recharge le snapshot comme brouillon (200/404).
  - `display` blueprint : `GET /display` (page) ; `GET /events` (SSE). À la connexion : `retry: 3000` + event `snapshot` (état publié ou état vide si jamais publié) ; puis relais des events du broker ; heartbeat `: keepalive` toutes les 15 s.
  - Helper `format_sse(event, data) -> str`.

- [ ] **Step 1: Tests (échouent)**

`tests/test_publish.py` :
```python
import json
import pytest


@pytest.fixture
def auth_client(client):
    client.post("/admin/setup", data={"password": "motdepasse8"})
    return client


def test_publish_copies_draft_to_published(auth_client, app):
    auth_client.post("/api/people", json={"name": "Jean", "role": "HF", "beltpack": "12"})
    r = auth_client.post("/api/publish")
    assert r.status_code == 200
    published = app.extensions["storage"].load_published()
    assert any(p["name"] == "Jean" for p in published["people"])


def test_publish_invalid_draft_409(auth_client, app):
    # injecte un brouillon invalide directement
    bad = {"version": 1, "updated_at": "x", "groups": [],
           "people": [{"id": "1", "name": "A", "role": "", "beltpack": "1", "group_id": "ghost"}]}
    app.extensions["storage"].save_draft(bad)
    r = auth_client.post("/api/publish")
    assert r.status_code == 409


def test_publish_archives_history(auth_client, app):
    auth_client.post("/api/publish")
    assert len(app.extensions["history"].list()) >= 1


def test_publish_notifies_sse_subscriber(auth_client, app):
    broker = app.extensions["broker"]
    q = broker.subscribe()
    auth_client.post("/api/people", json={"name": "Jean", "role": "HF", "beltpack": "12"})
    auth_client.post("/api/publish")
    event, data = q.get_nowait()
    assert event == "published"
    assert any(p["name"] == "Jean" for p in data["people"])


def test_events_endpoint_sends_snapshot(client):
    resp = client.get("/events", buffered=True)
    assert resp.status_code == 200
    assert resp.mimetype == "text/event-stream"
    body = next(resp.response).decode()
    assert "retry: 3000" in body or "snapshot" in body


def test_restore_history(auth_client, app):
    auth_client.post("/api/people", json={"name": "Jean", "role": "HF", "beltpack": "12"})
    auth_client.post("/api/publish")
    ts = app.extensions["history"].list()[0]["timestamp"]
    r = auth_client.post(f"/api/history/{ts}/restore")
    assert r.status_code == 200
```

- [ ] **Step 2: Lancer (échoue)** — FAIL.

- [ ] **Step 3: Câbler extensions dans la factory**

Dans `comroster/__init__.py`, après `app.extensions["secret"] = ...` :
```python
    from .services.pubsub import Broker
    from .services.history import History
    app.extensions["broker"] = Broker()
    app.extensions["history"] = History(app.extensions["storage"])
```
Et après l'enregistrement de `api_bp` :
```python
    from .display import bp as display_bp
    app.register_blueprint(display_bp)
```

- [ ] **Step 4: Ajouter publish/history à api.py**

Ajouter dans `comroster/api.py` :
```python
def _broker():
    return current_app.extensions["broker"]


def _history():
    return current_app.extensions["history"]


@bp.post("/api/publish")
@login_required
def publish():
    state = _storage().load_draft()
    try:
        model.validate_state(state)
    except model.ValidationError as exc:
        return _error(exc)
    _storage().save_published(state)
    _history().archive(state)
    _broker().publish("published", state)
    return jsonify({"ok": True, "updated_at": state["updated_at"]})


@bp.get("/api/history")
@login_required
def history_list():
    return jsonify(_history().list())


@bp.post("/api/history/<ts>/restore")
@login_required
def history_restore(ts):
    try:
        snapshot = _history().load(ts)
    except KeyError:
        return jsonify({"error": "not_found", "code": "not_found"}), 404
    model.touch(snapshot)
    _storage().save_draft(snapshot)
    return jsonify(snapshot)
```

- [ ] **Step 5: Implémenter display.py**

```python
import json
import time

from flask import Blueprint, Response, current_app, render_template, stream_with_context

from .services import model

bp = Blueprint("display", __name__)

HEARTBEAT_SECONDS = 15


def format_sse(event, data):
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@bp.get("/display")
def display_page():
    try:
        return render_template("display.html")
    except Exception:
        return "DISPLAY OK"


@bp.get("/events")
def events():
    broker = current_app.extensions["broker"]
    storage = current_app.extensions["storage"]

    def stream():
        q = broker.subscribe()
        try:
            published = storage.load_published() or model.empty_state()
            yield "retry: 3000\n\n"
            yield format_sse("snapshot", published)
            last = time.monotonic()
            while True:
                try:
                    event, data = q.get(timeout=1.0)
                    yield format_sse(event, data)
                except Exception:
                    pass
                if time.monotonic() - last >= HEARTBEAT_SECONDS:
                    yield ": keepalive\n\n"
                    last = time.monotonic()
        finally:
            broker.unsubscribe(q)

    resp = Response(stream_with_context(stream()), mimetype="text/event-stream")
    resp.headers["Cache-Control"] = "no-cache"
    resp.headers["X-Accel-Buffering"] = "no"
    resp.headers["Connection"] = "keep-alive"
    return resp
```
> `q.get(timeout=1.0)` lève `queue.Empty` → capturé par `except Exception` ; on retombe sur le heartbeat. Importer `queue` et remplacer `except Exception` par `except queue.Empty` pour la précision.

- [ ] **Step 6: Lancer (passe)** — `.venv/bin/pytest tests/test_publish.py -v` → PASS.
> Le test SSE lit le premier chunk via `next(resp.response)` ; comme le générateur est infini, ne pas itérer entièrement. `buffered=True` + lecture d'un seul chunk suffit.

- [ ] **Step 7: Commit**

```bash
git add comroster/display.py comroster/api.py comroster/__init__.py tests/test_publish.py
git commit -m "feat(p4): publication atomique + historisation + SSE (snapshot/published/heartbeat)"
```

### Task 9: Tranche verticale de bout en bout (test d'intégration)

**Files:**
- Test: `tests/test_integration.py`

- [ ] **Step 1: Écrire le test bout-en-bout**

```python
import pytest


def test_add_publish_appears_on_display(client, app):
    client.post("/admin/setup", data={"password": "motdepasse8"})
    g = client.post("/api/groups", json={"name": "Plateau", "color": "#00A8E8"}).get_json()
    client.post("/api/people", json={"name": "Jean", "role": "HF", "beltpack": "12", "group_id": g["id"]})
    # avant publication : le publié est vide
    assert app.extensions["storage"].load_published() is None
    client.post("/api/publish")
    published = app.extensions["storage"].load_published()
    assert published["people"][0]["name"] == "Jean"
    assert published["groups"][0]["name"] == "Plateau"
```

- [ ] **Step 2: Lancer (passe)** — `.venv/bin/pytest -v` → tout PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_integration.py && git commit -m "test(p4): tranche verticale ajouter→publier→publié"
```

---

## Phase 5 — UI Admin

### Task 10: Page admin — groupes, personnes, drag-and-drop, publier

**Files:**
- Create: `templates/admin.html`, `static/css/main.css`, `static/js/admin.js`, `static/vendor/sortable.min.js`
- Test: vérification manuelle (parcours §8 du cahier des charges)

**Interfaces:**
- Consomme l'API P3/P4 (`/api/state`, CRUD, `/api/publish`, `/api/export`, `/api/import`).
- `admin.html` expose le `csrf_token()` dans une balise `<meta name="csrf-token">`, lue par `admin.js` et envoyée en en-tête `X-CSRFToken` sur chaque requête mutative (Flask-WTF accepte cet en-tête).

- [ ] **Step 1: Vendorer SortableJS**

Run: `curl -L https://cdn.jsdelivr.net/npm/sortablejs@1.15.2/Sortable.min.js -o static/vendor/sortable.min.js`
Expected: fichier ~45 ko non vide.

- [ ] **Step 2: Écrire admin.html**

```html
<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="csrf-token" content="{{ csrf_token() }}">
  <title>ComRoster — Admin</title>
  <link rel="stylesheet" href="{{ url_for('static', filename='css/main.css') }}">
</head>
<body class="admin">
  <header class="toolbar">
    <h1>ComRoster — Régie</h1>
    <div class="actions">
      <button id="add-group">+ Groupe</button>
      <button id="add-person">+ Personne</button>
      <button id="export">Exporter</button>
      <label class="import-btn">Importer<input type="file" id="import" accept="application/json" hidden></label>
      <button id="publish" class="primary">Publier vers l'affichage</button>
      <form method="post" action="{{ url_for('auth.logout') }}" style="display:inline">
        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
        <button>Déconnexion</button>
      </form>
    </div>
  </header>
  <main id="board">
    <section class="pool">
      <h2>Disponibles</h2>
      <ul id="pool" class="people-list" data-group=""></ul>
    </section>
    <div id="groups"></div>
  </main>
  <div id="toast" class="toast" hidden></div>
  <script src="{{ url_for('static', filename='vendor/sortable.min.js') }}"></script>
  <script src="{{ url_for('static', filename='js/admin.js') }}"></script>
</body>
</html>
```

- [ ] **Step 3: Écrire admin.js**

```javascript
const CSRF = document.querySelector('meta[name="csrf-token"]').content;
let state = { groups: [], people: [] };

async function api(method, url, body) {
  const opts = { method, headers: { 'X-CSRFToken': CSRF } };
  if (body !== undefined) { opts.headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(body); }
  const resp = await fetch(url, opts);
  const data = resp.headers.get('content-type')?.includes('json') ? await resp.json() : null;
  if (!resp.ok) { toast(data?.error || `Erreur ${resp.status}`, true); throw new Error(data?.code || resp.status); }
  return data;
}

function toast(msg, error) {
  const t = document.getElementById('toast');
  t.textContent = msg; t.classList.toggle('error', !!error); t.hidden = false;
  setTimeout(() => (t.hidden = true), 3000);
}

async function load() { state = await api('GET', '/api/state'); render(); }

function personLi(p) {
  const li = document.createElement('li');
  li.className = 'person'; li.dataset.id = p.id;
  li.innerHTML = `<span class="name">${esc(p.name)}</span><span class="role">${esc(p.role)}</span><span class="bp">#${esc(p.beltpack)}</span>`;
  li.addEventListener('contextmenu', (e) => { e.preventDefault(); personMenu(p, e); });
  return li;
}

function esc(s) { const d = document.createElement('div'); d.textContent = s ?? ''; return d.innerHTML; }

function render() {
  const groupsEl = document.getElementById('groups');
  const poolEl = document.getElementById('pool');
  groupsEl.innerHTML = ''; poolEl.innerHTML = '';
  for (const p of state.people.filter(x => !x.group_id)) poolEl.appendChild(personLi(p));
  for (const g of [...state.groups].sort((a, b) => a.order - b.order)) {
    const sec = document.createElement('section');
    sec.className = 'group'; sec.style.borderColor = g.color;
    sec.innerHTML = `<h2 style="background:${g.color}">${esc(g.name)}
      <button data-edit="${g.id}">✎</button><button data-del="${g.id}">🗑</button></h2>`;
    const ul = document.createElement('ul');
    ul.className = 'people-list'; ul.dataset.group = g.id;
    for (const p of state.people.filter(x => x.group_id === g.id)) ul.appendChild(personLi(p));
    sec.appendChild(ul); groupsEl.appendChild(sec);
    makeSortable(ul);
  }
  makeSortable(poolEl);
  groupsEl.querySelectorAll('[data-del]').forEach(b => b.onclick = () => delGroup(b.dataset.del));
  groupsEl.querySelectorAll('[data-edit]').forEach(b => b.onclick = () => editGroup(b.dataset.edit));
}

function makeSortable(ul) {
  Sortable.create(ul, {
    group: 'people', animation: 150,
    onAdd: async (evt) => {
      const pid = evt.item.dataset.id;
      const gid = evt.to.dataset.group || null;
      try { await api('PATCH', `/api/people/${pid}`, { group_id: gid }); }
      finally { load(); }
    },
  });
}

async function delGroup(id) { await api('DELETE', `/api/groups/${id}`); load(); }
async function editGroup(id) {
  const g = state.groups.find(x => x.id === id);
  const name = prompt('Nom du groupe', g.name); if (name === null) return;
  const color = prompt('Couleur (hex)', g.color); if (color === null) return;
  await api('PATCH', `/api/groups/${id}`, { name, color }); load();
}

function personMenu(p, e) {
  const bp = prompt(`Beltpack de ${p.name}`, p.beltpack);
  if (bp === null) return;
  api('PATCH', `/api/people/${p.id}`, { beltpack: bp }).then(load);
}

document.getElementById('add-group').onclick = async () => {
  const name = prompt('Nom du groupe'); if (!name) return;
  const color = prompt('Couleur (hex)', '#00A8E8') || '#00A8E8';
  await api('POST', '/api/groups', { name, color }); load();
};
document.getElementById('add-person').onclick = async () => {
  const name = prompt('Nom'); if (!name) return;
  const role = prompt('Rôle (HF, plateau…)') || '';
  const beltpack = prompt('Numéro de beltpack'); if (!beltpack) return;
  try { await api('POST', '/api/people', { name, role, beltpack }); load(); }
  catch (err) { if (String(err.message).includes('beltpack')) toast('Beltpack déjà attribué', true); }
};
document.getElementById('publish').onclick = async () => {
  await api('POST', '/api/publish'); toast('Publié ✓');
};
document.getElementById('export').onclick = () => { window.location = '/api/export'; };
document.getElementById('import').onchange = async (e) => {
  const file = e.target.files[0]; if (!file) return;
  const data = JSON.parse(await file.text());
  await api('POST', '/api/import', data); load();
};

load();
```

- [ ] **Step 4: Écrire main.css (base admin + display)**

```css
:root { --primary:#00A8E8; --secondary:#1b1f2a; --accent:#ffd166; }
* { box-sizing: border-box; }
body { margin:0; font-family: system-ui, sans-serif; }
body.admin { background:#0f1320; color:#e7ecf3; }
.toolbar { display:flex; justify-content:space-between; align-items:center; padding:.75rem 1rem; background:var(--secondary); position:sticky; top:0; }
.toolbar .actions { display:flex; gap:.5rem; flex-wrap:wrap; }
button, .import-btn { background:#2a3142; color:#e7ecf3; border:1px solid #3a4256; border-radius:8px; padding:.5rem .8rem; cursor:pointer; }
button.primary { background:var(--primary); color:#04121b; font-weight:600; }
#board { display:flex; gap:1rem; padding:1rem; align-items:flex-start; flex-wrap:wrap; }
.pool, .group { background:#161b2b; border:1px solid #283349; border-radius:12px; padding:.75rem; min-width:220px; }
.group { border-top:4px solid; }
.people-list { list-style:none; margin:0; padding:0; min-height:40px; display:flex; flex-direction:column; gap:.4rem; }
.person { background:#202840; border-radius:8px; padding:.5rem .6rem; cursor:grab; display:flex; gap:.5rem; align-items:baseline; }
.person .role { opacity:.7; font-size:.85em; } .person .bp { margin-left:auto; color:var(--accent); font-weight:600; }
.toast { position:fixed; bottom:1rem; left:50%; transform:translateX(-50%); background:#1f8a4c; color:#fff; padding:.6rem 1rem; border-radius:8px; }
.toast.error { background:#c0392b; }
```

- [ ] **Step 5: Vérification manuelle**

Run: `FLASK_SECRET_KEY=dev DATA_DIR=$(pwd)/instance .venv/bin/flask --app app run`
Parcours : ouvrir `/admin/setup`, créer un mot de passe, noter le code, aller sur `/admin`. Vérifier : créer un groupe (couleur visible), ajouter une personne, drag-and-drop pool↔groupe (persisté après refresh), clic droit → changer le beltpack, tenter un beltpack en double → toast d'erreur, Exporter (télécharge), Importer (recharge), Publier → toast « Publié ✓ ».

- [ ] **Step 6: Commit**

```bash
git add templates/admin.html static/ && git commit -m "feat(p5): UI admin — DnD SortableJS, CRUD, contextuel, import/export, publier"
```

---

## Phase 6 — UI Display

### Task 11: Affichage TV temps réel

**Files:**
- Create: `templates/display.html`, `static/js/display.js`
- Modify: `static/css/main.css` (ajouter styles display/glassmorphism)
- Test: vérification manuelle (D1–D8)

- [ ] **Step 1: Écrire display.html**

```html
<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>ComRoster — Affichage</title>
  <link rel="stylesheet" href="{{ url_for('static', filename='css/main.css') }}">
</head>
<body class="display" data-theme="night">
  <header class="d-header">
    <h1>Affectation Intercom</h1>
    <div class="d-meta">
      <span id="stats"></span>
      <span id="clock"></span>
      <span id="live" class="live off">● Hors ligne</span>
      <button id="theme">☀/☾</button>
    </div>
  </header>
  <main id="display-board" class="display-board"></main>
  <script src="{{ url_for('static', filename='js/display.js') }}"></script>
</body>
</html>
```

- [ ] **Step 2: Écrire display.js**

```javascript
const board = document.getElementById('display-board');
const live = document.getElementById('live');
const stats = document.getElementById('stats');

const SCROLL = { initialDelay: 4000, edgePause: 2500, speed: 35 }; // px/s

function esc(s){ const d=document.createElement('div'); d.textContent=s??''; return d.innerHTML; }

function render(state) {
  board.innerHTML = '';
  const grouped = [...state.groups].sort((a,b)=>a.order-b.order);
  for (const g of grouped) {
    const members = state.people.filter(p => p.group_id === g.id);
    const card = document.createElement('section');
    card.className = 'glass-card';
    card.style.setProperty('--card-color', g.color);
    card.innerHTML = `<h2>${esc(g.name)}</h2>` + members.map(p =>
      `<div class="d-person"><span>${esc(p.name)}</span><span class="d-role">${esc(p.role)}</span><span class="d-bp">${esc(p.beltpack)}</span></div>`
    ).join('') || `<h2>${esc(g.name)}</h2><div class="empty">—</div>`;
    board.appendChild(card);
  }
  stats.textContent = `${state.groups.length} groupes · ${state.people.length} personnes`;
}

function setLive(on) {
  live.classList.toggle('off', !on);
  live.classList.toggle('on', on);
  live.textContent = on ? '● En direct' : '● Reconnexion…';
}

function connect() {
  const es = new EventSource('/events');
  es.addEventListener('snapshot', (e) => { render(JSON.parse(e.data)); setLive(true); });
  es.addEventListener('published', (e) => { render(JSON.parse(e.data)); setLive(true); });
  es.onopen = () => setLive(true);
  es.onerror = () => setLive(false); // EventSource reconnecte seul ; le prochain snapshot resync (D8)
}

function tickClock() {
  document.getElementById('clock').textContent = new Date().toLocaleTimeString('fr-FR');
}
setInterval(tickClock, 1000); tickClock();

document.getElementById('theme').onclick = () => {
  const b = document.body;
  b.dataset.theme = b.dataset.theme === 'night' ? 'day' : 'night';
};

// Auto-scroll vertical doux avec pauses en haut/bas
function autoScroll() {
  let dir = 1, paused = true;
  setTimeout(() => (paused = false), SCROLL.initialDelay);
  let last = performance.now();
  function step(now) {
    const dt = (now - last) / 1000; last = now;
    if (!paused) {
      const max = document.body.scrollHeight - window.innerHeight;
      if (max > 0) {
        window.scrollBy(0, dir * SCROLL.speed * dt);
        const y = window.scrollY;
        if (y >= max - 1 && dir === 1) { dir = -1; paused = true; setTimeout(()=>paused=false, SCROLL.edgePause); }
        if (y <= 1 && dir === -1) { dir = 1; paused = true; setTimeout(()=>paused=false, SCROLL.edgePause); }
      }
    }
    requestAnimationFrame(step);
  }
  requestAnimationFrame(step);
}

connect(); autoScroll();
```

- [ ] **Step 3: Ajouter les styles display à main.css**

```css
body.display { background:#05070f; color:#eaf2ff; transition:background .4s, color .4s; }
body.display[data-theme="day"] { background:#eef3fb; color:#0b1424; }
.d-header { position:sticky; top:0; display:flex; justify-content:space-between; align-items:center; padding:1rem 2rem; backdrop-filter:blur(12px); background:rgba(10,14,25,.55); }
body.display[data-theme="day"] .d-header { background:rgba(255,255,255,.6); }
.d-meta { display:flex; gap:1.5rem; align-items:center; font-size:1.4rem; }
.live.on { color:#2ecc71; } .live.off { color:#e74c3c; }
.display-board { display:grid; grid-template-columns:repeat(auto-fill, minmax(320px, 1fr)); gap:1.5rem; padding:2rem; }
.glass-card { border-radius:18px; padding:1.2rem 1.5rem; background:rgba(255,255,255,.07); border:1px solid rgba(255,255,255,.15); border-top:6px solid var(--card-color); backdrop-filter:blur(14px); box-shadow:0 8px 32px rgba(0,0,0,.35); }
.glass-card h2 { margin:0 0 .8rem; font-size:1.8rem; }
.d-person { display:flex; gap:1rem; align-items:baseline; font-size:1.5rem; padding:.35rem 0; border-bottom:1px solid rgba(255,255,255,.08); }
.d-role { opacity:.7; font-size:.9em; } .d-bp { margin-left:auto; font-weight:700; color:var(--accent); }
.empty { opacity:.4; }
@media (prefers-reduced-motion: reduce) { .glass-card { backdrop-filter:none; } }
```

- [ ] **Step 4: Vérification manuelle (D1–D8)**

Avec le serveur lancé : ouvrir `/display` dans un onglet, `/admin` dans un autre. Vérifier : horloge qui avance (D4), indicateur « En direct » vert (D5), stats correctes (D6), bouton jour/nuit (D7), auto-scroll après délai avec pauses (D3). Publier depuis l'admin → l'écran se met à jour sans rechargement (D2). Couper le serveur puis le relancer → l'indicateur passe rouge puis revient vert et resynchronise (D8).

- [ ] **Step 5: Commit**

```bash
git add templates/display.html static/js/display.js static/css/main.css
git commit -m "feat(p6): UI display — SSE, glassmorphism, auto-scroll, horloge, live, jour/nuit, reconnexion"
```

---

## Phase 7 — Historique (nice-to-have)

### Task 12: UI consultation & restauration des publications

**Files:**
- Modify: `templates/admin.html` (bouton « Historique » + panneau), `static/js/admin.js` (fetch `/api/history`, restore)
- Test: vérification manuelle (B4/B5) — l'API est déjà testée en P4 (`test_restore_history`).

- [ ] **Step 1: Ajouter le bouton et le panneau dans admin.html**

Dans `.actions`, avant le bouton Publier :
```html
<button id="history-btn">Historique</button>
```
Avant `</body>` :
```html
<dialog id="history-dialog">
  <h2>Publications passées</h2>
  <ul id="history-list"></ul>
  <menu><button id="history-close">Fermer</button></menu>
</dialog>
```

- [ ] **Step 2: Ajouter la logique dans admin.js**

```javascript
document.getElementById('history-btn').onclick = async () => {
  const items = await api('GET', '/api/history');
  const ul = document.getElementById('history-list');
  ul.innerHTML = items.map(i =>
    `<li>${i.datetime} <button data-restore="${i.timestamp}">Restaurer</button></li>`).join('')
    || '<li>Aucune publication.</li>';
  ul.querySelectorAll('[data-restore]').forEach(b => b.onclick = async () => {
    await api('POST', `/api/history/${b.dataset.restore}/restore`);
    document.getElementById('history-dialog').close();
    toast('Snapshot restauré dans le brouillon'); load();
  });
  document.getElementById('history-dialog').showModal();
};
document.getElementById('history-close').onclick = () =>
  document.getElementById('history-dialog').close();
```

- [ ] **Step 3: Vérification manuelle**

Publier plusieurs fois (en modifiant entre-temps), ouvrir « Historique » → liste horodatée. Cliquer « Restaurer » sur une entrée ancienne → le brouillon admin revient à cet état ; republier le diffuse.

- [ ] **Step 4: Commit**

```bash
git add templates/admin.html static/js/admin.js
git commit -m "feat(p7): UI historique — consultation et restauration des snapshots"
```

---

## Phase 8 — Durcissement & déploiement

### Task 13: Tests modes de panne + packaging prod

**Files:**
- Create: `tests/test_failure_modes.py`, `deploy/comroster.service`, `deploy/nginx.conf`, `README.md`, `gunicorn.conf.py`
- Modify: `requirements.txt` (ajouter `gunicorn`)

- [ ] **Step 1: Tests modes de panne**

`tests/test_failure_modes.py` :
```python
import pytest


@pytest.fixture
def auth_client(client):
    client.post("/admin/setup", data={"password": "motdepasse8"})
    return client


def test_last_write_wins_two_admins(auth_client, app, client):
    # deux "sessions" écrivent ; la dernière gagne
    p = auth_client.post("/api/people", json={"name": "Jean", "role": "HF", "beltpack": "12"}).get_json()
    auth_client.patch(f"/api/people/{p['id']}", json={"name": "A"})
    auth_client.patch(f"/api/people/{p['id']}", json={"name": "B"})
    state = auth_client.get("/api/state").get_json()
    assert [x for x in state["people"] if x["id"] == p["id"]][0]["name"] == "B"


def test_duplicate_beltpack_blocked_on_patch(auth_client):
    auth_client.post("/api/people", json={"name": "Jean", "role": "HF", "beltpack": "12"})
    p2 = auth_client.post("/api/people", json={"name": "Marie", "role": "Lum", "beltpack": "13"}).get_json()
    r = auth_client.patch(f"/api/people/{p2['id']}", json={"beltpack": "12"})
    assert r.status_code == 409


def test_corrupted_draft_recovers(app, tmp_path):
    # un fichier corrompu ne doit pas planter le chargement de façon silencieuse
    storage = app.extensions["storage"]
    with open(storage.draft_path, "w") as fh:
        fh.write("{ pas du json")
    with pytest.raises(Exception):
        storage.load_draft()
```
> Décision : un brouillon corrompu lève (échec bruyant) plutôt que de masquer la corruption. Acceptable car l'écriture atomique empêche la corruption en fonctionnement normal ; ce test documente le comportement.

- [ ] **Step 2: Lancer (passe)** — `.venv/bin/pytest -v` → tout PASS.

- [ ] **Step 3: gunicorn.conf.py**

```python
workers = 1
threads = 8
worker_class = "gthread"
bind = "127.0.0.1:8080"
timeout = 120
```
Ajouter `gunicorn>=21` à `requirements.txt`.

- [ ] **Step 4: deploy/comroster.service**

```ini
[Unit]
Description=ComRoster
After=network.target

[Service]
Type=simple
User=comroster
WorkingDirectory=/opt/comroster
Environment=FLASK_SECRET_KEY=__REMPLACER_PAR_UNE_CLE_LONGUE__
Environment=DATA_DIR=/opt/comroster/instance
ExecStart=/opt/comroster/.venv/bin/gunicorn -c gunicorn.conf.py app:app
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 5: deploy/nginx.conf**

```nginx
server {
    listen 80;
    server_name comroster.local;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
    location /events {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_buffering off;            # indispensable au SSE
        proxy_cache off;
        proxy_read_timeout 3600s;
        proxy_set_header Connection '';
        chunked_transfer_encoding off;
    }
}
```

- [ ] **Step 6: README.md** — documenter : install (`python3.12 -m venv`, `pip install -r requirements.txt`), variables d'env (`FLASK_SECRET_KEY` obligatoire, `DATA_DIR`, `PORT`, `FLASK_DEBUG`), lancement dev (`flask --app app run`), lancement prod (gunicorn 1 worker), setup initial (`/admin/setup`), note SSE + Nginx `proxy_buffering off`, rappel `.gitignore` des fichiers d'état.

- [ ] **Step 7: Commit**

```bash
git add tests/test_failure_modes.py gunicorn.conf.py deploy/ README.md requirements.txt
git commit -m "feat(p8): tests modes de panne, gunicorn 1 worker, systemd, nginx SSE, README"
```

---

## Checklist d'acceptation finale (§10.7)

- [ ] A1–A7 : setup unique, login/logout, récupération, reset, routes gardées
- [ ] G1–G5 : CRUD groupes ; suppression → membres au pool
- [ ] P1–P8 : CRUD personnes, DnD, menu contextuel ; beltpack unique, blocage dur (409)
- [ ] I1–I2 : export / import JSON
- [ ] B1–B5 : publication atomique, SSE, historisation, consultation/restauration
- [ ] D1–D8 : affichage TV, temps réel, auto-scroll, horloge, live, stats, jour/nuit, reconnexion auto
- [ ] Sécurité : secret obligatoire, cookies durcis, CSRF, rate-limit, hashing, secret hors git
- [ ] Prod : systemd + Nginx (`proxy_buffering off`, `X-Accel-Buffering: no`) + gunicorn 1 worker gthread

## Notes de couverture (auto-revue)

- **A6 (reset total)** : non codé — c'est une action manuelle (`rm admin_secret.json`), documentée au README (Step 6). Aucune route nécessaire.
- **Cookies durcis (`SESSION_COOKIE_*`)** : à poser dans la factory en P2 — ajouter à `create_app` :
  `app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")` et `SESSION_COOKIE_SECURE=True` hors debug/testing.
- **G5 (ordre des groupes)** : champ `order` géré côté modèle et tri à l'affichage ; réordonnancement par DnD des groupes = amélioration optionnelle (le `PATCH order` existe déjà).
- **A1 « min 8 caractères »** : validé dans `auth.setup` (Step 4, P2).

