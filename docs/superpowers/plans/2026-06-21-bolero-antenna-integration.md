# Intégration antenne Bolero — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permettre à ComRoster, en option activable, de se connecter à une antenne Riedel Bolero (IP + mot de passe) et d'importer ses beltpacks réels dans le brouillon d'affectation.

**Architecture:** Feature flag `bolero_enabled` (réglages persistés). Un service `antenna.py` (client REST Bolero synchrone en Basic Auth, identifiants chiffrés Fernet) + des fonctions de fusion dans `model.py` (`merge_beltpacks`, `diff_beltpacks`). Un blueprint `comroster/antenna.py` expose `/api/settings` et `/api/antenna/*`, gardés par le flag. L'UI admin gagne un dialog Réglages (interrupteur + bloc Antenne) et un dialog récap d'import.

**Tech Stack:** Python 3.12, Flask, `cryptography` (Fernet), urllib (client HTTP), pytest, JS vanilla.

**Spec de référence :** `docs/superpowers/specs/2026-06-21-bolero-antenna-integration-design.md`.

## Global Constraints

- **Feature flag `bolero_enabled`** : défaut **false**. Flag faux ⇒ `/api/antenna/*` renvoient **409** `{"error":"bolero_disabled"}`, aucune UI antenne, aucun appel réseau, pas de reconnexion auto.
- **Auth Bolero** : HTTP Basic Auth, utilisateur **fixe `admin`** + mot de passe → `Authorization: Basic base64("admin:"+password)`. Mot de passe vide ⇒ header omis.
- **Mapping** : `bpConfig.bpNumber` → `beltpack` (str) ; `bpConfig.bpName` → `role` ; nom de personne **vide** à l'import.
- **Ré-import = synchroniser** : crée les nouveaux, met à jour le rôle des existants, **préserve noms et fiches manuelles**, ne supprime jamais.
- **Identifiants chiffrés** : Fernet, clé = `base64.urlsafe_b64encode(sha256(FLASK_SECRET_KEY))`. `antenna.json` permissions `600`, `password_enc` jamais en clair, **jamais renvoyé au client**.
- **Persistance** : `settings.json` et `antenna.json` dans `DATA_DIR`, **gitignored**.
- **Endpoints** protégés `login_required` + CSRF (déjà global). Import en deux temps : `preview` (sans muter) puis `apply`.
- **TDD** sur le backend (settings, antenna client, merge/diff, gardes). Commits atomiques.

---

## File Structure

| Fichier | Responsabilité |
|---------|----------------|
| `comroster/services/settings.py` | Réglages app persistés (`bolero_enabled`) |
| `comroster/services/antenna.py` | Client Bolero (Basic Auth, test connexion, `/rest/bp`), creds chiffrés, état mémoire |
| `comroster/antenna.py` | Blueprint : `/api/settings`, `/api/antenna/*`, garde flag |
| `comroster/services/model.py` | + `merge_beltpacks`, `diff_beltpacks` |
| `comroster/__init__.py` | Instancier services, enregistrer blueprint, reconnexion auto (lazy) |
| `templates/admin.html` | Toolbar regroupée + dialog Réglages + dialog Récap |
| `static/js/admin.js` | Logique réglages/connexion/import |
| `static/css/admin.css` | Styles toolbar groupée + interrupteur |
| `requirements.txt` | + `cryptography` |
| `.gitignore` | + `settings.json`, `antenna.json` |
| `tests/test_settings.py`, `tests/test_antenna.py`, `tests/test_merge_beltpacks.py`, `tests/test_antenna_api.py` | pytest |

---

## Task 1: Réglages persistés (`settings.py`) + dépendance

**Files:**
- Create: `comroster/services/settings.py`
- Modify: `requirements.txt`, `.gitignore`
- Test: `tests/test_settings.py`

**Interfaces:**
- Consumes: `Storage` (de `comroster/services/storage.py`) — `Storage(data_dir)` a `.data_dir`, `.atomic_write(path, data)`, et lit via `json`.
- Produces:
  - `Settings(storage)` ; `.get(key, default=None)` ; `.set(key, value) -> None` ; `.all() -> dict`.
  - Persiste `<data_dir>/settings.json`. Défaut `{}` si absent.

- [ ] **Step 1: Ajouter la dépendance et les ignores**

`requirements.txt` — ajouter la ligne :
```
cryptography>=42
```
`.gitignore` — ajouter sous le bloc des fichiers d'état :
```
settings.json
antenna.json
```
Puis installer : `.venv/bin/pip install -q 'cryptography>=42'`.

- [ ] **Step 2: Écrire les tests (échouent)**

