# Refonte UX de l'intégration antenne — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rendre l'intégration antenne découvrable et pro : un bouton dédié « 🛰 Antenne » à pastille d'état, un assistant guidé en 3 étapes au premier usage, puis un tableau de bord ; retrait du flag d'activation.

**Architecture:** Suppression du flag `bolero_enabled` (les routes `/api/antenna/*` restent `login_required` mais sans garde 409). L'UI antenne passe d'un dialog « Réglages » à un panneau dédié (`#antenna-dialog`) qui affiche un assistant (jamais configuré) ou un tableau de bord (déjà configuré), choisi via `GET /api/antenna/status`. Une pastille sur le bouton reflète l'état en continu.

**Tech Stack:** Python 3.12, Flask, pytest, JS vanilla, CSS. (Aucune nouvelle dépendance.)

**Spec de référence :** `docs/superpowers/specs/2026-06-21-antenna-ux-refonte-design.md`.

## Global Constraints

- **Retrait de `bolero_enabled`** : plus de garde 409 sur `/api/antenna/*` ; `settings` ne porte plus que `antenna_ranges`. `load_persisted()` au boot devient **inconditionnel**.
- **Point d'entrée** : bouton `#antenna-btn` (« 🛰 Antenne ») dans la barre, zone *données* (près de « Configs »), toujours visible, avec pastille `.dot` (`off` gris / `online` vert / `offline` orange).
- **Choix assistant vs tableau de bord** : `status.ip == null` → assistant ; sinon tableau de bord.
- **Assistant** 3 étapes : Connexion → Beltpacks à charger (plages) → Import (récap inline).
- **Tableau de bord** : blocs État / Filtre (numéros) / Actions (Actualiser, Déconnecter).
- **Ton pro et concis**, aucun texte « à quoi ça sert ».
- **Conservés** : `import-dialog` (récap modal pour *Actualiser*), `configs-dialog`, toute la logique backend de sync/plages/configs.
- **Sécurité** : endpoints `login_required` + CSRF, mot de passe jamais renvoyé.
- **TDD** sur le backend ; vérification manuelle de l'UI (faux serveur antenne).

---

## File Structure

| Fichier | Changement |
|---------|-----------|
| `comroster/antenna.py` | Retrait `_guard` + `bolero_enabled` (get/put settings, routes) |
| `comroster/__init__.py` | `load_persisted()` inconditionnel |
| `templates/admin.html` | Bouton + dialog antenne ; retrait bouton/dialog Réglages |
| `static/js/admin.js` | Badge, ouverture, assistant, tableau de bord ; retrait logique interrupteur |
| `static/css/admin.css` | Pastille, stepper d'assistant, blocs du tableau de bord |
| `tests/test_antenna_api.py` | Retrait des tests de garde flag + ajout statut sans config |

---

## Task 1: Backend — retrait du flag `bolero_enabled`

**Files:**
- Modify: `comroster/antenna.py`, `comroster/__init__.py`
- Test: `tests/test_antenna_api.py`

**Interfaces:**
- Produces : `GET /api/settings` → `{"antenna_ranges": [...]}` ; `PUT /api/settings {antenna_ranges}` ; `/api/antenna/*` sans garde 409 (toujours `login_required`).

- [ ] **Step 1: Mettre à jour les tests (rendre le retrait du flag attendu)**

Dans `tests/test_antenna_api.py` : **supprimer** les fonctions `test_disabled_by_default_returns_409` et `test_disable_disconnects`. **Remplacer** la 1ʳᵉ ligne de `test_enable_connect_import_flow` et des autres tests qui contiennent `auth_client.put("/api/settings", json={"bolero_enabled": True})` ou `{"bolero_enabled": True, ...}` :
- `test_enable_connect_import_flow` : retirer la ligne `auth_client.put("/api/settings", json={"bolero_enabled": True})`.
- `test_connect_failure_502` : idem retirer cette ligne.
- `test_ranges_filter_import` : remplacer `{"bolero_enabled": True, "antenna_ranges": [[1, 25]]}` par `{"antenna_ranges": [[1, 25]]}`.
- `test_apply_mirror_removes_absent` : retirer la ligne `put .../settings {"bolero_enabled": True}`.
- `test_configs_save_load_disconnects` : idem retirer cette ligne.

