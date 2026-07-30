# Menu « Réglages » — plan d'implémentation

> **Pour les agents :** SOUS-COMPÉTENCE REQUISE : utiliser superpowers:subagent-driven-development (recommandé) ou superpowers:executing-plans pour exécuter ce plan tâche par tâche. Les étapes utilisent la syntaxe case à cocher (`- [ ]`).

**Spec :** [docs/superpowers/specs/2026-07-30-menu-reglages-design.md](../specs/2026-07-30-menu-reglages-design.md)

**But :** regrouper Réseau, Sauvegarde, Mot de passe, Journal, Santé et Redémarrer sous une entrée unique `Réglages ▾` en fin de barre d'onglets de l'admin, et retirer leurs anciens accès.

**Architecture :** aucun changement serveur. `templates/admin.html` déplace six éléments existants dans un panneau `[hidden]` ; `static/css/admin.css` style le panneau ; `static/js/admin.js` ajoute la bascule et branche la fermeture sur le handler clavier global déjà en place. **Les quatre ids de boutons (`#network-btn`, `#backup-btn`, `#password-btn`, `#reboot-btn`) sont conservés**, donc leurs quatre `addEventListener` existants ne sont pas touchés.

**Pile technique :** Jinja2, CSS natif (jetons `--ui`/`--pad`/`--row`/`--rad`), JavaScript nu sans dépendance de runtime, pytest + Playwright.

## Contraintes globales

- **Aucun `<style>` inline, aucune feuille externe** : CSP stricte `default-src 'self'` (leçon 2026-07-07).
- **Aucun `display` inconditionnel sur un élément piloté par `hidden`** : la règle d'affichage cible `#settings-menu:not([hidden])` (leçon 2026-06-21, erreur commise deux fois).
- **Tout jeton CSS utilisé doit être défini** : `test_css_tokens.py` le garde ; n'employer que des jetons déjà présents dans `admin.css` (`--ui`, `--pad`, `--row`, `--rad`, `--track`, `--fg`, `--fg-muted`, `--border`, `--border-soft`, `--surface-3`, `--warning`).
- **Un accès par fonction** : après déplacement, chaque id ne doit apparaître **qu'une fois** dans le HTML rendu (leçon 2026-07-25).
- **Attente Playwright sur un élément masqué** : toujours `state="attached"` ou `state="hidden"` explicite, jamais le `visible` implicite (leçons 2026-07-23 et 2026-07-27).
- **Chaque nouveau test est confronté à un cas qui échoue volontairement** avant d'être considéré comme acquis (leçon 2026-07-23).
- **Ne jamais enchaîner un `git commit` derrière un `pytest | tail` avec `&&`** : le pipe masque le code retour. Lancer les tests, LIRE le résultat, puis committer (leçon 2026-07-26).
- `admin.js` est une **IIFE unique** : tout est au niveau d'indentation de 2 espaces et partage une seule portée.

## Structure des fichiers

| Fichier | Responsabilité | Nature du changement |
|---|---|---|
| `templates/admin.html` | balisage du menu ; suppression des anciens accès | modifier l. 30-43, 83-90, 108-112 |
| `static/css/admin.css` | apparence du déclencheur et du panneau | ajouter après l. 117 ; retirer l. 222 devenue morte |
| `static/js/admin.js` | bascule, clic extérieur, clavier | insérer avant l. 1447 ; modifier l. 1453 et 1456-1459 |
| `tests/test_ui.py` | garde structurelle d'unicité d'accès | ajouter un test |
| `tests/e2e/helpers.py` | ouverture du menu, source unique | **créer** |
| `tests/e2e/test_e2e.py` | 3 clics `#network-btn` à faire passer par le menu | modifier l. 442, 562, 586 |
| `tests/e2e/test_audit_features.py` | 4 clics `#password-btn`/`#backup-btn` | modifier l. 91, 121, 136, 162 |
| `tests/e2e/test_reglages_menu.py` | comportement du menu dans un vrai navigateur | **créer** |
| `tasks/todo.md` | trace du lot | ajouter une section |

---

### Tâche 1 : le déplacement — le menu existe, les anciens accès disparaissent

Cette tâche est **atomique et ne peut pas être scindée** : ajouter les items du menu sans retirer les anciens créerait des ids en double (`getElementById` ne verrait que le premier, et le HTML serait invalide) ; retirer d'abord rendrait six fonctions inaccessibles entre deux commits.

**Fichiers :**
- Modifier : `templates/admin.html:30-43`, `templates/admin.html:83-90`, `templates/admin.html:108-112`
- Modifier : `static/css/admin.css:117` (insertion après), `static/css/admin.css:222` (suppression)
- Modifier : `static/js/admin.js:1447` (insertion avant)
- Test : `tests/test_ui.py` (ajout), `tests/e2e/helpers.py` (création), `tests/e2e/test_e2e.py`, `tests/e2e/test_audit_features.py`