`tests/test_settings.py` :
```python
from comroster.services.storage import Storage
from comroster.services.settings import Settings


def test_default_empty(tmp_path):
    s = Settings(Storage(str(tmp_path)))
    assert s.get("bolero_enabled", False) is False
    assert s.all() == {}


def test_set_and_persist(tmp_path):
    st = Storage(str(tmp_path))
    Settings(st).set("bolero_enabled", True)
    # nouvelle instance relit le disque
    assert Settings(st).get("bolero_enabled") is True


def test_set_overwrites(tmp_path):
    st = Storage(str(tmp_path))
    s = Settings(st)
    s.set("bolero_enabled", True)
    s.set("bolero_enabled", False)
    assert s.get("bolero_enabled") is False
```

- [ ] **Step 3: Lancer (échoue)** — `.venv/bin/pytest tests/test_settings.py -q` → FAIL (module absent).

- [ ] **Step 4: Implémenter `settings.py`**

```python
import json
import os


class Settings:
    def __init__(self, storage):
        self.storage = storage
        self.path = os.path.join(storage.data_dir, "settings.json")

    def all(self):
        if not os.path.exists(self.path):
            return {}
        with open(self.path, encoding="utf-8") as fh:
            return json.load(fh)

    def get(self, key, default=None):
        return self.all().get(key, default)

    def set(self, key, value):
        data = self.all()
        data[key] = value
        self.storage.atomic_write(self.path, data)
```

- [ ] **Step 5: Lancer (passe)** — `.venv/bin/pytest tests/test_settings.py -q` → PASS.

- [ ] **Step 6: Commit**

```bash
git add comroster/services/settings.py tests/test_settings.py requirements.txt .gitignore
git commit -m "feat(bolero): réglages app persistés + dépendance cryptography"
```

---

## Task 2: Fusion des beltpacks dans le modèle (`merge_beltpacks` / `diff_beltpacks`)

**Files:**
- Modify: `comroster/services/model.py`
- Test: `tests/test_merge_beltpacks.py`

**Interfaces:**
- Consumes: `empty_state()`, `new_id()`, `normalize_beltpack(value)`, `touch(state)` (déjà dans `model.py`).
- Produces:
  - `merge_beltpacks(state, items) -> dict` où `items=[{"number":str,"name":str,"online":bool}]`, retourne `{"created":int,"updated":int}`. Mute `state`.
  - `diff_beltpacks(state, items) -> dict` → `{"new":[{number,name}], "changed":[{number,old_role,new_role}], "unchanged":int, "missing":[{number,role}]}`. Ne mute pas.

- [ ] **Step 1: Écrire les tests (échouent)**

`tests/test_merge_beltpacks.py` :
```python
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
```

- [ ] **Step 2: Lancer (échoue)** — `.venv/bin/pytest tests/test_merge_beltpacks.py -q` → FAIL.

- [ ] **Step 3: Implémenter dans `model.py`** (ajouter à la fin du fichier)

```python
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
                "id": new_id(), "name": "", "role": name,
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
```

- [ ] **Step 4: Lancer (passe)** — `.venv/bin/pytest tests/test_merge_beltpacks.py -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add comroster/services/model.py tests/test_merge_beltpacks.py
git commit -m "feat(bolero): merge_beltpacks + diff_beltpacks (synchro antenne→brouillon)"
```

---

## Task 3: Client antenne (`services/antenna.py`)

**Files:**
- Create: `comroster/services/antenna.py`
- Test: `tests/test_antenna.py`

**Interfaces:**
- Produces:
  - `AntennaError(Exception)`.
  - `AntennaClient(data_dir: str, secret_key: str)`.
  - `.connect(ip, password) -> dict` (info) — teste `GET /rest/nodeStatus` en Basic Auth ; succès → persiste creds chiffrés + info, `connected=True` ; échec → `AntennaError`, rien écrit.
  - `.disconnect() -> None` (efface mémoire + `antenna.json`).
  - `.status() -> dict` → `{"connected":bool,"ip":str|None,"info":dict}` (jamais le mot de passe).
  - `.fetch_beltpacks() -> list[dict]` → `[{"number":str,"name":str,"online":bool}]` (BP `registered`).
  - `.load_persisted() -> None` (recharge ip+password déchiffrés, sans tester).
  - `.reconnect() -> bool` (re-teste avec les creds en mémoire ; True si connecté).
  - `.connected -> bool` (propriété), `.ip -> str|None`.
  - `_request(method, path, body=None, timeout=5) -> (ok:bool, data:dict)` (mockée en test).

- [ ] **Step 1: Écrire les tests (échouent)**