Ajouter le test du nouveau comportement :
```python
def test_settings_has_only_ranges(auth_client):
    assert auth_client.get("/api/settings").get_json() == {"antenna_ranges": []}


def test_antenna_status_ok_without_config(auth_client):
    # plus de garde 409 : status répond 200 même rien configuré
    r = auth_client.get("/api/antenna/status")
    assert r.status_code == 200 and r.get_json()["connected"] is False
```

- [ ] **Step 2: Lancer (échoue)** — `.venv/bin/pytest tests/test_antenna_api.py -q` → FAIL (status renvoie encore 409 ; settings contient `bolero_enabled`).

- [ ] **Step 3: Retirer la garde et le flag dans `comroster/antenna.py`**

Supprimer la fonction `_guard` et l'appel `guard = _guard(); if guard: return guard` au début de **chacune** des routes `antenna_connect`, `antenna_disconnect`, `antenna_status`, `antenna_import_preview`, `antenna_import_apply` (retirer ces deux lignes dans chaque fonction). Remplacer `get_settings`/`put_settings` par :
```python
@bp.get("/api/settings")
@login_required
def get_settings():
    return jsonify({"antenna_ranges": _settings().get("antenna_ranges", [])})


@bp.put("/api/settings")
@login_required
def put_settings():
    data = request.get_json(force=True)
    if "antenna_ranges" in data:
        ranges = _valid_ranges(data.get("antenna_ranges"))
        if ranges is None:
            return jsonify({"error": "Plages invalides"}), 400
        _settings().set("antenna_ranges", ranges)
    return jsonify({"antenna_ranges": _settings().get("antenna_ranges", [])})
```
Supprimer aussi la fonction devenue inutilisée `_enabled()`.

- [ ] **Step 4: `load_persisted()` inconditionnel dans `comroster/__init__.py`**

Remplacer :
```python
    app.extensions["antenna"] = AntennaClient(app.config["DATA_DIR"], app.config.get("SECRET_KEY", ""))
    if app.extensions["settings"].get("bolero_enabled", False):
        app.extensions["antenna"].load_persisted()  # reconnexion lazy (testée au 1er /status)
```
par :
```python
    app.extensions["antenna"] = AntennaClient(app.config["DATA_DIR"], app.config.get("SECRET_KEY", ""))
    app.extensions["antenna"].load_persisted()  # recharge les identifiants s'ils existent
```

- [ ] **Step 5: Lancer (passe)** — `.venv/bin/pytest tests/test_antenna_api.py -q` → PASS.

- [ ] **Step 6: Suite complète + commit**

```bash
.venv/bin/pytest -q
git add comroster/antenna.py comroster/__init__.py tests/test_antenna_api.py
git commit -m "refactor(bolero): retrait du flag bolero_enabled (intégration toujours disponible)"
```

---

## Task 2: UI — bouton à pastille, assistant guidé, tableau de bord

**Files:**
- Modify: `templates/admin.html`, `static/js/admin.js`, `static/css/admin.css`
- Test: `tests/test_ui.py` (ajustement), vérification manuelle

**Interfaces:**
- Consomme l'API (status, connect, disconnect, settings, import/preview, import/apply) et les helpers `apiSend`, `toast`, `esc`, `load` de `admin.js`.

- [ ] **Step 1: HTML — toolbar (remplacer Réglages par Antenne)**

Dans `templates/admin.html`, dans le `tb-group` *Données*, remplacer le bouton Configs+suite. Concrètement : remplacer
```html
        <button type="button" id="configs-btn">Configs</button>
      </div>
```
par
```html
        <button type="button" id="configs-btn">Configs</button>
        <button type="button" id="antenna-btn">🛰 Antenne <span class="dot off" id="antenna-dot"></span></button>
      </div>
```
Et **supprimer** le bouton Réglages :
```html
      <button type="button" id="settings-btn">⚙ Réglages</button>
```
(la ligne entière disparaît).

- [ ] **Step 2: HTML — remplacer `#settings-dialog` par `#antenna-dialog`**