**Interfaces :**
- Consomme : rien (première tâche).
- Produit, dans la portée de l'IIFE d'`admin.js`, pour la tâche 2 :
  - `settingsOpen() -> boolean` — le panneau est-il ouvert ;
  - `closeSettings({ focus = false } = {}) -> boolean` — ferme s'il était ouvert et renvoie `true` dans ce cas, `false` sinon ; `focus: true` rend le focus à `#settings-btn` ;
  - `setSettings(open: boolean) -> void` — pose `hidden` et `aria-expanded`.
- Produit, pour les e2e : `tests/e2e/helpers.py::open_reglages(page) -> None`.

- [ ] **Étape 1 : écrire le test structurel qui échoue**

Ajouter à la fin de `tests/test_ui.py` :

```python
def _fragment(html, debut, fin):
    """Découpe le fragment de `html` entre deux marqueurs.

    On borne sur des balises FERMANTES de conteneur (`</nav>`, `</aside>`) et non sur
    `</div>`, qui serait ambigu : le panneau contient lui-même des `<div>` séparateurs.
    """
    i = html.index(debut)
    return html[i:html.index(fin, i)]


def test_reglages_regroupe_les_fonctions_boitier(auth_client):
    """Les six fonctions du boîtier vivent dans le menu, et NULLE PART AILLEURS.

    Le comptage à 1 est le cœur du test : il échoue aussi bien si une fonction est
    perdue (0) que si un ancien accès survit ou revient (2). C'est exactement le
    défaut relevé à la revue du 2026-07-25 (« Système » ouvrait le dialogue de
    « Réseau », l'aperçu était accessible à deux endroits).
    """
    html = auth_client.get("/admin").get_data(as_text=True)

    menu = _fragment(html, 'id="settings-menu"', "</nav>")
    for cible in ('id="network-btn"', 'id="backup-btn"',
                  'id="password-btn"', 'id="reboot-btn"', ">Santé<", ">Journal<"):
        assert cible in menu, f"{cible} absent du menu Réglages"
        assert html.count(cible) == 1, f"{cible} a {html.count(cible)} accès, il en faut 1"

    # Le déclencheur annonce son panneau, et le panneau part fermé.
    assert 'id="settings-btn"' in html
    assert 'aria-expanded="false"' in html
    assert 'aria-controls="settings-menu"' in html
    assert 'id="settings-menu" role="menu" hidden' in html

    # Anciens emplacements : la section « Boîtier » de la latérale n'existe plus, et le
    # pied ne garde que la déconnexion.
    assert "Boîtier" not in html
    pied = _fragment(html, 'class="side-foot"', "</aside>")
    assert "reboot-btn" not in pied
    assert "logout-link" in pied
```

- [ ] **Étape 2 : lancer le test, vérifier qu'il échoue**

Lancer : `.venv/bin/pytest tests/test_ui.py::test_reglages_regroupe_les_fonctions_boitier -v`