`tests/test_antenna.py` :
```python
import json
import os
import pytest
from comroster.services.antenna import AntennaClient, AntennaError


def _fake_ok(method, path, body=None, timeout=5):
    if path == "/rest/nodeStatus":
        return True, {"nodeStatus": [{"nodeId": 1, "isLocal": True, "ip": "192.168.1.11"}]}
    if path == "/rest/firmware":
        return True, {"firmware": {"version": "3.4.1-15"}}
    if path == "/rest/bp":
        return True, {"bp": [
            {"registered": True, "id": 1, "connectedNodeId": 1,
             "bpConfig": {"bpNumber": 5, "bpName": "Régie Son"}},
            {"registered": True, "id": 2, "connectedNodeId": 0,
             "bpConfig": {"bpNumber": 7, "bpName": "Lumière"}},
            {"registered": False, "id": 3, "bpConfig": {"bpNumber": 9, "bpName": "x"}},
        ]}
    return False, {"error": "unexpected"}


def test_connect_persists_encrypted(tmp_path, monkeypatch):
    c = AntennaClient(str(tmp_path), "secret-key")
    monkeypatch.setattr(c, "_request", _fake_ok)
    info = c.connect("192.168.1.11", "motdepasse")
    assert c.connected is True and c.ip == "192.168.1.11"
    assert info["firmware"]["version"] == "3.4.1-15"
    raw = open(os.path.join(str(tmp_path), "antenna.json")).read()
    assert "motdepasse" not in raw                  # mot de passe chiffré
    assert json.loads(raw)["ip"] == "192.168.1.11"


def test_status_never_leaks_password(tmp_path, monkeypatch):
    c = AntennaClient(str(tmp_path), "secret-key")
    monkeypatch.setattr(c, "_request", _fake_ok)
    c.connect("192.168.1.11", "motdepasse")
    st = c.status()
    assert "password" not in json.dumps(st) and "motdepasse" not in json.dumps(st)


def test_connect_failure_writes_nothing(tmp_path, monkeypatch):
    c = AntennaClient(str(tmp_path), "secret-key")
    monkeypatch.setattr(c, "_request", lambda *a, **k: (False, {"error": "timeout"}))
    with pytest.raises(AntennaError):
        c.connect("10.0.0.9", "x")
    assert not os.path.exists(os.path.join(str(tmp_path), "antenna.json"))
    assert c.connected is False


def test_persisted_creds_reloaded(tmp_path, monkeypatch):
    c = AntennaClient(str(tmp_path), "secret-key")
    monkeypatch.setattr(c, "_request", _fake_ok)
    c.connect("192.168.1.11", "motdepasse")
    c2 = AntennaClient(str(tmp_path), "secret-key")
    c2.load_persisted()
    assert c2.ip == "192.168.1.11"
    monkeypatch.setattr(c2, "_request", _fake_ok)
    assert len(c2.fetch_beltpacks()) == 2          # prouve que le mdp déchiffré marche


def test_wrong_key_ignores_creds(tmp_path, monkeypatch):
    c = AntennaClient(str(tmp_path), "secret-key")
    monkeypatch.setattr(c, "_request", _fake_ok)
    c.connect("192.168.1.11", "motdepasse")
    other = AntennaClient(str(tmp_path), "AUTRE-CLE")
    other.load_persisted()
    assert other.ip is None                         # creds illisibles → ignorés


def test_fetch_beltpacks_parses_registered_only(tmp_path, monkeypatch):
    c = AntennaClient(str(tmp_path), "secret-key")
    monkeypatch.setattr(c, "_request", _fake_ok)
    c.connect("192.168.1.11", "")
    bps = c.fetch_beltpacks()
    assert bps == [
        {"number": "5", "name": "Régie Son", "online": True},
        {"number": "7", "name": "Lumière", "online": False},
    ]
```

- [ ] **Step 2: Lancer (échoue)** — `.venv/bin/pytest tests/test_antenna.py -q` → FAIL.

- [ ] **Step 3: Implémenter `antenna.py`**