Supprimer entièrement le `<dialog id="settings-dialog" …>…</dialog>` et le remplacer par :
```html
  <dialog id="antenna-dialog" class="admin-dialog antenna-dialog">
    <div id="antenna-wizard" hidden>
      <div class="wiz-steps">
        <span class="wiz-dot active" data-dot="1"></span>
        <span class="wiz-line"></span>
        <span class="wiz-dot" data-dot="2"></span>
        <span class="wiz-line"></span>
        <span class="wiz-dot" data-dot="3"></span>
      </div>
      <section class="wiz-step" data-step="1">
        <h2>Connexion à l'antenne</h2>
        <label class="field"><span>Adresse IP</span>
          <input type="text" id="wiz-ip" placeholder="192.168.1.11" autocomplete="off"></label>
        <label class="field"><span>Mot de passe</span>
          <input type="password" id="wiz-password" autocomplete="off"></label>
        <p id="wiz-error" class="auth-error" hidden></p>
        <div class="dialog-actions">
          <button type="button" data-close="antenna-dialog">Annuler</button>
          <button type="button" id="wiz-connect-btn" class="primary">Connecter →</button>
        </div>
      </section>
      <section class="wiz-step" data-step="2" hidden>
        <h2>Beltpacks à charger</h2>
        <div class="ranges-editor">
          <span class="dlg-label">Numéros (vide = tous)</span>
          <div id="wiz-ranges-list"></div>
          <button type="button" id="wiz-add-range">+ Plage</button>
        </div>
        <div class="dialog-actions">
          <button type="button" id="wiz-back-2">← Retour</button>
          <button type="button" id="wiz-next-2" class="primary">Suivant →</button>
        </div>
      </section>
      <section class="wiz-step" data-step="3" hidden>
        <h2>Import</h2>
        <ul id="wiz-summary" class="import-summary"></ul>
        <div class="dialog-actions">
          <button type="button" id="wiz-back-3">← Retour</button>
          <button type="button" id="wiz-import-btn" class="primary">Importer</button>
        </div>
      </section>
    </div>

    <div id="antenna-dashboard" hidden>
      <h2>🛰 Antenne Bolero</h2>
      <div class="dash-grid">
        <section class="dash-card">
          <div class="dash-card-title">État</div>
          <div id="dash-state"></div>
        </section>
        <section class="dash-card">
          <div class="dash-card-title">Beltpacks à charger</div>
          <div class="ranges-editor">
            <div id="dash-ranges-list"></div>
            <button type="button" id="dash-add-range">+ Plage</button>
          </div>
        </section>
      </div>
      <div class="dialog-actions">
        <button type="button" id="dash-reconnect-btn" hidden>Reconnecter</button>
        <button type="button" id="dash-refresh-btn" class="primary">Actualiser depuis l'antenne</button>
        <button type="button" id="dash-disconnect-btn">Déconnecter</button>
        <button type="button" data-close="antenna-dialog">Fermer</button>
      </div>
    </div>
  </dialog>
```
> `import-dialog` et `configs-dialog` restent inchangés, plus bas dans le fichier.

- [ ] **Step 3: CSS — pastille, stepper, tableau de bord**

Ajouter à la fin de `static/css/admin.css` :
```css
/* ---------- Pastille d'état antenne ---------- */
#antenna-btn { display: inline-flex; align-items: center; gap: 0.45rem; }
.dot { width: 0.6rem; height: 0.6rem; border-radius: 50%; flex: 0 0 auto; }
.dot.off { background: #5d6a82; }
.dot.online { background: #2ecc71; box-shadow: 0 0 6px rgba(46,204,113,.6); }
.dot.offline { background: #e0913a; box-shadow: 0 0 6px rgba(224,145,58,.6); }

/* ---------- Assistant ---------- */
.antenna-dialog { max-width: 480px; }
.wiz-steps { display: flex; align-items: center; justify-content: center; gap: 0.5rem; margin-bottom: 0.4rem; }
.wiz-dot { width: 0.8rem; height: 0.8rem; border-radius: 50%; background: #2a3550; }
.wiz-dot.active { background: var(--primary); }
.wiz-dot.done { background: #2ecc71; }
.wiz-line { width: 2.2rem; height: 2px; background: #2a3550; }
.wiz-step h2 { margin: 0.2rem 0 0.4rem; }

/* ---------- Tableau de bord ---------- */
.dash-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0.8rem; }
@media (max-width: 520px) { .dash-grid { grid-template-columns: 1fr; } }
.dash-card { background: #0c111d; border: 1px solid #243049; border-radius: 8px; padding: 0.7rem 0.8rem; }
.dash-card-title { font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.05em; color: #8b97ad; margin-bottom: 0.45rem; }
#dash-state { display: flex; flex-direction: column; gap: 0.15rem; font-size: 0.9rem; }
#dash-state .ds-line { display: flex; align-items: center; gap: 0.4rem; }
#dash-state .ds-sub { color: #8b97ad; font-size: 0.82rem; }
```