Attendu : ÉCHEC sur `ValueError: substring not found` (le marqueur `id="settings-menu"` n'existe pas encore).

- [ ] **Étape 3 : remplacer le bloc d'onglets du template**

Dans `templates/admin.html`, remplacer l'intégralité du `<nav class="admin-tabs">` (l. 30-43) par :

```html
      <nav class="admin-tabs" role="tablist" aria-label="Sections de l'administration">
        {# Affectations et Écran sont des panneaux. UN accès par fonction : l'antenne
           passe par son onglet-voyant, et TOUT ce qui concerne le boîtier lui-même
           (consultation, configuration, redémarrage) passe par « Réglages ». #}
        <button type="button" class="tab" data-tab="board" role="tab" aria-selected="true">Affectations</button>
        <button type="button" class="tab" data-tab="screen" role="tab" aria-selected="false">Écran</button>
        {# Intercom garde son accès direct : il PORTE le voyant d'état en direct, et un
           voyant enfermé dans un menu fermé n'informe de rien. #}
        <button type="button" class="tab" id="antenna-btn" title="Connexion au réseau intercom">
          <span class="dot off" id="antenna-dot"></span>Intercom</button>
        <div class="tab-menu">
          <button type="button" class="tab" id="settings-btn" aria-haspopup="true"
                  aria-expanded="false" aria-controls="settings-menu">Réglages<span class="tab-chev" aria-hidden="true">▾</span></button>
          {# Trois blocs : on consulte, puis on configure, puis on redémarre. L'ordre va
             du inoffensif au destructeur, et les ids sont ceux d'avant le déplacement —
             les quatre addEventListener d'admin.js n'ont donc rien à changer. #}
          <div class="menu-pop" id="settings-menu" role="menu" hidden>
            <a class="menu-item" role="menuitem" href="{{ url_for('api.health_page') }}">Santé</a>
            <a class="menu-item" role="menuitem" href="{{ url_for('api.journal_page') }}">Journal</a>
            <div class="menu-sep" role="separator"></div>
            <button type="button" class="menu-item" role="menuitem" id="network-btn"
                    title="Configuration réseau du boîtier">Réseau</button>
            <button type="button" class="menu-item" role="menuitem" id="backup-btn"
                    title="Archive complète : plateau, réseau, antenne, configurations, mot de passe">Sauvegarde</button>
            <button type="button" class="menu-item" role="menuitem" id="password-btn">Mot de passe</button>
            <div class="menu-sep" role="separator"></div>
            <button type="button" class="menu-item nav-danger" role="menuitem" id="reboot-btn"
                    title="Redémarre le Raspberry Pi (écran et admin indisponibles ~1 min)">Redémarrer</button>
          </div>
        </div>
      </nav>
```

- [ ] **Étape 4 : retirer la section « Boîtier » de la latérale**

Dans `templates/admin.html`, supprimer entièrement les lignes 83-90, soit le commentaire Jinja `{# Le boîtier lui-même … #}` et le `<nav class="side-nav">` qui contient `#backup-btn` et `#password-btn`.

- [ ] **Étape 5 : retirer « Redémarrer » du pied de latérale**

Dans `templates/admin.html`, remplacer le `<div class="side-foot-row">` (l. 109-112) par :

```html
          <div class="side-foot-row">
            {# Redémarrer a rejoint « Réglages » : le pied ne garde que la déconnexion. #}
            <a class="logout-link" id="logout-link" href="{{ url_for('auth.logout') }}">Déconnexion</a>
          </div>
```

- [ ] **Étape 6 : styler le déclencheur et le panneau**

Dans `static/css/admin.css`, insérer juste après la ligne 117 (`.admin-tabs .tab[aria-selected="true"] { … }`) :

```css
/* Menu « Réglages » : tout ce qui concerne le BOÎTIER sous une entrée unique.
   Le panneau est piloté par l'attribut [hidden] — la règle d'affichage cible donc
   `:not([hidden])` et AUCUN display inconditionnel n'est posé ici (leçon 2026-06-21,
   où un `display:flex` inconditionnel écrasait `hidden` et laissait l'élément visible). */
.tab-menu { position: relative; display: flex; align-items: stretch; }
.tab-chev { font-size: 9px; line-height: 1; opacity: 0.7; }
#settings-menu:not([hidden]) {
    position: absolute; top: 100%; right: 0; z-index: 40;
    min-width: 190px; padding: 5px 0;
    display: flex; flex-direction: column;
    background: var(--surface-3); border: 1px solid var(--border);
    border-radius: var(--rad); box-shadow: 0 10px 28px #00000088;
}
/* Même gabarit que les rangées de la latérale (d'où viennent quatre de ces six items) :
   le menu ne doit pas introduire un troisième registre de rangée cliquable. */
.menu-item {
    display: flex; align-items: center;
    width: 100%; height: calc(var(--row) - 3px); padding: 0 var(--pad);
    color: var(--fg-muted); font-size: calc(var(--ui) + 1px); font-weight: 600;
    letter-spacing: var(--track); text-align: left; white-space: nowrap; cursor: pointer;
}
.menu-item:hover:not(:disabled), .menu-item:focus-visible { background: #ffffff08; color: var(--fg); }
.menu-sep { height: 1px; margin: 5px 0; background: var(--border-soft); }
```

`Redémarrer` réutilise la classe `.nav-danger` existante (l. 216-217) : son survol ambre fonctionne tel quel dans le menu, et la réutiliser évite de dupliquer un registre « danger ».

- [ ] **Étape 7 : supprimer la règle CSS devenue morte**

Dans `static/css/admin.css`, supprimer la ligne 222 :

```css
.side-foot-row .nav-item { width: auto; flex: 0 0 auto; padding: 0 var(--pad); }
```

`#reboot-btn` était le seul `.nav-item` du pied ; la règle ne cible plus rien. Un sélecteur orphelin se supprime dans le même commit que ce qui l'a vidé (leçon 2026-07-28).

- [ ] **Étape 8 : câbler la bascule**

Dans `static/js/admin.js`, insérer **juste avant** la ligne 1447 (`window.addEventListener("keydown", …`) :

```js
  // ---------- Menu « Réglages » (fonctions du boîtier) ----------
  // Ce n'est PAS un <dialog> : il ne prend pas le focus à l'ouverture et ne bloque pas
  // la page. Déclaré AVANT le handler clavier global, qui s'en sert dès la ligne suivante.
  const settingsBtn = document.getElementById("settings-btn");
  const settingsMenu = document.getElementById("settings-menu");
  const settingsOpen = () => !settingsMenu.hidden;
  function setSettings(open) {
    settingsMenu.hidden = !open;
    settingsBtn.setAttribute("aria-expanded", open ? "true" : "false");
  }
  function closeSettings({ focus = false } = {}) {
    if (!settingsOpen()) return false;
    setSettings(false);
    if (focus) settingsBtn.focus();
    return true;
  }
  settingsBtn.addEventListener("click", (ev) => {
    // Sans stopPropagation, l'écouteur « clic extérieur » ci-dessous refermerait
    // aussitôt ce que ce clic vient d'ouvrir.
    ev.stopPropagation();
    setSettings(!settingsOpen());
  });
  // Choisir un item referme : les trois dialogues et le redémarrage laisseraient sinon
  // le menu ouvert DERRIÈRE eux, et les deux liens quittent la page de toute façon.
  settingsMenu.addEventListener("click", (ev) => {
    if (ev.target.closest(".menu-item")) closeSettings();
  });
  document.addEventListener("click", (ev) => {
    if (settingsOpen() && !ev.target.closest(".tab-menu")) closeSettings();
  });
```

- [ ] **Étape 9 : lancer le test structurel, vérifier qu'il passe**

Lancer : `.venv/bin/pytest tests/test_ui.py::test_reglages_regroupe_les_fonctions_boitier -v`

Attendu : PASS.

- [ ] **Étape 10 : créer le helper e2e**

Créer `tests/e2e/helpers.py` :

```python
"""Gestes d'interface partagés par les e2e.

Une seule définition : les fonctions du boîtier vivent désormais dans un menu, et
sept tests existants cliquaient leurs boutons en direct. Recopier l'ouverture dans
chaque fichier reviendrait à entretenir deux versions du même geste.
"""


def open_reglages(page):
    """Ouvre le menu « Réglages » et attend que son panneau soit réellement visible.

    L'attente est explicite : le panneau est piloté par `hidden`, et un `wait_for_selector`
    sans état attend `visible` par défaut — c'est ce qui a fait expirer deux attentes dans
    ce dépôt (leçons 2026-07-23 et 2026-07-27).
    """
    page.click("#settings-btn")
    page.wait_for_selector("#settings-menu:not([hidden])", state="visible")
```

- [ ] **Étape 11 : faire passer les sept clics existants par le menu**

Dans `tests/e2e/test_e2e.py`, ajouter l'import en tête de fichier (à côté des autres imports) :

```python
from .helpers import open_reglages
```

puis, aux lignes 442, 562 et 586, remplacer chaque occurrence de :

```python
    page.click("#network-btn")
```

par :

```python
    open_reglages(page)
    page.click("#network-btn")
```

Dans `tests/e2e/test_audit_features.py`, ajouter le même import, puis appliquer le même traitement à `page.click("#password-btn")` (l. 91) et aux trois `page.click("#backup-btn")` (l. 121, 136, 162).

- [ ] **Étape 12 : lancer la suite complète, LIRE le résultat**

Lancer, en commandes **séparées** (un pipe masquerait le code retour — leçon 2026-07-26) :

```bash
.venv/bin/pytest tests/ -x -q --ignore=tests/e2e
.venv/bin/pytest tests/e2e -q
.venv/bin/ruff check .
```

Attendu : tout vert, ruff propre. Les sept e2e modifiés doivent passer ; s'ils échouent sur un `timeout` d'attente du panneau, le défaut est dans le CSS de l'étape 6 (un `display` qui écrase `hidden`), pas dans le test.

- [ ] **Étape 13 : vérifier que la garde MORD**

Retirer temporairement le second `<div class="menu-sep" role="separator"></div>` et le bouton `#reboot-btn` du template, relancer :

```bash
.venv/bin/pytest tests/test_ui.py::test_reglages_regroupe_les_fonctions_boitier -v
```

Attendu : ÉCHEC sur `id="reboot-btn" absent du menu Réglages`. Puis **rétablir le template** et re-vérifier le PASS. Sans cette confrontation, l'assertion de comptage est une assertion négative jamais vue échouer — donc sans valeur (leçon 2026-07-23).

- [ ] **Étape 14 : commit**

```bash
git add templates/admin.html static/css/admin.css static/js/admin.js tests/test_ui.py tests/e2e/helpers.py tests/e2e/test_e2e.py tests/e2e/test_audit_features.py
git commit -m "feat: menu « Réglages » regroupant les six fonctions du boîtier

Réseau, Sauvegarde, Mot de passe, Journal, Santé et Redémarrer vivaient dans
trois zones différentes de l'admin. Ils passent sous une entrée unique en fin
de barre d'onglets ; leurs anciens accès sont retirés (un accès par fonction).

Les quatre ids de boutons sont conservés : aucun des addEventListener
d'admin.js ne change. Sept clics e2e passent par un helper qui ouvre le menu."
```

---

### Tâche 2 : le clavier — Échap, ⌘Z/⌘A, flèches

**Fichiers :**
- Modifier : `static/js/admin.js:1453` (prédicat `onBoard`), `static/js/admin.js:1456-1459` (ordre d'Échap), insertion après le bloc de la tâche 1
- Test : `tests/e2e/test_reglages_menu.py` (création)

**Interfaces :**
- Consomme : `settingsOpen()`, `closeSettings({ focus })`, `setSettings(open)` de la tâche 1.
- Produit : rien que d'autres tâches consomment.

- [ ] **Étape 1 : écrire les tests qui échouent**

Créer `tests/e2e/test_reglages_menu.py` :

```python
"""Comportement clavier et souris du menu « Réglages ».

Ces gestes vivent dans le navigateur : les valider en DOM seul ne prouverait rien
(leçon 2026-07-07). Le menu entre en collision avec trois raccourcis déjà en place
(Échap, ⌘Z, ⌘A) — c'est ce que ce fichier garde.
"""
import pytest

from .helpers import open_reglages

pytestmark = pytest.mark.e2e


def _enter_admin(page, base):
    page.goto(base + "/admin/setup")
    page.fill("input[name=password]", "motdepasse8")
    page.click("button[type=submit]")
    page.click("a.auth-submit")
    page.wait_for_selector("#add-block-btn")


def test_menu_souvre_et_se_ferme(page, live_server):
    _enter_admin(page, live_server)
    open_reglages(page)
    assert page.get_attribute("#settings-btn", "aria-expanded") == "true"

    # Clic extérieur : sur le titre du fil d'Ariane, hors de .tab-menu.
    page.click("#board-title")
    page.wait_for_selector("#settings-menu", state="hidden")
    assert page.get_attribute("#settings-btn", "aria-expanded") == "false"


def test_echap_ferme_le_menu_et_rend_le_focus(page, live_server):
    _enter_admin(page, live_server)
    open_reglages(page)
    page.keyboard.press("Escape")
    page.wait_for_selector("#settings-menu", state="hidden")
    # Sans le retour de focus, la navigation clavier repartirait du début du document.
    assert page.evaluate("document.activeElement.id") == "settings-btn"


def test_echap_ferme_le_menu_avant_de_quitter_la_selection(page, live_server):
    """Un menu ouvert est ce que l'utilisateur VOIT : il part en premier.

    La sélection multiple, elle, doit survivre à ce premier Échap — sinon on perd
    d'un coup un état qu'on avait mis plusieurs clics à construire.
    """
    _enter_admin(page, live_server)
    page.keyboard.press("Meta+a")               # ⌘A = tout sélectionner (vue active)
    page.wait_for_selector("#selection-bar.active")
    open_reglages(page)
    page.keyboard.press("Escape")
    page.wait_for_selector("#settings-menu", state="hidden")
    # La sélection est INTACTE : la barre est toujours active.
    assert "active" in (page.get_attribute("#selection-bar", "class") or "")
    # Le second Échap, lui, la quitte.
    page.keyboard.press("Escape")
    page.wait_for_selector("#selection-bar:not(.active)", state="attached")


def test_les_fleches_parcourent_les_items(page, live_server):
    _enter_admin(page, live_server)
    page.click("#settings-btn")
    page.wait_for_selector("#settings-menu:not([hidden])", state="visible")
    page.keyboard.press("ArrowDown")
    assert page.evaluate("document.activeElement.textContent.trim()") == "Santé"
    page.keyboard.press("ArrowDown")
    assert page.evaluate("document.activeElement.textContent.trim()") == "Journal"
    # Le parcours boucle : ↑ depuis le premier item ramène au dernier.
    page.keyboard.press("ArrowUp")
    page.keyboard.press("ArrowUp")
    assert page.evaluate("document.activeElement.id") == "reboot-btn"
```

- [ ] **Étape 2 : lancer les tests, vérifier qu'ils échouent**

Lancer : `.venv/bin/pytest tests/e2e/test_reglages_menu.py -q`

Attendu : `test_menu_souvre_et_se_ferme` PASSE déjà (la tâche 1 l'a livré) ; les **trois autres ÉCHOUENT** — pas de fermeture sur Échap, pas de retour de focus, pas de navigation aux flèches.

- [ ] **Étape 3 : insérer la fermeture par Échap au bon rang**

Dans `static/js/admin.js`, dans le handler `keydown` global, insérer la branche **entre** la ligne 1456 (annulation du décompte de publication) et la ligne 1459 (sortie de sélection) :

```js
    // Échap ferme le menu « Réglages » — APRÈS le décompte de publication (c'est l'action
    // la plus conséquente à pouvoir rattraper, rang décidé le 2026-07-27) mais AVANT la
    // sortie de sélection : un menu ouvert est ce que l'utilisateur voit, il part d'abord,
    // et la sélection multiple survit à ce premier Échap.
    if (e.key === "Escape" && closeSettings({ focus: true })) { e.preventDefault(); return; }
```

- [ ] **Étape 4 : étendre le prédicat partagé `onBoard`**

Dans `static/js/admin.js`, remplacer la ligne 1453 :

```js
    const onBoard = !/INPUT|TEXTAREA|SELECT/.test(tag) && !document.querySelector("dialog[open]");
```

par :

```js
    const onBoard = !/INPUT|TEXTAREA|SELECT/.test(tag) && !document.querySelector("dialog[open]")
      && !settingsOpen();
```

La condition va dans le **seul prédicat partagé**, jamais recopiée dans les branches ⌘Z / ⌘A / Échap : une liste d'exclusions recopiée se périme au premier raccourci ajouté (leçon 2026-07-27).

- [ ] **Étape 5 : ajouter la navigation aux flèches**

Dans `static/js/admin.js`, à la fin du bloc « Menu Réglages » ajouté par la tâche 1 :

```js
  // ↓ depuis le déclencheur ouvre et entre dans le menu ; Entrée et Espace n'ont besoin
  // de rien, ce sont des <button> et des <a> — le navigateur les active nativement.
  settingsBtn.addEventListener("keydown", (ev) => {
    if (ev.key !== "ArrowDown") return;
    ev.preventDefault();
    setSettings(true);
    settingsMenu.querySelector(".menu-item")?.focus();
  });
  settingsMenu.addEventListener("keydown", (ev) => {
    if (ev.key !== "ArrowDown" && ev.key !== "ArrowUp") return;
    ev.preventDefault();
    const items = [...settingsMenu.querySelectorAll(".menu-item")];
    const i = items.indexOf(document.activeElement);
    const suivant = (ev.key === "ArrowDown" ? i + 1 : i - 1 + items.length) % items.length;
    items[suivant].focus();
  });
```

- [ ] **Étape 6 : lancer les tests, vérifier qu'ils passent**

Lancer : `.venv/bin/pytest tests/e2e/test_reglages_menu.py -q`

Attendu : 4 PASS.

- [ ] **Étape 7 : vérifier que le rang d'Échap MORD**

Déplacer temporairement la branche de l'étape 3 **après** la sortie de sélection (l. 1459), relancer :

```bash
.venv/bin/pytest tests/e2e/test_reglages_menu.py::test_echap_ferme_le_menu_avant_de_quitter_la_selection -q
```

Attendu : ÉCHEC — la sélection est quittée alors que le menu était ouvert. Puis **rétablir le bon rang** et re-vérifier le PASS. C'est la confrontation exigée par la leçon 2026-07-23 : sans elle, rien ne prouve que ce test teste l'ORDRE et pas juste la fermeture.

- [ ] **Étape 8 : vérifier que la garde `onBoard` MORD**

Retirer temporairement `&& !settingsOpen()` de la ligne 1453, puis, dans un navigateur ouvert sur l'admin : menu ouvert, ⌘Z. Attendu sans la garde : la dernière modification du brouillon est annulée alors que le curseur est dans un menu. Rétablir la garde et constater que ⌘Z n'a plus d'effet menu ouvert.

Ce contrôle reste manuel : la garde est une seule condition dans un prédicat déjà couvert par les tests de ⌘Z existants, et l'observation directe suffit à prouver qu'elle mord.

- [ ] **Étape 9 : lancer la suite complète, LIRE le résultat**

```bash
.venv/bin/pytest tests/ -x -q --ignore=tests/e2e
.venv/bin/pytest tests/e2e -q
.venv/bin/ruff check .
```

Attendu : tout vert, ruff propre.

- [ ] **Étape 10 : commit**

```bash
git add static/js/admin.js tests/e2e/test_reglages_menu.py
git commit -m "feat: clavier du menu « Réglages » (Échap, flèches, garde ⌘Z/⌘A)

Échap se place entre l'annulation du décompte de publication et la sortie de
sélection : un menu ouvert part en premier, la sélection multiple survit. La
condition « menu ouvert » entre dans le seul prédicat onBoard, pas recopiée
dans chaque branche."
```

---

### Tâche 3 : vérification au rendu réel et trace du lot

**Fichiers :**
- Créer : script de capture dans le scratchpad de session (hors dépôt)
- Modifier : `tasks/todo.md`

**Interfaces :**
- Consomme : le menu livré par les tâches 1 et 2.
- Produit : rien.

- [ ] **Étape 1 : écrire le script de capture**

Un changement structurel ne se valide pas par des tests DOM seuls (leçon 2026-07-07). Écrire le script **dans un fichier**, jamais en heredoc : le hook rtk peut altérer le corps d'un heredoc, et une vérification qui n'a pas tourné donne une confiance fausse (leçon 2026-07-28).

Créer `<scratchpad>/capture_reglages.py` (le chemin du scratchpad est donné par l'environnement de session) :

```python
"""Capture l'en-tête de l'admin, menu « Réglages » ouvert, et exige une console vide."""
import sys

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8080"
SORTIE = sys.argv[2] if len(sys.argv) > 2 else "reglages.png"

with sync_playwright() as p:
    nav = p.chromium.launch()
    page = nav.new_page(viewport={"width": 1440, "height": 900})
    erreurs, vus = [], []
    page.on("console", lambda m: (vus.append(m.type),
                                  erreurs.append(m.text) if m.type == "error" else None))
    page.on("pageerror", lambda e: erreurs.append(str(e)))

    page.goto(BASE + "/admin/setup")
    page.fill("input[name=password]", "motdepasse8")
    page.click("button[type=submit]")
    page.click("a.auth-submit")
    page.wait_for_selector("#add-block-btn")
    page.click("#settings-btn")
    page.wait_for_selector("#settings-menu:not([hidden])", state="visible")

    # La hauteur d'en-tête est fixée par le jeton --top-h (53 px) : si le menu l'a fait
    # bouger, c'est un défaut. Mesuré, pas jugé à l'œil (leçon 2026-07-23).
    haut = page.evaluate("document.querySelector('.admin-top').getBoundingClientRect().height")
    print(f"hauteur d'en-tête : {haut} px (attendu 53)")

    page.screenshot(path=SORTIE, clip={"x": 0, "y": 0, "width": 1440, "height": 400})

    # Le compteur `vus` prouve que le collecteur est ARMÉ : sans lui, « aucune erreur »
    # passerait au vert même si le canal n'avait jamais été branché (leçon 2026-07-23).
    print(f"messages console vus : {len(vus)} · erreurs : {erreurs}")
    assert erreurs == [], erreurs
    assert abs(haut - 53) < 1, f"l'en-tête a changé de hauteur : {haut} px"
    nav.close()
print(f"capture écrite dans {SORTIE}")
```

- [ ] **Étape 2 : lancer un serveur, capturer, arrêter le serveur**

```bash
.venv/bin/python app.py
```

(en tâche de fond), puis lancer le script sur le port du serveur, puis **arrêter le serveur dès la capture faite** — un processus de fond laissé sur un port partagé a coûté une soirée à Nathan (leçon 2026-07-26). Arrêt par le port, jamais par un motif `pkill` non vérifié :

```bash
lsof -ti tcp:8080 | xargs kill
```

- [ ] **Étape 3 : regarder la capture**

Ouvrir l'image et contrôler ce que les tests ne voient pas : le panneau ne débord pas de la fenêtre à droite, les deux filets séparent bien trois blocs, `Redémarrer` se distingue du reste, le chevron n'écrase pas le libellé, et l'ombre ne bave pas sur les onglets. La hauteur d'en-tête, elle, est déjà mesurée par le script — ne pas la juger à l'œil.

- [ ] **Étape 4 : consigner le lot dans `tasks/todo.md`**

Ajouter à la fin de `tasks/todo.md` :

```markdown
---

# LOT 2026-07-30 — Menu « Réglages »

Spec : [docs/superpowers/specs/2026-07-30-menu-reglages-design.md](../docs/superpowers/specs/2026-07-30-menu-reglages-design.md)
Plan : [docs/superpowers/plans/2026-07-30-menu-reglages.md](../docs/superpowers/plans/2026-07-30-menu-reglages.md)

Demande Nathan : regrouper Réseau, Sauvegarde, Mot de passe, Journal et Santé dans un
menu à part. Nom retenu **Réglages** (mes réserves — Journal et Santé ne se règlent pas ;
« Système » avait déjà été supprimé le 2026-07-25 — consignées dans la spec puis tranchées),
libellé texte plutôt qu'engrenage, et **Redémarrer** ajouté au menu.

- [x] Les six fonctions vivaient dans TROIS zones (barre d'onglets, section « Boîtier » de
      la latérale, pied de latérale). Le lot corrige cette dispersion et vide la latérale de
      tout ce qui n'est pas contenu de plateau.
- [x] **Ids conservés** (`#network-btn`, `#backup-btn`, `#password-btn`, `#reboot-btn`) : les
      quatre `addEventListener` d'`admin.js` ne changent pas. Le lot est structurel.
- [x] **Sept clics e2e** visaient ces ids en direct et auraient expiré dans un menu fermé
      (Playwright attend `visible`) — repéré AVANT d'écrire le code, pas après. Helper unique
      `tests/e2e/helpers.py::open_reglages`.
- [x] Rang d'Échap tranché : décompte de publication > fermeture du menu > sortie de
      sélection. La condition « menu ouvert » entre dans le seul prédicat `onBoard`.
- [x] `.side-foot-row .nav-item` supprimée : `#reboot-btn` était son unique cible.

**Coût assumé :** Santé passe d'un clic à deux, alors que c'est le contrôle d'avant-show.
Atténuation identifiée et NON faite (point d'alerte sur le menu quand le verdict n'est pas
« Prêt ») : elle demanderait de sonder la santé depuis l'admin, ce qui n'existe pas.

**Arbitrage assumé :** le menu vit dans `admin.html` seul. `journal.html` et `health.html`
n'embarquent ni les dialogues ni `admin.js` ; y porter le menu voudrait dire les dupliquer.
Ces deux pages restent des culs-de-sac avec leur lien de retour.
```

- [ ] **Étape 5 : dernière passe complète, LIRE le résultat**

```bash
.venv/bin/pytest tests/ -q --ignore=tests/e2e
.venv/bin/pytest tests/e2e -m e2e -q
.venv/bin/ruff check .
npm test
```

⚠️ `-m e2e` est OBLIGATOIRE : sans lui, pytest répond « 30 deselected » et rend 0, ce qui
ressemble à un succès. De même, `npx vitest run --dir tests/js` n'exécute AUCUN test
(« PASS (0) FAIL (0) ») — la commande du projet est `npm test`. Se lire sur le NOMBRE de
tests exécutés, jamais sur le code retour seul.

Attendu : tout vert. (Les tests JS ne touchent pas ce lot — ils portent sur la logique pure — mais la suite complète est le seuil du projet.)

- [ ] **Étape 6 : commit**

```bash
git add tasks/todo.md
git commit -m "docs: consigner le lot du menu « Réglages »"
```

---

## Revue du plan contre la spec

**Couverture, section par section :**

| Section de la spec | Tâche |
|---|---|
| §2 en-tête cible, position en fin de `admin-tabs` | 1, étape 3 |
| §3 contenu, ordre des trois blocs, liens vs boutons | 1, étape 3 |
| §3 ids conservés | 1, étape 3 + interfaces |
| §4 suppression des anciens accès | 1, étapes 3-5 ; gardé par l'étape 1 |
| §5 balisage ARIA, ouverture/fermeture, clic extérieur | 1, étapes 3 et 8 |
| §5 Échap + retour du focus, rang entre publication et sélection | 2, étapes 3 et 7 |
| §5 `onBoard` étendu dans le seul prédicat | 2, étapes 4 et 8 |
| §5 flèches ↑↓, Entrée/Espace natifs | 2, étape 5 |
| §5 contrainte `hidden` sans `display` inconditionnel | 1, étape 6 (et contraintes globales) |
| §6 portée admin seule | aucune tâche ne touche `journal.html`/`health.html` ; arbitrage consigné en 3, étape 4 |
| §7 sept e2e existants | 1, étapes 10-11 |
| §7 tests du menu | 2, étape 1 |
| §7 garde structurelle d'unicité | 1, étape 1 |
| §7 confrontation à un échec volontaire | 1 étape 13 ; 2 étapes 7-8 |
| §7 capture + console vide | 3, étapes 1-3 |
| §8 coût assumé sur Santé | consigné, 3 étape 4 |
| §9 hors périmètre | aucune tâche ne touche au serveur ni au contenu des dialogues |

**Cohérence des noms :** `settingsOpen`, `setSettings`, `closeSettings`, `settingsBtn`, `settingsMenu`, `open_reglages`, `_fragment`, `.menu-item`, `.menu-sep`, `.menu-pop`, `.tab-menu`, `.tab-chev`, `#settings-btn`, `#settings-menu` — employés à l'identique de leur définition dans toutes les tâches.

**Point d'attention pour l'exécutant :** les numéros de ligne cités valent pour l'état du dépôt au commit `5618cad`. Ils se décalent dès la première insertion — se repérer sur les marqueurs cités (le texte de la ligne, pas son numéro), et vérifier la cible avant chaque édition.