```python
import base64
import hashlib
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone

from cryptography.fernet import Fernet


class AntennaError(Exception):
    pass


class AntennaClient:
    def __init__(self, data_dir, secret_key):
        self._secret_key = secret_key or "dev-insecure-key"
        self.path = os.path.join(data_dir, "antenna.json")
        self._ip = None
        self._password = None
        self._connected = False
        self._info = {}

    @property
    def connected(self):
        return self._connected

    @property
    def ip(self):
        return self._ip

    def _fernet(self):
        key = base64.urlsafe_b64encode(hashlib.sha256(self._secret_key.encode()).digest())
        return Fernet(key)

    def _request(self, method, path, body=None, timeout=5):
        if not self._ip:
            return False, {"error": "not connected"}
        url = f"http://{self._ip}{path}"
        data = json.dumps(body).encode() if body is not None else None
        headers = {}
        if data:
            headers["Content-Type"] = "application/json"
        if self._password:
            creds = base64.b64encode(f"admin:{self._password}".encode()).decode()
            headers["Authorization"] = f"Basic {creds}"
        try:
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                return True, (json.loads(raw) if raw and raw.strip() else {})
        except urllib.error.HTTPError as e:
            return False, {"error": f"HTTP {e.code}"}
        except Exception as e:
            return False, {"error": str(e)}

    def connect(self, ip, password):
        self._ip = (ip or "").strip()
        self._password = password or ""
        if not self._ip:
            self._ip = None
            raise AntennaError("IP requise")
        ok, data = self._request("GET", "/rest/nodeStatus", timeout=4)
        if not ok:
            self._ip = None
            self._password = None
            raise AntennaError(data.get("error", "Connexion échouée — vérifiez IP et mot de passe"))
        ok2, fw = self._request("GET", "/rest/firmware")
        nodes = data.get("nodeStatus", [])
        local = next((n for n in nodes if n.get("isLocal")), nodes[0] if nodes else {})
        self._info = {"nodes": nodes, "local": local,
                      "firmware": fw.get("firmware", {}) if ok2 else {}}
        self._connected = True
        self._persist()
        return self._info

    def disconnect(self):
        self._ip = self._password = None
        self._connected = False
        self._info = {}
        if os.path.exists(self.path):
            os.unlink(self.path)

    def reconnect(self):
        """Re-teste la connexion avec les identifiants déjà en mémoire."""
        if not self._ip:
            return False
        try:
            self.connect(self._ip, self._password or "")
            return True
        except AntennaError:
            return False

    def status(self):
        return {"connected": self._connected, "ip": self._ip, "info": self._info}

    def fetch_beltpacks(self):
        ok, data = self._request("GET", "/rest/bp")
        if not ok:
            raise AntennaError(data.get("error", "Lecture des beltpacks impossible"))
        out = []
        for bp in data.get("bp", []):
            if not bp.get("registered"):
                continue
            cfg = bp.get("bpConfig", {})
            num = cfg.get("bpNumber")
            if num is None:
                continue
            out.append({"number": str(num), "name": cfg.get("bpName", "") or "",
                        "online": bool(bp.get("connectedNodeId"))})
        return out

    def _persist(self):
        token = self._fernet().encrypt(self._password.encode()).decode() if self._password else ""
        payload = {"ip": self._ip, "password_enc": token, "info": self._info,
                   "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False, indent=2))
        os.chmod(self.path, 0o600)

    def load_persisted(self):
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError):
            return
        ip = data.get("ip")
        token = data.get("password_enc") or ""
        password = ""
        if token:
            try:
                password = self._fernet().decrypt(token.encode()).decode()
            except Exception:
                return  # clé changée / corrompu → on ignore les creds
        self._ip = ip
        self._password = password
        self._info = data.get("info", {})
```

- [ ] **Step 4: Lancer (passe)** — `.venv/bin/pytest tests/test_antenna.py -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add comroster/services/antenna.py tests/test_antenna.py
git commit -m "feat(bolero): client antenne — Basic Auth, creds chiffrés Fernet, fetch beltpacks"
```

---

## Task 4: Blueprint API + câblage factory (garde flag, reconnexion lazy)

**Files:**
- Create: `comroster/antenna.py`
- Modify: `comroster/__init__.py`
- Test: `tests/test_antenna_api.py`

**Interfaces:**
- Consumes: `Settings` (`.get/.set`), `AntennaClient` (`.connect/.disconnect/.status/.fetch_beltpacks/.reconnect/.load_persisted/.ip/.connected`), `Storage` (`.load_draft/.save_draft`), `model.diff_beltpacks/.merge_beltpacks`, `login_required`.
- Produces (toutes `login_required`) :
  - `GET /api/settings` → `{bolero_enabled}` ; `PUT /api/settings {bolero_enabled}` (désactivation → `disconnect`).
  - `POST /api/antenna/connect {ip,password}` → 200 `{connected,info}` / 400 / 502 ; `POST /api/antenna/disconnect` → 200.
  - `GET /api/antenna/status` → `{connected,ip,info}` (tente `reconnect()` si creds chargés mais non connecté).
  - `POST /api/antenna/import/preview` → `diff_beltpacks` ; `POST /api/antenna/import/apply` → `merge_beltpacks` + save draft.
  - Flag off ⇒ tous les `/api/antenna/*` → **409** `{"error":"bolero_disabled"}`.
- `app.extensions["settings"]`, `app.extensions["antenna"]`.