- [ ] **Step 4: JS — remplacer la section « Réglages & intégration Bolero » et l'« Éditeur de plages »**

Dans `static/js/admin.js`, **supprimer** :
- le bloc commençant à `/* ---------- Réglages & intégration Bolero ---------- */` jusqu'à la ligne `document.getElementById("settings-btn").addEventListener("click", openSettings);` incluse ;
- le bloc `/* ---------- Éditeur de plages ---------- */` (de `let currentRanges = [];` jusqu'au handler `add-range-btn` inclus) ;
- dans l'objet `el = {…}` en haut, les lignes `settingsDialog`, ainsi que les refs `boleroToggle`/`antennaBlock` si présentes (elles ne servent plus).

**Insérer** à la place (juste avant `/* ---------- Configurations ---------- */`) :
```javascript
  /* ---------- Antenne : pastille, assistant, tableau de bord ---------- */
  const antennaDialog = document.getElementById("antenna-dialog");
  let currentRanges = [];
  let rangesListEl = null;

  function summaryHtml(p) {
    return [
      `<li><b>${p.new.length}</b> à ajouter${p.new.length ? " : " + p.new.map((n) => esc(`#${n.number} ${n.name}`)).join(", ") : ""}</li>`,
      `<li><b>${p.changed.length}</b> rôle(s) mis à jour${p.changed.length ? " : " + p.changed.map((c) => esc(`#${c.number} ${c.old_role}→${c.new_role}`)).join(", ") : ""}</li>`,
      `<li><b>${p.unchanged}</b> inchangé(s)</li>`,
      `<li><b>${p.missing.length}</b> à retirer${p.missing.length ? " : " + p.missing.map((m) => esc(`#${m.number} ${m.role}`)).join(", ") : ""}</li>`,
    ].join("");
  }

  // Pastille d'état (off / online / offline)
  async function refreshAntennaBadge() {
    const dot = document.getElementById("antenna-dot");
    let st;
    try { st = await apiSend("GET", "/api/antenna/status"); } catch { return; }
    dot.className = "dot " + (st.connected ? "online" : st.ip ? "offline" : "off");
    return st;
  }

  // Éditeur de plages partagé (assistant + dashboard)
  function renderRanges() {
    if (!rangesListEl) return;
    rangesListEl.innerHTML = "";
    currentRanges.forEach((r, i) => {
      const row = document.createElement("div");
      row.className = "range-row";
      row.innerHTML = `de <input type="number" min="1" value="${r[0]}" data-i="${i}" data-k="0"> à `
        + `<input type="number" min="1" value="${r[1]}" data-i="${i}" data-k="1">`;
      const del = document.createElement("button");
      del.type = "button"; del.className = "range-del"; del.textContent = "✕";
      del.addEventListener("click", () => { currentRanges.splice(i, 1); renderRanges(); saveRanges(); });
      row.appendChild(del);
      rangesListEl.appendChild(row);
    });
    rangesListEl.querySelectorAll("input").forEach((inp) => inp.addEventListener("change", () => {
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
  function addRange() { currentRanges.push([1, 25]); renderRanges(); saveRanges(); }
  document.getElementById("wiz-add-range").addEventListener("click", addRange);
  document.getElementById("dash-add-range").addEventListener("click", addRange);

  // Navigation de l'assistant
  function wizGo(step) {
    antennaDialog.querySelectorAll(".wiz-step").forEach((s) => { s.hidden = +s.dataset.step !== step; });
    antennaDialog.querySelectorAll(".wiz-dot").forEach((d) => {
      const n = +d.dataset.dot;
      d.classList.toggle("active", n === step);
      d.classList.toggle("done", n < step);
    });
    if (step === 2) { rangesListEl = document.getElementById("wiz-ranges-list"); renderRanges(); }
  }

  async function openAntenna() {
    const settings = await apiSend("GET", "/api/settings");
    currentRanges = (settings.antenna_ranges || []).map((r) => [r[0], r[1]]);
    const st = await refreshAntennaBadge();
    if (st && st.ip) {
      // Tableau de bord
      document.getElementById("antenna-wizard").hidden = true;
      document.getElementById("antenna-dashboard").hidden = false;
      const online = st.connected;
      const fw = st.info?.firmware?.version || "?";
      const name = st.info?.local?.name || st.ip;
      const nbp = (st.info?.nodes || []).reduce((a, n) => a + (n.bp ? n.bp.length : 0), 0);
      document.getElementById("dash-state").innerHTML =
        `<div class="ds-line"><span class="dot ${online ? "online" : "offline"}"></span>`
        + `<b>${online ? "Connecté" : "Hors ligne"}</b></div>`
        + `<div class="ds-sub">${esc(name)}${online ? ` · firmware ${esc(fw)}` : ""}</div>`
        + (online && nbp ? `<div class="ds-sub">${nbp} beltpack(s) sur le réseau</div>` : "");
      document.getElementById("dash-reconnect-btn").hidden = online;
      document.getElementById("dash-refresh-btn").hidden = !online;
      rangesListEl = document.getElementById("dash-ranges-list"); renderRanges();
    } else {
      // Assistant
      document.getElementById("antenna-dashboard").hidden = true;
      document.getElementById("antenna-wizard").hidden = false;
      document.getElementById("wiz-ip").value = "";
      document.getElementById("wiz-password").value = "";
      document.getElementById("wiz-error").hidden = true;
      wizGo(1);
    }
    antennaDialog.showModal();
  }
  document.getElementById("antenna-btn").addEventListener("click", openAntenna);

  // Assistant — étape 1 : connexion
  document.getElementById("wiz-connect-btn").addEventListener("click", async () => {
    const ip = document.getElementById("wiz-ip").value.trim();
    const password = document.getElementById("wiz-password").value;
    const err = document.getElementById("wiz-error");
    err.hidden = true;
    try {
      await apiSend("POST", "/api/antenna/connect", { ip, password });
      await refreshAntennaBadge();
      wizGo(2);
    } catch (e) {
      err.textContent = e.payload?.error || "Connexion échouée";
      err.hidden = false;
    }
  });
  document.getElementById("wiz-back-2").addEventListener("click", () => wizGo(1));
  document.getElementById("wiz-back-3").addEventListener("click", () => wizGo(2));

  // Assistant — étape 2 → 3 : récap inline
  document.getElementById("wiz-next-2").addEventListener("click", async () => {
    let p;
    try { p = await apiSend("POST", "/api/antenna/import/preview"); }
    catch { toast("Lecture des beltpacks impossible", true); return; }
    document.getElementById("wiz-summary").innerHTML = summaryHtml(p);
    wizGo(3);
  });
  // Assistant — étape 3 : import
  document.getElementById("wiz-import-btn").addEventListener("click", async () => {
    try {
      await apiSend("POST", "/api/antenna/import/apply");
      antennaDialog.close();
      setUnpublished(true);
      await load();
      await refreshAntennaBadge();
      toast("Beltpacks importés");
    } catch { toast("Import impossible", true); }
  });

  // Tableau de bord — actions
  document.getElementById("dash-reconnect-btn").addEventListener("click", openAntenna);
  document.getElementById("dash-disconnect-btn").addEventListener("click", async () => {
    try { await apiSend("POST", "/api/antenna/disconnect"); } finally {
      antennaDialog.close();
      await refreshAntennaBadge();
    }
  });
  document.getElementById("dash-refresh-btn").addEventListener("click", async () => {
    let p;
    try { p = await apiSend("POST", "/api/antenna/import/preview"); }
    catch { toast("Lecture des beltpacks impossible", true); return; }
    document.getElementById("import-summary").innerHTML = summaryHtml(p);
    document.getElementById("import-dialog").showModal();
  });

  // Récap modal (Actualiser depuis le dashboard) → appliquer
  document.getElementById("import-apply-btn").addEventListener("click", async () => {
    try {
      await apiSend("POST", "/api/antenna/import/apply");
      document.getElementById("import-dialog").close();
      antennaDialog.close();
      setUnpublished(true);
      await load();
      await refreshAntennaBadge();
      toast("Beltpacks importés");
    } catch { toast("Import impossible", true); }
  });
```
> Si un handler `import-apply-btn` existait déjà dans l'ancien bloc supprimé, c'est cette version (ci-dessus) qui le remplace — il ne doit y en avoir qu'un.

- [ ] **Step 5: JS — initialiser la pastille au chargement**

Dans le bloc `/* ---------- Init ---------- */`, après `updateSelectionBar();`, ajouter :
```javascript
  refreshAntennaBadge();
```

- [ ] **Step 6: Test de rendu**

Dans `tests/test_ui.py`, remplacer `test_admin_has_settings_and_import_dialogs` par :
```python
def test_admin_has_antenna_panel(auth_client):
    html = auth_client.get("/admin").get_data(as_text=True)
    assert 'id="antenna-btn"' in html
    assert 'id="antenna-dialog"' in html
    assert "antenna-wizard" in html
    assert "antenna-dashboard" in html
    assert "settings-dialog" not in html      # ancien dialog retiré
```
Run: `.venv/bin/pytest tests/test_ui.py -q` → PASS.

- [ ] **Step 7: Vérification manuelle (faux serveur antenne)**

`./run-dev.sh` + faux serveur antenne. Dans `/admin` :
- Pastille grise au départ. Clic « 🛰 Antenne » → **assistant** étape 1 → saisir IP/mdp → Connecter → étape 2 (plages) → Suivant → étape 3 (récap) → Importer → fiches importées, pastille **verte**.
- Ré-ouvrir « Antenne » → **tableau de bord** (état connecté, firmware, plages, actions). « Actualiser » → récap → Appliquer. « Déconnecter » → pastille **grise**.
- Couper le faux serveur, ré-ouvrir → état **hors ligne** (pastille orange) + bouton « Reconnecter ».

- [ ] **Step 8: Commit**

```bash
git add templates/admin.html static/js/admin.js static/css/admin.css tests/test_ui.py
git commit -m "feat(ui): panneau Antenne dédié — bouton à pastille, assistant guidé, tableau de bord"
```

---

## Self-review (couverture du spec)

- Bouton « 🛰 Antenne » + pastille (off/online/offline) → Task 2 (HTML, CSS, `refreshAntennaBadge`). ✓
- Assistant 3 étapes (Connexion → Plages → Import récap inline) → Task 2 (`wizGo`, handlers). ✓
- Tableau de bord (État / Filtre / Actions) → Task 2 (`openAntenna` branche dashboard). ✓
- Choix assistant/dashboard via `status.ip` → Task 2 (`openAntenna`). ✓
- Retrait du flag + garde 409 + `load_persisted` inconditionnel → Task 1. ✓
- `GET /api/settings` → `{antenna_ranges}` → Task 1. ✓
- Récap modal conservé pour Actualiser ; configs conservés → Task 2 (réutilise `import-dialog`, `summaryHtml`). ✓
- Reconnexion : `status` retente, bouton Reconnecter, Déconnecter pour changer d'identifiants → Task 2. ✓

**Cohérence vérifiée :** `summaryHtml(p)` utilisé pour le wizard (`wiz-summary`) et le modal (`import-summary`) ; `currentRanges`/`rangesListEl` partagés entre assistant et dashboard ; un seul handler `import-apply-btn` après remplacement ; `refreshAntennaBadge` posant `off/online/offline` sur `#antenna-dot`.

