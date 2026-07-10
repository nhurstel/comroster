# Déploiement 2 Pi (serveur + afficheur) — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permettre à l'installation de choisir le rôle d'un boîtier (autonome / serveur / afficheur), l'afficheur se branchant sur un Pi serveur distant par IP, avec une page de configuration locale à l'écran.

**Architecture:** Le code serveur Flask ne change pas. On ajoute (1) un agent de config Python autonome sur l'afficheur (`http.server` + segno), (2) un fichier `viewer.json` décrivant le serveur visé, (3) un menu de rôle dans `setup-pi.sh` avec installation conditionnelle des services, (4) une logique de bascule dans `kiosk-run.sh`. Spec : `docs/superpowers/specs/2026-07-10-deux-pi-serveur-afficheur-design.md`.

**Tech Stack:** Python 3.12 (bibliothèque standard `http.server` pour l'agent), segno (QR), bash (scripts de déploiement), pytest.

## Global Constraints

- **Le mode Autonome reste le défaut et ne doit jamais régresser** — les 218 tests existants restent verts à chaque tâche.
- **L'agent afficheur n'exécute que la stdlib + segno + les modules `services` (netconfig, viewer)** — il ne démarre JAMAIS Flask/gunicorn. L'install afficheur pose les mêmes dépendances (`requirements.txt`, qui contient déjà segno) car le paquet `comroster` importe Flask au chargement ; Flask est présent mais jamais lancé sur l'afficheur (quelques Mo sur la SD, zéro coût runtime — la simplicité prime sur l'économie de disque).
- **L'agent tourne en utilisateur (jamais root)** : il n'écrit que des fichiers dans `DATA_DIR` (user-owned), appliqués au reboot par les services système.
- **Agent sans authentification** — réseau de régie isolé de confiance (même posture que `COMROSTER_INSECURE_COOKIE`), documenté.
- **TDD strict** : test rouge constaté avant chaque implémentation. Réutiliser `netconfig.validate` pour valider les IP (ne pas réécrire de validation).
- Port de l'agent afficheur : **8081**. Port du serveur ComRoster : **8080**.
- Écritures de fichiers de config atomiques (`tempfile` + `os.replace`), fichiers en `0600` comme l'existant.

---

### Task 1: Modèle `viewer.json` (config du serveur visé par l'afficheur)

Petit module qui lit/écrit/valide la cible serveur de l'afficheur. Isolé, testable sans réseau.

**Files:**
- Create: `comroster/services/viewer.py`
- Test: `tests/test_viewer_config.py`

**Interfaces:**
- Consumes: `comroster.services.netconfig.validate` (validation IP existante — non, on valide l'IP serveur directement avec `ipaddress`).
- Produces:
  - `ViewerConfig(data_dir)` avec `.load() -> dict` (défaut `{"server_ip": "", "server_port": 8080}`), `.save(cfg) -> dict` (lève `ValueError` si IP invalide), `.display_url() -> str|None` (None si pas d'IP), `.health_url() -> str|None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_viewer_config.py
import pytest
from comroster.services.viewer import ViewerConfig


def test_default_is_empty(tmp_path):
    vc = ViewerConfig(str(tmp_path))
    assert vc.load() == {"server_ip": "", "server_port": 8080}
    assert vc.display_url() is None
    assert vc.health_url() is None


def test_save_and_urls(tmp_path):
    vc = ViewerConfig(str(tmp_path))
    vc.save({"server_ip": "192.168.42.10", "server_port": 8080})
    assert vc.load()["server_ip"] == "192.168.42.10"
    assert vc.display_url() == "http://192.168.42.10:8080/display"
    assert vc.health_url() == "http://192.168.42.10:8080/healthz"


def test_save_rejects_bad_ip(tmp_path):
    vc = ViewerConfig(str(tmp_path))
    with pytest.raises(ValueError):
        vc.save({"server_ip": "pas-une-ip", "server_port": 8080})


def test_save_rejects_bad_port(tmp_path):
    vc = ViewerConfig(str(tmp_path))
    with pytest.raises(ValueError):
        vc.save({"server_ip": "192.168.42.10", "server_port": 70000})


def test_corrupt_file_falls_back_to_default(tmp_path):
    vc = ViewerConfig(str(tmp_path))
    with open(vc.path, "w") as fh:
        fh.write("{ pas du json")
    assert vc.load() == {"server_ip": "", "server_port": 8080}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_viewer_config.py -q`
Expected: FAIL (ModuleNotFoundError: comroster.services.viewer)

- [ ] **Step 3: Write minimal implementation**

```python
# comroster/services/viewer.py
import ipaddress
import json
import os


class ViewerConfig:
    """Cible serveur d'un Pi afficheur (mode 2 Pi). Écrit un JSON simple lu par
    kiosk-run.sh pour savoir quel serveur distant afficher."""

    def __init__(self, data_dir):
        os.makedirs(data_dir, exist_ok=True)
        self.path = os.path.join(data_dir, "viewer.json")

    def load(self):
        cfg = {"server_ip": "", "server_port": 8080}
        if os.path.exists(self.path):
            try:
                with open(self.path, encoding="utf-8") as fh:
                    cfg.update(json.load(fh))
            except (OSError, json.JSONDecodeError):
                return {"server_ip": "", "server_port": 8080}
        return cfg

    def save(self, cfg):
        ip = (cfg.get("server_ip") or "").strip()
        try:
            ipaddress.ip_address(ip)
        except ValueError:
            raise ValueError("Adresse IP du serveur invalide")
        port = cfg.get("server_port", 8080)
        if not (isinstance(port, int) and not isinstance(port, bool) and 1 <= port <= 65535):
            raise ValueError("Port serveur invalide")
        data = {"server_ip": ip, "server_port": port}
        tmp = self.path + ".tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)
        return data

    def _base(self):
        cfg = self.load()
        if not cfg["server_ip"]:
            return None
        return f"http://{cfg['server_ip']}:{cfg['server_port']}"

    def display_url(self):
        base = self._base()
        return f"{base}/display" if base else None

    def health_url(self):
        base = self._base()
        return f"{base}/healthz" if base else None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_viewer_config.py -q`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add comroster/services/viewer.py tests/test_viewer_config.py
git commit -m "feat(viewer): config de la cible serveur pour le Pi afficheur"
```

---

### Task 2: Test de joignabilité du serveur distant

Fonction pure (testable avec un serveur HTTP mocké) qui dit si le serveur répond. Séparée pour être testable sans l'agent HTTP complet.

**Files:**
- Modify: `comroster/services/viewer.py`
- Test: `tests/test_viewer_config.py`

**Interfaces:**
- Produces: `probe_server(health_url, timeout=2.0) -> bool` (module-level dans `viewer.py`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_viewer_config.py  (ajouter)
import http.server
import threading
from comroster.services.viewer import probe_server


def _serve_once(status):
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(status)
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')
        def log_message(self, *a):
            pass
    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]


def test_probe_reachable():
    srv, port = _serve_once(200)
    try:
        assert probe_server(f"http://127.0.0.1:{port}/healthz") is True
    finally:
        srv.shutdown()


def test_probe_unreachable():
    # port fermé : rien n'écoute
    assert probe_server("http://127.0.0.1:59999/healthz", timeout=0.5) is False


def test_probe_none_url():
    assert probe_server(None) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_viewer_config.py -k probe -q`
Expected: FAIL (ImportError: cannot import name 'probe_server')

- [ ] **Step 3: Write minimal implementation**

```python
# comroster/services/viewer.py  (ajouter en tête après les imports)
import urllib.request
import urllib.error


def probe_server(health_url, timeout=2.0):
    """True si le serveur ComRoster distant répond sur son /healthz."""
    if not health_url:
        return False
    try:
        with urllib.request.urlopen(health_url, timeout=timeout) as resp:
            return 200 <= resp.status < 400
    except (urllib.error.URLError, OSError, ValueError):
        return False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_viewer_config.py -q`
Expected: PASS (8 passed)

- [ ] **Step 5: Commit**

```bash
git add comroster/services/viewer.py tests/test_viewer_config.py
git commit -m "feat(viewer): sonde de joignabilité du serveur distant"
```

---

### Task 3: Agent de config afficheur — routes API (sans rendu HTML)

Le cœur logique de l'agent : les routes `/api/server-status` et `POST /config`, testées via le test client HTTP de la stdlib. Le HTML vient en Task 4.

**Files:**
- Create: `comroster/viewer_agent.py`
- Test: `tests/test_viewer_agent.py`

**Interfaces:**
- Consumes: `ViewerConfig`, `probe_server` (Task 1-2), `comroster.services.netconfig.NetConfig` + `validate` (réseau existant).
- Produces:
  - `make_handler(data_dir)` → classe handler `http.server.BaseHTTPRequestHandler` prête à servir.
  - `build_server(data_dir, port=8081)` → `http.server.HTTPServer`.
  - Routes : `GET /api/server-status` → JSON `{"reachable": bool, "display_url": str|None}` ; `POST /config` (form-urlencoded : `server_ip`, `network_mode`, `network_address`, `network_prefix`) → écrit viewer.json + network.json, renvoie 200 JSON `{"ok": true}` ou 400 `{"error": "..."}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_viewer_agent.py
import json
import threading
import urllib.request
import urllib.parse
import pytest
from comroster.viewer_agent import build_server


@pytest.fixture
def agent(tmp_path):
    srv = build_server(str(tmp_path), port=0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]
    yield f"http://127.0.0.1:{port}", tmp_path
    srv.shutdown()


def _get(base, path):
    with urllib.request.urlopen(base + path) as r:
        return r.status, r.read().decode()


def _post(base, path, fields):
    data = urllib.parse.urlencode(fields).encode()
    req = urllib.request.Request(base + path, data=data, method="POST")
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def test_server_status_unreachable_by_default(agent):
    base, _ = agent
    status, body = _get(base, "/api/server-status")
    assert status == 200
    payload = json.loads(body)
    assert payload["reachable"] is False
    assert payload["display_url"] is None


def test_post_config_writes_viewer_and_network(agent):
    base, tmp = agent
    status, body = _post(base, "/config", {
        "server_ip": "192.168.42.10",
        "network_mode": "static",
        "network_address": "192.168.42.50",
        "network_prefix": "24",
    })
    assert status == 200
    assert json.loads(body)["ok"] is True
    viewer = json.load(open(tmp / "viewer.json"))
    assert viewer["server_ip"] == "192.168.42.10"
    net = json.load(open(tmp / "network.json"))
    assert net["mode"] == "static" and net["address"] == "192.168.42.50"


def test_post_config_rejects_bad_server_ip(agent):
    base, _ = agent
    status, body = _post(base, "/config", {"server_ip": "nope", "network_mode": "dhcp"})
    assert status == 400
    assert "error" in json.loads(body)


def test_post_config_dhcp_no_address(agent):
    base, tmp = agent
    status, _ = _post(base, "/config", {"server_ip": "192.168.42.10", "network_mode": "dhcp"})
    assert status == 200
    assert json.load(open(tmp / "network.json"))["mode"] == "dhcp"
```

Note : ajouter `import urllib.error` en tête du test.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_viewer_agent.py -q`
Expected: FAIL (ModuleNotFoundError: comroster.viewer_agent)

- [ ] **Step 3: Write minimal implementation**

```python
# comroster/viewer_agent.py
import http.server
import json
import urllib.parse

from .services.viewer import ViewerConfig, probe_server
from .services.netconfig import NetConfig, validate as validate_network


def make_handler(data_dir):
    viewer = ViewerConfig(data_dir)
    netcfg = NetConfig(data_dir)

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _json(self, status, payload):
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path.startswith("/api/server-status"):
                reachable = probe_server(viewer.health_url(), timeout=1.5)
                return self._json(200, {
                    "reachable": reachable,
                    "display_url": viewer.display_url(),
                })
            return self._json(404, {"error": "not_found"})

        def do_POST(self):
            if self.path.rstrip("/") != "/config":
                return self._json(404, {"error": "not_found"})
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length).decode()
            form = {k: v[0] for k, v in urllib.parse.parse_qs(raw).items()}
            # 1. Cible serveur
            try:
                viewer.save({"server_ip": form.get("server_ip", ""),
                             "server_port": int(form.get("server_port", 8080))})
            except (ValueError, TypeError) as exc:
                return self._json(400, {"error": str(exc)})
            # 2. Réseau propre de l'afficheur (schéma NetConfig)
            net = {"link": "ethernet", "mode": form.get("network_mode", "link-local")}
            if net["mode"] == "static":
                net["address"] = form.get("network_address", "")
                net["prefix"] = int(form.get("network_prefix", 24))
            ok, err = validate_network(net)
            if not ok:
                return self._json(400, {"error": err})
            netcfg.save(net)
            return self._json(200, {"ok": True, "reboot_required": True})

    return Handler


def build_server(data_dir, port=8081):
    return http.server.HTTPServer(("0.0.0.0", port), make_handler(data_dir))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_viewer_agent.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add comroster/viewer_agent.py tests/test_viewer_agent.py
git commit -m "feat(viewer-agent): routes API config (server-status, POST config)"
```

---

### Task 4: Agent de config afficheur — pages HTML (boot + config + QR)

Ajoute les pages servies au navigateur : `/` (boot avec bannière 5 s), `/config` (formulaire), `/qr.svg`. Fichiers HTML/CSS servis directement par l'agent (pas de Jinja).

**Files:**
- Modify: `comroster/viewer_agent.py`
- Create: `comroster/viewer_pages.py` (HTML en constantes, sépare le markup de la logique)
- Test: `tests/test_viewer_agent.py`

**Interfaces:**
- Consumes: Task 3 handler.
- Produces: routes `GET /` (HTML page boot, contient le compte à rebours 5 s et l'appel JS à `/api/server-status`), `GET /config` (HTML formulaire), `GET /qr.svg` (image SVG du QR vers `/config`). `viewer_pages.boot_html(display_url)`, `viewer_pages.config_html(viewer_cfg, net_cfg)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_viewer_agent.py  (ajouter)
def test_boot_page_served(agent):
    base, _ = agent
    status, body = _get(base, "/")
    assert status == 200
    assert "server-status" in body        # le JS interroge l'agent
    assert "Configurer" in body           # bannière de config

def test_config_page_has_fields(agent):
    base, _ = agent
    status, body = _get(base, "/config")
    assert status == 200
    assert 'name="server_ip"' in body
    assert 'name="network_mode"' in body

def test_qr_is_svg(agent):
    base, _ = agent
    status, body = _get(base, "/qr.svg")
    assert status == 200
    assert "<svg" in body
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_viewer_agent.py -k "boot or config_page or qr" -q`
Expected: FAIL (404 → assertion errors)

- [ ] **Step 3: Write minimal implementation**

Create `comroster/viewer_pages.py` :

```python
# comroster/viewer_pages.py
def boot_html(display_url):
    # Page affichée par le kiosk au démarrage. Interroge l'agent (same-origin),
    # laisse 5 s pour aller à la config, sinon navigue vers le display distant.
    return """<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ComRoster — Afficheur</title>
<style>
 body{margin:0;height:100vh;display:flex;flex-direction:column;align-items:center;
 justify-content:center;background:#0A1628;color:#eaf1f9;font-family:system-ui,sans-serif}
 .count{font-size:1rem;color:#8aa0b8;margin-top:1.5rem}
 a.btn{margin-top:2rem;padding:.8rem 1.6rem;background:#3AAFA9;color:#04121b;
 border-radius:10px;text-decoration:none;font-weight:700}
 .err{color:#ff9;margin-top:1rem}
</style></head><body>
<h1>🎧 ComRoster — Afficheur</h1>
<div id="msg">Recherche du serveur…</div>
<a class="btn" href="/config">⚙ Configurer</a>
<div class="count" id="count"></div>
<script>
let left=5;
const msg=document.getElementById("msg"), count=document.getElementById("count");
async function tick(){
  let st={reachable:false,display_url:null};
  try{ st=await fetch("/api/server-status").then(r=>r.json()); }catch(e){}
  if(left<=0){
    if(st.reachable && st.display_url){ location.href=st.display_url; return; }
    location.href="/config"; return;
  }
  msg.textContent = st.reachable ? "Serveur trouvé — démarrage de l'affichage…"
                                 : "Serveur introuvable — ouverture de la configuration…";
  count.textContent = "("+left+"…)";
  left--; setTimeout(tick,1000);
}
tick();
</script></body></html>"""


def config_html(viewer_cfg, net_cfg):
    ip = viewer_cfg.get("server_ip", "")
    mode = net_cfg.get("mode", "link-local")
    addr = net_cfg.get("address", "")
    prefix = net_cfg.get("prefix", 24)
    def sel(m):
        return " selected" if mode == m else ""
    return f"""<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Configuration afficheur</title>
<style>
 body{{margin:0;min-height:100vh;background:#0A1628;color:#eaf1f9;
 font-family:system-ui,sans-serif;display:flex;justify-content:center}}
 form{{max-width:420px;width:100%;padding:2rem}}
 label{{display:block;margin:1rem 0 .3rem}}
 input,select{{width:100%;padding:.6rem;border-radius:8px;border:1px solid #2b3f57;
 background:#12203a;color:#eaf1f9;box-sizing:border-box}}
 button{{margin-top:1.5rem;width:100%;padding:.9rem;background:#3AAFA9;color:#04121b;
 border:none;border-radius:10px;font-weight:700;font-size:1rem}}
 .qr{{text-align:center;margin-bottom:1rem}}
 .ok{{color:#7CFFB2}}.err{{color:#ff9}}
</style></head><body><form method="POST" action="/config">
<h1>Configuration de l'afficheur</h1>
<div class="qr"><img src="/qr.svg" width="150" alt="QR config"></div>
<label>IP du serveur ComRoster</label>
<input name="server_ip" value="{ip}" placeholder="192.168.42.10" inputmode="decimal">
<label>Adresse réseau de cet afficheur</label>
<select name="network_mode" onchange="document.getElementById('st').hidden=this.value!=='static'">
 <option value="link-local"{sel('link-local')}>Automatique (link-local)</option>
 <option value="dhcp"{sel('dhcp')}>Automatique (DHCP)</option>
 <option value="static"{sel('static')}>IP fixe</option>
</select>
<div id="st" {'hidden' if mode != 'static' else ''}>
 <label>IP fixe de l'afficheur</label>
 <input name="network_address" value="{addr}" placeholder="192.168.42.50" inputmode="decimal">
 <label>Préfixe (CIDR)</label>
 <input name="network_prefix" type="number" min="1" max="32" value="{prefix}">
</div>
<button type="submit">Enregistrer et redémarrer</button>
</form></body></html>"""
```

Modify `comroster/viewer_agent.py` — ajouter dans `do_GET` (avant le 404 final), et l'import :

```python
# en tête
import io
import segno
from . import viewer_pages

# dans do_GET, après le bloc /api/server-status :
            if self.path == "/" or self.path.startswith("/?"):
                return self._html(200, viewer_pages.boot_html(viewer.display_url()))
            if self.path.rstrip("/") == "/config":
                return self._html(200, viewer_pages.config_html(viewer.load(), netcfg.load()))
            if self.path.startswith("/qr.svg"):
                buf = io.BytesIO()
                segno.make("http://%s:8081/config" % self._host_ip(), error="m").save(
                    buf, kind="svg", scale=5, border=2)
                self.send_response(200)
                self.send_header("Content-Type", "image/svg+xml")
                self.end_headers()
                self.wfile.write(buf.getvalue())
                return
```

Ajouter les helpers dans la classe Handler :

```python
        def _html(self, status, body):
            data = body.encode()
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _host_ip(self):
            # IP par laquelle le client nous joint (pour le QR pointant vers cet afficheur)
            host = self.headers.get("Host", "")
            return host.split(":")[0] or "comroster.local"
```

Note : `POST /config` doit renvoyer une page de confirmation HTML plutôt que du JSON quand le navigateur poste le formulaire. Adapter : si l'en-tête `Accept` contient `text/html`, répondre par une page « ✅ Enregistré — redémarrage… ». Garder le JSON pour les tests (qui n'envoient pas cet Accept). Ajouter dans `do_POST`, à la place du `return self._json(200, ...)` final :

```python
            if "text/html" in self.headers.get("Accept", ""):
                return self._html(200, "<!DOCTYPE html><meta charset=utf-8>"
                    "<body style='background:#0A1628;color:#7CFFB2;font-family:sans-serif;"
                    "text-align:center;padding-top:20vh'><h1>✅ Enregistré</h1>"
                    "<p>Redémarrez l'afficheur pour appliquer.</p></body>")
            return self._json(200, {"ok": True, "reboot_required": True})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_viewer_agent.py -q`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add comroster/viewer_agent.py comroster/viewer_pages.py tests/test_viewer_agent.py
git commit -m "feat(viewer-agent): pages boot (bannière 5 s), config et QR"
```

---

### Task 5: Point d'entrée exécutable de l'agent

Rend l'agent lançable par systemd (`python -m comroster.viewer_agent`).

**Files:**
- Modify: `comroster/viewer_agent.py`
- Test: `tests/test_viewer_agent.py`

**Interfaces:**
- Produces: `main()` lisant `DATA_DIR` (défaut `os.getcwd()/instance`) et `COMROSTER_VIEWER_PORT` (défaut 8081) depuis l'environnement, bloc `if __name__ == "__main__"`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_viewer_agent.py  (ajouter)
def test_main_callable_exists():
    from comroster import viewer_agent
    assert callable(viewer_agent.main)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_viewer_agent.py -k main_callable -q`
Expected: FAIL (AttributeError: module has no attribute 'main')

- [ ] **Step 3: Write minimal implementation**

```python
# comroster/viewer_agent.py  (ajouter en bas)
import os


def main():
    data_dir = os.environ.get("DATA_DIR", os.path.join(os.getcwd(), "instance"))
    port = int(os.environ.get("COMROSTER_VIEWER_PORT", "8081"))
    srv = build_server(data_dir, port=port)
    print(f"ComRoster viewer-agent sur 0.0.0.0:{port} (data={data_dir})")
    srv.serve_forever()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_viewer_agent.py -q`
Expected: PASS (8 passed)

- [ ] **Step 5: Commit**

```bash
git add comroster/viewer_agent.py tests/test_viewer_agent.py
git commit -m "feat(viewer-agent): point d'entrée exécutable (python -m)"
```

---

### Task 6: `kiosk-run.sh` — cibler l'agent local en profil afficheur

Le kiosk du profil afficheur pointe vers l'agent local (`http://127.0.0.1:8081/`) au lieu du serveur. La logique de bascule vit dans la page de l'agent.

**Files:**
- Modify: `deploy/kiosk-run.sh`

**Interfaces:**
- Consumes: variable d'environnement `COMROSTER_ROLE` (`autonomous` | `viewer`), écrite par `setup-pi.sh` (Task 7).

- [ ] **Step 1: Écrire la modification**

Dans `deploy/kiosk-run.sh`, remplacer la définition de `URL`/`HEALTH` par une sélection selon le rôle :

```bash
ROLE="${COMROSTER_ROLE:-autonomous}"
if [ "$ROLE" = "viewer" ]; then
  # Afficheur : le kiosk ouvre l'agent local, qui teste le serveur distant et
  # bascule (display distant ou page de config). Attente de l'agent, pas du serveur.
  URL="${COMROSTER_KIOSK_URL:-http://127.0.0.1:8081/}"
  HEALTH="${COMROSTER_HEALTH_URL:-http://127.0.0.1:8081/api/server-status}"
else
  URL="${COMROSTER_KIOSK_URL:-http://127.0.0.1:8080/display}"
  HEALTH="${COMROSTER_HEALTH_URL:-http://127.0.0.1:8080/healthz}"
fi
```

- [ ] **Step 2: Vérifier la syntaxe**

Run: `sh -n deploy/kiosk-run.sh && echo OK`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add deploy/kiosk-run.sh
git commit -m "feat(kiosk): profil afficheur → kiosk sur l'agent local"
```

---

### Task 7: `setup-pi.sh` — menu de rôle et installation conditionnelle

Ajoute le choix du profil et n'installe/active que les services voulus. Le service `comroster-viewer` (agent) est nouveau.

**Files:**
- Modify: `deploy/setup-pi.sh`
- Create: `deploy/comroster-viewer.service` (référence ; le script génère la version finale in-place)

**Interfaces:**
- Consumes: rien (interactif). Produces: `/etc/comroster.env` avec `COMROSTER_ROLE` ; services actifs selon le profil.

- [ ] **Step 1: Écrire la modification (menu + branches)**

Au début de `setup-pi.sh` (après la détection utilisateur), ajouter le menu :

```bash
echo "▶ Rôle de ce boîtier :"
echo "   1) Autonome  — serveur + affichage (défaut)"
echo "   2) Serveur   — données + admin seuls"
echo "   3) Afficheur — écran seul, se branche sur un serveur distant"
printf "Choix [1] : "
read -r ROLE_CHOICE </dev/tty || ROLE_CHOICE=1
case "${ROLE_CHOICE:-1}" in
  2) ROLE=server ;;
  3) ROLE=viewer ;;
  *) ROLE=autonomous ;;
esac
echo "▶ Rôle retenu : $ROLE"

SERVER_IP=""
if [ "$ROLE" = "viewer" ]; then
  printf "IP du Pi serveur (ex. 192.168.42.10) : "
  read -r SERVER_IP </dev/tty
fi
```

Ajouter `COMROSTER_ROLE=$ROLE` dans le bloc de génération de `/etc/comroster.env`.
Pour le profil `viewer`, écrire `instance/viewer.json` :

```bash
if [ "$ROLE" = "viewer" ] && [ -n "$SERVER_IP" ]; then
  install -d -o "$TARGET_USER" -g "$TARGET_USER" "$DATA_DIR"
  cat > "$DATA_DIR/viewer.json" <<JSON
{"server_ip": "$SERVER_IP", "server_port": 8080}
JSON
  chown "$TARGET_USER:$TARGET_USER" "$DATA_DIR/viewer.json"
fi
```

Rendre conditionnelle l'installation des services :
- `comroster.service` (serveur Flask) : installer/activer si `ROLE != viewer`.
- `comroster-kiosk.service` : installer/activer si `ROLE != server`.
- `comroster-viewer.service` (agent) : installer/activer si `ROLE = viewer` :

```bash
if [ "$ROLE" = "viewer" ]; then
  cat > "$KIOSK_DIR/comroster-viewer.service" <<EOF
[Unit]
Description=ComRoster — agent de configuration afficheur
After=network.target

[Service]
Type=simple
EnvironmentFile=$ENV_FILE
ExecStart=$VENV/bin/python -m comroster.viewer_agent
Restart=on-failure
RestartSec=3

[Install]
WantedBy=default.target
EOF
  sudo -u "$TARGET_USER" XDG_RUNTIME_DIR="/run/user/$TARGET_UID" \
    systemctl --user enable comroster-viewer.service || true
fi
```

Note : **pas de changement du `pip install`** — tous les profils installent `requirements.txt` (qui contient déjà `segno`). Sur l'afficheur, Flask est installé mais jamais lancé (voir Global Constraints). Cela garantit aussi que `python -m comroster.viewer_agent` peut charger le paquet `comroster` (dont l'`__init__` importe Flask).

- [ ] **Step 2: Vérifier la syntaxe**

Run: `bash -n deploy/setup-pi.sh && echo OK`
Expected: `OK`

- [ ] **Step 3: Vérifier que le mode autonome reste inchangé (suite complète)**

Run: `.venv/bin/python -m pytest -q -m "e2e or not e2e"`
Expected: PASS (tous verts — le code serveur n'a pas bougé)

- [ ] **Step 4: Commit**

```bash
git add deploy/setup-pi.sh deploy/comroster-viewer.service
git commit -m "feat(setup): menu de rôle (autonome/serveur/afficheur) + service agent"
```

---

### Task 8: Documentation 2 Pi

Met à jour la doc terrain avec le montage serveur/afficheur.

**Files:**
- Modify: `deploy/raspberry-pi.md`
- Modify: `deploy/aide-memoire-terrain.md`

- [ ] **Step 1: Écrire la section 2 Pi dans `raspberry-pi.md`**

Ajouter une section « Déploiement 2 Pi (serveur + afficheur) » : tableau des 3 profils, la procédure (installer le serveur d'abord, noter son IP, installer l'afficheur en saisissant cette IP), et le fonctionnement de la page de config afficheur (bannière 5 s au boot, QR de reconfiguration, reboot pour appliquer). Mentionner l'avertissement sécurité (agent sans auth, réseau isolé).

- [ ] **Step 2: Ajouter une entrée dans `aide-memoire-terrain.md`**

Dans le tableau de dépannage, ajouter : « Afficheur bloqué sur "Serveur introuvable" → vérifier `instance/viewer.json` et que le serveur répond sur `http://<ip-serveur>:8080/healthz` » ; et « Reconfigurer un afficheur → rebooter, appuyer sur ⚙ pendant les 5 s, ou scanner le QR ».

- [ ] **Step 3: Commit**

```bash
git add deploy/raspberry-pi.md deploy/aide-memoire-terrain.md
git commit -m "docs: procédure et dépannage du déploiement 2 Pi"
```

---

## Notes d'exécution / validation matérielle

Testable **sans Pi** (couvert par les tâches) : viewer.json, sonde serveur, routes et pages de l'agent, point d'entrée, syntaxe des scripts, non-régression du mode autonome.

À valider **sur Pi réel** (non simulable, à faire au banc de test) :
- Menu des 3 profils dans `setup-pi.sh`.
- Profil afficheur : bannière 5 s → bascule vers le display distant.
- Serveur injoignable → page de config affichée ; QR → config au téléphone.
- `POST /config` → reboot → nouvelle IP serveur + réseau appliqués.