- [ ] **Step 1: Écrire les tests (échouent)**

`tests/test_antenna_api.py` :
```python
import pytest


def _fake_ok(method, path, body=None, timeout=5):
    if path == "/rest/nodeStatus":
        return True, {"nodeStatus": [{"nodeId": 1, "isLocal": True}]}
    if path == "/rest/firmware":
        return True, {"firmware": {"version": "3.4.1-15"}}
    if path == "/rest/bp":
        return True, {"bp": [
            {"registered": True, "id": 1, "connectedNodeId": 1,
             "bpConfig": {"bpNumber": 5, "bpName": "Régie Son"}},
            {"registered": True, "id": 2, "connectedNodeId": 0,
             "bpConfig": {"bpNumber": 7, "bpName": "Lumière"}},
        ]}
    return False, {"error": "unexpected"}


@pytest.fixture
def auth_client(client):
    client.post("/admin/setup", data={"password": "motdepasse8"})
    return client


def test_disabled_by_default_returns_409(auth_client):
    assert auth_client.get("/api/settings").get_json() == {"bolero_enabled": False}
    assert auth_client.get("/api/antenna/status").status_code == 409
    assert auth_client.post("/api/antenna/connect", json={"ip": "x", "password": "y"}).status_code == 409


def test_enable_connect_import_flow(auth_client, app, monkeypatch):
    auth_client.put("/api/settings", json={"bolero_enabled": True})
    monkeypatch.setattr(app.extensions["antenna"], "_request", _fake_ok)

    r = auth_client.post("/api/antenna/connect", json={"ip": "192.168.1.11", "password": "pw"})
    assert r.status_code == 200 and r.get_json()["connected"] is True

    preview = auth_client.post("/api/antenna/import/preview").get_json()
    assert len(preview["new"]) == 2 and preview["unchanged"] == 0

    applied = auth_client.post("/api/antenna/import/apply").get_json()
    assert applied == {"created": 2, "updated": 0}

    state = auth_client.get("/api/state").get_json()
    assert sorted(p["beltpack"] for p in state["people"]) == ["5", "7"]


def test_connect_failure_502(auth_client, app, monkeypatch):
    auth_client.put("/api/settings", json={"bolero_enabled": True})
    monkeypatch.setattr(app.extensions["antenna"], "_request", lambda *a, **k: (False, {"error": "timeout"}))
    r = auth_client.post("/api/antenna/connect", json={"ip": "10.0.0.9", "password": "x"})
    assert r.status_code == 502


def test_disable_disconnects(auth_client, app, monkeypatch):
    auth_client.put("/api/settings", json={"bolero_enabled": True})
    monkeypatch.setattr(app.extensions["antenna"], "_request", _fake_ok)
    auth_client.post("/api/antenna/connect", json={"ip": "192.168.1.11", "password": "pw"})
    auth_client.put("/api/settings", json={"bolero_enabled": False})
    assert app.extensions["antenna"].connected is False
```

- [ ] **Step 2: Lancer (échoue)** — `.venv/bin/pytest tests/test_antenna_api.py -q` → FAIL.

- [ ] **Step 3: Implémenter le blueprint `comroster/antenna.py`**

```python
from flask import Blueprint, request, jsonify, current_app

from .security import login_required
from .services import model
from .services.antenna import AntennaError

bp = Blueprint("antenna", __name__)


def _settings():
    return current_app.extensions["settings"]


def _client():
    return current_app.extensions["antenna"]


def _storage():
    return current_app.extensions["storage"]


def _enabled():
    return bool(_settings().get("bolero_enabled", False))


def _guard():
    if not _enabled():
        return jsonify({"error": "bolero_disabled"}), 409
    return None


@bp.get("/api/settings")
@login_required
def get_settings():
    return jsonify({"bolero_enabled": _enabled()})


@bp.put("/api/settings")
@login_required
def put_settings():
    data = request.get_json(force=True)
    enabled = bool(data.get("bolero_enabled"))
    _settings().set("bolero_enabled", enabled)
    if not enabled:
        _client().disconnect()
    return jsonify({"bolero_enabled": enabled})


@bp.post("/api/antenna/connect")
@login_required
def antenna_connect():
    guard = _guard()
    if guard:
        return guard
    data = request.get_json(force=True)
    ip = (data.get("ip") or "").strip()
    password = data.get("password") or ""
    if not ip:
        return jsonify({"error": "IP requise"}), 400
    try:
        info = _client().connect(ip, password)
    except AntennaError as exc:
        return jsonify({"error": str(exc)}), 502
    return jsonify({"connected": True, "info": info})


@bp.post("/api/antenna/disconnect")
@login_required
def antenna_disconnect():
    guard = _guard()
    if guard:
        return guard
    _client().disconnect()
    return jsonify({"connected": False})


@bp.get("/api/antenna/status")
@login_required
def antenna_status():
    guard = _guard()
    if guard:
        return guard
    client = _client()
    if client.ip and not client.connected:
        client.reconnect()
    return jsonify(client.status())


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
    state = _storage().load_draft()
    result = model.merge_beltpacks(state, items)
    _storage().save_draft(state)
    return jsonify(result)
```

- [ ] **Step 4: Câbler la factory**

Dans `comroster/__init__.py`, après `app.extensions["history"] = ...` :
```python
    from .services.settings import Settings
    from .services.antenna import AntennaClient
    app.extensions["settings"] = Settings(app.extensions["storage"])
    app.extensions["antenna"] = AntennaClient(app.config["DATA_DIR"], app.config.get("SECRET_KEY", ""))
    if app.extensions["settings"].get("bolero_enabled", False):
        app.extensions["antenna"].load_persisted()  # reconnexion lazy (testée au 1er /status)
```
Et après l'enregistrement de `display_bp` :
```python
    from .antenna import bp as antenna_bp
    app.register_blueprint(antenna_bp)
```

- [ ] **Step 5: Lancer (passe)** — `.venv/bin/pytest tests/test_antenna_api.py -q` → PASS.

- [ ] **Step 6: Suite complète + commit**

```bash
.venv/bin/pytest -q
git add comroster/antenna.py comroster/__init__.py tests/test_antenna_api.py
git commit -m "feat(bolero): API settings + antenna (connect/status/import), garde flag, câblage factory"
```

---

## Task 5: UI admin — toolbar regroupée, dialog Réglages, dialog Récap

**Files:**
- Modify: `templates/admin.html`, `static/js/admin.js`, `static/css/admin.css`
- Test: `tests/test_ui.py` (ajout), vérification manuelle contre le mock server

**Interfaces:**
- Consomme l'API de la Task 4. Réutilise les helpers existants de `admin.js` : `apiSend(method,url,body)`, `toast(msg,error)`, `esc(s)`, `load()`, `setUnpublished(bool)`.

- [ ] **Step 1: Toolbar regroupée + bouton Réglages**

Dans `templates/admin.html`, remplacer le contenu de `<div class="admin-toolbar">…</div>` par :
```html
    <div class="admin-toolbar">
      <div class="tb-group">
        <button type="button" id="add-block-btn">+ Groupe</button>
        <button type="button" id="add-user-btn">+ Personne</button>
      </div>
      <span class="tb-sep" aria-hidden="true"></span>
      <div class="tb-group">
        <button type="button" id="edit-meta-btn">Infos</button>
        <button type="button" id="toggle-theme-btn">Écran : nuit</button>
        <button type="button" id="history-btn">Historique</button>
      </div>
      <span class="tb-sep" aria-hidden="true"></span>
      <div class="tb-group">
        <button type="button" id="export-btn">Exporter</button>
        <label class="import-label">Importer<input type="file" id="import-input" accept="application/json"></label>
      </div>
      <span class="toolbar-spacer" aria-hidden="true"></span>
      <button type="button" id="settings-btn">⚙ Réglages</button>
      <button type="button" id="publish-btn" class="primary">Publier vers l'affichage</button>
      <a class="logout-link" href="{{ url_for('auth.logout') }}"
         onclick="event.preventDefault(); document.getElementById('logout-form').submit();">Déconnexion</a>
      <form id="logout-form" method="post" action="{{ url_for('auth.logout') }}" hidden>
        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
      </form>
    </div>
```

- [ ] **Step 2: Ajouter les dialogs Réglages et Récap**

Dans `templates/admin.html`, juste avant `<footer>` :
```html
  <dialog id="settings-dialog" class="admin-dialog">
    <form method="dialog">
      <h2>Réglages</h2>
      <label class="switch-row">
        <span>Intégration réseau Bolero</span>
        <input type="checkbox" id="bolero-enabled" class="switch">
      </label>
      <div id="antenna-block" hidden>
        <hr class="dlg-sep">
        <div id="antenna-disconnected">
          <p class="dialog-hint">Connectez ComRoster à une antenne du réseau intercom.</p>
          <label class="field"><span>Adresse IP</span>
            <input type="text" id="antenna-ip" placeholder="192.168.1.11" autocomplete="off"></label>
          <label class="field"><span>Mot de passe</span>
            <input type="password" id="antenna-password" autocomplete="off"></label>
          <button type="button" id="antenna-connect-btn" class="primary">Connecter</button>
          <p id="antenna-error" class="auth-error" hidden></p>
        </div>
        <div id="antenna-connected" hidden>
          <p id="antenna-info" class="dialog-hint"></p>
          <div class="dialog-actions" style="justify-content:flex-start">
            <button type="button" id="antenna-import-btn" class="primary">Importer les beltpacks</button>
            <button type="button" id="antenna-disconnect-btn">Déconnecter</button>
          </div>
        </div>
      </div>
      <div class="dialog-actions"><button type="button" data-close="settings-dialog">Fermer</button></div>
    </form>
  </dialog>

  <dialog id="import-dialog" class="admin-dialog">
    <form method="dialog">
      <h2>Récapitulatif de l'import</h2>
      <ul id="import-summary" class="import-summary"></ul>
      <div class="dialog-actions">
        <button type="button" id="import-apply-btn" class="primary">Appliquer</button>
        <button type="button" data-close="import-dialog">Annuler</button>
      </div>
    </form>
  </dialog>
```

- [ ] **Step 3: Styles (toolbar groupée, interrupteur, récap)**

Ajouter à la fin de `static/css/admin.css` :
```css
/* ---------- Toolbar groupée ---------- */
.tb-group { display: flex; gap: 0.4rem; }
.tb-sep { width: 1px; align-self: stretch; background: #2a3550; margin: 0 0.1rem; }

/* ---------- Interrupteur ---------- */
.switch-row { display: flex; align-items: center; justify-content: space-between; gap: 1rem; font-weight: 600; }
.switch { appearance: none; -webkit-appearance: none; width: 2.4rem; height: 1.35rem; border-radius: 999px; background: #2a3550; position: relative; cursor: pointer; transition: background .15s; flex: 0 0 auto; }
.switch:checked { background: var(--primary); }
.switch::after { content: ""; position: absolute; top: 2px; left: 2px; width: 1.05rem; height: 1.05rem; border-radius: 50%; background: #fff; transition: left .15s; }
.switch:checked::after { left: 1.2rem; }
.dlg-sep { border: none; border-top: 1px solid #243049; margin: 0.6rem 0; }
#antenna-block { display: flex; flex-direction: column; gap: 0.7rem; }
#antenna-error { margin: 0.4rem 0 0; }

/* ---------- Récap import ---------- */
.import-summary { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 0.4rem; }
.import-summary li { padding: 0.5rem 0.6rem; background: #0c111d; border: 1px solid #243049; border-radius: 7px; font-size: 0.85rem; }
```

- [ ] **Step 4: Logique JS (réglages, connexion, import)**

Ajouter dans `static/js/admin.js`, juste avant le bloc `/* ---------- Init ---------- */` :
```javascript
  /* ---------- Réglages & intégration Bolero ---------- */
  const settingsDialog = document.getElementById("settings-dialog");
  const boleroToggle = document.getElementById("bolero-enabled");
  const antennaBlock = document.getElementById("antenna-block");

  async function refreshAntenna() {
    let st;
    try { st = await apiSend("GET", "/api/antenna/status"); } catch { return; }
    document.getElementById("antenna-connected").hidden = !st.connected;
    document.getElementById("antenna-disconnected").hidden = !!st.connected;
    if (st.connected) {
      const fw = st.info?.firmware?.version || "?";
      const name = st.info?.local?.name || st.ip;
      document.getElementById("antenna-info").textContent = `Connecté à ${name} · firmware ${fw}`;
    }
  }

  async function openSettings() {
    const s = await apiSend("GET", "/api/settings");
    boleroToggle.checked = !!s.bolero_enabled;
    antennaBlock.hidden = !s.bolero_enabled;
    if (s.bolero_enabled) await refreshAntenna();
    settingsDialog.showModal();
  }

  boleroToggle.addEventListener("change", async () => {
    const s = await apiSend("PUT", "/api/settings", { bolero_enabled: boleroToggle.checked });
    antennaBlock.hidden = !s.bolero_enabled;
    if (s.bolero_enabled) await refreshAntenna();
  });

  document.getElementById("antenna-connect-btn").addEventListener("click", async () => {
    const ip = document.getElementById("antenna-ip").value.trim();
    const password = document.getElementById("antenna-password").value;
    const errEl = document.getElementById("antenna-error");
    errEl.hidden = true;
    try {
      await apiSend("POST", "/api/antenna/connect", { ip, password });
      await refreshAntenna();
    } catch (e) {
      errEl.textContent = e.payload?.error || "Connexion échouée";
      errEl.hidden = false;
    }
  });

  document.getElementById("antenna-disconnect-btn").addEventListener("click", async () => {
    try { await apiSend("POST", "/api/antenna/disconnect"); } finally { await refreshAntenna(); }
  });

  document.getElementById("antenna-import-btn").addEventListener("click", async () => {
    let p;
    try { p = await apiSend("POST", "/api/antenna/import/preview"); }
    catch { toast("Lecture des beltpacks impossible", true); return; }
    const li = [];
    li.push(`<li><b>${p.new.length}</b> nouveau(x)${p.new.length ? " : " + p.new.map((n) => esc(`#${n.number} ${n.name}`)).join(", ") : ""}</li>`);
    li.push(`<li><b>${p.changed.length}</b> rôle(s) mis à jour${p.changed.length ? " : " + p.changed.map((c) => esc(`#${c.number} ${c.old_role}→${c.new_role}`)).join(", ") : ""}</li>`);
    li.push(`<li><b>${p.unchanged}</b> inchangé(s)</li>`);
    li.push(`<li><b>${p.missing.length}</b> absent(s) de l'antenne (conservés)</li>`);
    document.getElementById("import-summary").innerHTML = li.join("");
    document.getElementById("import-dialog").showModal();
  });

  document.getElementById("import-apply-btn").addEventListener("click", async () => {
    try {
      const res = await apiSend("POST", "/api/antenna/import/apply");
      document.getElementById("import-dialog").close();
      settingsDialog.close();
      setUnpublished(true);
      await load();
      toast(`Import : ${res.created} créé(s), ${res.updated} mis à jour`);
    } catch { toast("Import impossible", true); }
  });

  document.getElementById("settings-btn").addEventListener("click", openSettings);
```

- [ ] **Step 5: Test de rendu**

Ajouter à `tests/test_ui.py` :
```python
def test_admin_has_settings_and_import_dialogs(auth_client):
    html = auth_client.get("/admin").get_data(as_text=True)
    assert "settings-dialog" in html
    assert "bolero-enabled" in html
    assert "⚙ Réglages" in html
    assert "import-dialog" in html
```
Run: `.venv/bin/pytest tests/test_ui.py -q` → PASS.

- [ ] **Step 6: Vérification manuelle contre le mock server**

Terminal A (faux antenne) :
```bash
cd "RIEDEL SOFTS/Riedel Bolero/Webapp" && .venv/bin/pip install -q tornado && python3 bolero_mock_server.py --port 8090
```
Terminal B (ComRoster) : `./run-dev.sh`
Dans `/admin` → ⚙ Réglages → activer l'interrupteur → IP `127.0.0.1:8090` (ou l'IP du mock), mot de passe quelconque → Connecter → « Importer les beltpacks » → vérifier le récap → Appliquer → les fiches apparaissent dans le pool. Désactiver l'interrupteur → le bloc Antenne disparaît, l'admin redevient standard.
> Note : le mock écoute sur un port ≠ 80 ; pour un test réaliste de bout en bout, l'IP saisie inclut le port (`127.0.0.1:8090`). En production l'antenne réelle est sur le port 80 (IP seule).

- [ ] **Step 7: Commit**

```bash
git add templates/admin.html static/js/admin.js static/css/admin.css tests/test_ui.py
git commit -m "feat(bolero): UI admin — réglages (interrupteur), connexion antenne, import avec récap"
```

---

## Self-review (couverture du spec)

- Feature flag `bolero_enabled` (défaut false, toggle, persistance) → Task 1 + Task 4.
- Garde flag → 409 sur `/api/antenna/*` → Task 4 (`_guard`).
- Client Basic Auth + test connexion + creds chiffrés Fernet + jamais en clair → Task 3.
- Reconnexion lazy (load au boot, test au 1er status) → Task 3 (`load_persisted`/`reconnect`) + Task 4 (factory + status).
- Import « fiches au pool » + synchro (création/maj rôle/préservation nom) → Task 2 (`merge_beltpacks`).
- Récap avant application (preview/apply) → Task 2 (`diff_beltpacks`) + Task 4 + Task 5.
- Mapping bpNumber→beltpack, bpName→rôle, nom vide → Task 2 + Task 3 (`fetch_beltpacks`).
- UI toolbar regroupée + dialogs → Task 5.
- Sécurité (login_required, mdp jamais renvoyé, fichiers gitignored, perms 600) → Task 1 (.gitignore) + Task 3 (perms, status) + Task 4 (login_required).
- Dépendance `cryptography` → Task 1.

**Notes de cohérence vérifiées :** `apiSend` (et non `api`) est le helper de `admin.js` ; les erreurs exposent `err.payload.error` ; `model.now_iso` non requis dans `antenna.py` (datetime direct) ; signatures `merge_beltpacks`/`diff_beltpacks` identiques entre Task 2, Task 4 et tests.



