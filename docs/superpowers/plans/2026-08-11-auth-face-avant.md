# Pages d'authentification, la face avant assumée — plan d'implémentation

> **Pour les agents :** SOUS-COMPÉTENCE REQUISE — utiliser `superpowers:subagent-driven-development` (recommandé) ou `superpowers:executing-plans` pour exécuter ce plan tâche par tâche. Les étapes utilisent la syntaxe case à cocher (`- [x]`).

**Objectif :** donner aux pages d'authentification une composition qui occupe le cadre, une identité visible, un thème clair et des cibles tactiles conformes — sans toucher `auth.js` ni les deux gabarits de page.

**Architecture :** la grille de `body.auth` passe à deux colonnes au-delà de 900 px et **réaffecte** ses trois enfants existants (`header`, `main`, `footer`) par `grid-template-areas`. Aucun élément d'état n'est dupliqué : le voyant, l'état, la version et l'horloge sont regroupés dans le pied, qui devient la « plaque d'appareil ». Les identifiants restent inchangés, donc le JavaScript aussi.

**Pile technique :** Flask, Jinja2, CSS nu (aucun préprocesseur), pytest, Playwright.

**Conception de référence :** [docs/superpowers/specs/2026-08-11-auth-face-avant-design.md](../specs/2026-08-11-auth-face-avant-design.md)

## Contraintes globales

Ces règles s'appliquent à **toutes** les tâches.

- **Aucune nouvelle dépendance** au runtime, aucun appel CDN : le Pi tourne hors ligne.
- **`auth.css` reste autonome.** Ne jamais y charger `main.css`, ne jamais emprunter un jeton à une autre feuille.
- **Tout jeton employé doit être défini dans `auth.css`** (`test_css_tokens` lit le fichier en texte brut, commentaires compris — ne pas écrire d'exemple d'appel de jeton dans un commentaire, il serait compté comme un usage réel).
- **Aucune classe existante n'est renommée.** Huit fichiers e2e visent `.auth-go`, `.auth-code`, `.auth-field`, `.auth-error`. On n'ajoute que du nouveau.
- **Aucune modification de `static/js/auth.js`.** Si une tâche semble l'exiger, c'est que la composition est à revoir.
- **Contraste minimal 4,5:1** dans les deux thèmes.
- **Français** dans les commentaires, les noms de tests et les libellés. Les commentaires expliquent le *pourquoi*.
- **Commits en français**, préfixés `feat:` / `fix:` / `test:` / `docs:`.

---

## Structure des fichiers

| Fichier | Responsabilité | Tâches |
|---|---|---|
| `static/css/auth.css` | jetons, composition, thème clair, tactile, typographie | 1, 2, 3, 4, 5 |
| `templates/auth_base.html` | cadre commun : regroupement de la plaque, retrait de `data-theme` | 2 |
| `tests/test_auth_pages.py` | gardes sur la feuille et sur les cinq états | 1, 2, 3, 4 |
| `tools/captures.py` | captures des états d'authentification | 6 |

`templates/login.html` et `templates/setup.html` **ne sont pas touchés** : ils ne portent que le bloc `corps`.

---

## Tâche 1 : les jetons — un focus qui n'est pas une erreur, et un thème clair complet

**Fichiers :**
- Modifier : `static/css/auth.css:35-58` (bloc `:root`), `static/css/auth.css:78` (`:focus-visible`), `static/css/auth.css:171` (focus du champ)
- Test : `tests/test_auth_pages.py`

**Interfaces :**
- Produit : le jeton `--focus` et le bloc `@media (prefers-color-scheme: light)`, consommés par les tâches 2, 3 et 5.

- [x] **Étape 1 : écrire les tests qui échouent**

Ajouter à la fin de `tests/test_auth_pages.py` :

```python
# --------------------------------------------------------------------------
# Jetons : le focus et l'erreur ne doivent PAS porter le même signal, et le
# thème clair ne doit pas être livré à moitié.
# --------------------------------------------------------------------------
FEUILLE = (CSS / "auth.css").read_text(encoding="utf-8")


def _bloc_sombre():
    """Le :root de base, hors media query."""
    debut = FEUILLE.index(":root {")
    return FEUILLE[debut:FEUILLE.index("\n}", debut)]


def _bloc_clair():
    """Le bloc complet du thème clair, accolade fermante en colonne 0."""
    debut = FEUILLE.index("@media (prefers-color-scheme: light)")
    return FEUILLE[debut:FEUILLE.index("\n}", debut)]


def _jetons_couleur(bloc):
    """Les seuls jetons dont la valeur est une couleur — les mesures (--gut,
    --col…) n'ont aucune raison d'être redéfinies par un thème."""
    return {
        nom for nom, valeur in re.findall(r"(--[a-z0-9-]+)\s*:\s*([^;]+);", bloc)
        if valeur.strip().startswith("#")
    }


def _valeur(bloc, jeton):
    trouve = re.search(rf"{jeton}\s*:\s*([^;]+);", bloc)
    assert trouve, f"{jeton} n'est pas défini dans ce bloc"
    return trouve.group(1).strip().lower()


def test_le_theme_clair_redefinit_toutes_les_couleurs_du_sombre():
    """Un thème à moitié fait est le mode de panne le plus probable : un jeton
    oublié laisse un aplat sombre au milieu d'une page claire, sans un bruit."""
    manquants = _jetons_couleur(_bloc_sombre()) - _jetons_couleur(_bloc_clair())
    assert not manquants, f"jetons non redéfinis en thème clair : {sorted(manquants)}"


@pytest.mark.parametrize("nom", ["sombre", "clair"])
def test_le_focus_ne_porte_ni_la_couleur_de_l_erreur_ni_celle_de_l_accent(nom):
    """Le défaut corrigé ici : l'accent était rouge, donc un champ en autofocus
    annonçait une erreur inexistante. Sans cette garde, un futur ajustement de
    palette les rapprocherait de nouveau en silence."""
    bloc = _bloc_sombre() if nom == "sombre" else _bloc_clair()
    focus = _valeur(bloc, "--focus")
    assert focus != _valeur(bloc, "--error")
    assert focus != _valeur(bloc, "--accent")


def test_la_feuille_n_accentue_plus_le_champ_au_focus():
    """Garde de mise en œuvre : le focus doit passer par --focus, pas --accent."""
    assert "input:focus { border-color: var(--focus)" in FEUILLE
```

- [x] **Étape 2 : lancer les tests pour vérifier qu'ils échouent**

Run : `.venv/bin/python -m pytest tests/test_auth_pages.py -k "focus or theme_clair" -v`
Attendu : ÉCHEC — `--focus` absent et `@media (prefers-color-scheme: light)` introuvable (`ValueError: substring not found`).

- [x] **Étape 3 : écrire l'implémentation**

Dans `static/css/auth.css`, ajouter le jeton de focus au bloc `:root` existant, juste après la ligne `--accent` :

```css
    /* Le focus est NEUTRE, et c'est un correctif : l'accent du produit est un
       corail (#D96253) voisin de --error (#F04D3E). Un champ simplement
       focalisé portait donc le signal de l'erreur, sur un formulaire dont le
       champ est en autofocus. Pas de turquoise ici : ce serait ressusciter la
       DA abandonnée en juillet. */
    --focus: #EEF1F7;
```

Remplacer la règle globale ligne 78 :

```css
:focus-visible { outline: 2px solid var(--focus); outline-offset: 2px; }
```

Remplacer la règle du champ ligne 171 :

```css
.auth-field input:focus { border-color: var(--focus); outline: none; }
```

Puis ajouter, **après** le bloc `:root` et avant le commentaire `/* ---------- Base ---------- */` :

```css
/* ---------- Thème clair ----------
   La page est ouverte au bureau en pleine lumière autant qu'en régie : un
   aplat #141821 plein écran y devient un miroir. Aucun réglage utilisateur,
   c'est le système qui tranche. Seules les COULEURS sont redéfinies — les
   mesures (gouttière, colonne, rayon) ne dépendent pas de la lumière. */
@media (prefers-color-scheme: light) {
    :root {
        --bg: #F2F4F8; --inset: #FFFFFF; --surface: #FFFFFF; --surface-2: #E9ECF3;
        --border: #C8CEDA; --border-2: #B4BCCB; --border-soft: #DDE2EA;
        --fg: #151922; --fg-muted: #3F4756; --fg-subtle: #5C6575; --muted: #7A8393;
        --success: #1B8B4A; --warning: #9A6410; --error: #C0392B;
        /* L'accent est assombri : #D96253 ne tient pas 4,5:1 sur fond clair. */
        --accent: #B23F31; --accent-lt: #8F3227; --on-accent: #FFFFFF;
        --focus: #151922;
    }
}
```

- [x] **Étape 4 : lancer les tests pour vérifier qu'ils passent**

Run : `.venv/bin/python -m pytest tests/test_auth_pages.py -v`
Attendu : PASS sur l'ensemble du fichier, anciennes gardes comprises.

- [x] **Étape 5 : mesurer le contraste, ne pas le supposer**

```bash
.venv/bin/python - <<'PY'
import socket, threading, tempfile, sys
from werkzeug.serving import make_server
from playwright.sync_api import sync_playwright
sys.path.insert(0, ".")
from comroster import create_app

app = create_app({"DATA_DIR": tempfile.mkdtemp(), "SECRET_KEY": "x", "DEBUG": True})
s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
srv = make_server("127.0.0.1", port, app, threaded=True)
threading.Thread(target=srv.serve_forever, daemon=True).start()

def canal(v):
    return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

def lum(rgb):
    r, g, b = [canal(int(x) / 255) for x in rgb]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b

import re
with sync_playwright() as p:
    nav = p.chromium.launch()
    ctx = nav.new_context(viewport={"width": 1440, "height": 900}, color_scheme="light")
    pg = ctx.new_page(); pg.goto(f"http://127.0.0.1:{port}/admin/setup")
    couples = pg.evaluate("""() => [...document.querySelectorAll('body *')]
        .filter(e => e.textContent.trim() && !e.children.length)
        .map(e => { const s = getComputedStyle(e);
                    let f = e, bg = 'rgba(0, 0, 0, 0)';
                    while (f && bg === 'rgba(0, 0, 0, 0)') { bg = getComputedStyle(f).backgroundColor; f = f.parentElement; }
                    return [s.color, bg, e.className || e.id]; })""")
    pire = 99
    for avant, arriere, nom in couples:
        a = lum(re.findall(r"\\d+", avant)[:3])
        b = lum(re.findall(r"\\d+", arriere)[:3])
        ratio = (max(a, b) + 0.05) / (min(a, b) + 0.05)
        if ratio < pire:
            pire, coupable = ratio, nom
    print(f"pire contraste : {pire:.2f}:1 sur « {coupable} »")
    nav.close()
srv.shutdown()
PY
```

Attendu : **≥ 4,5:1**. Si un couple descend sous la barre, assombrir le jeton fautif du bloc clair et relancer. **Consigner la valeur mesurée dans le message de commit.**

- [x] **Étape 6 : committer**

```bash
git add static/css/auth.css tests/test_auth_pages.py
git commit -m "fix(auth): le focus cesse de porter le signal de l'erreur, et le thème clair existe

L'accent du produit est un corail voisin de --error. Comme le champ de
connexion porte autofocus, la page d'arrivée annonçait un problème qui
n'existait pas. Un jeton --focus neutre sépare les deux signaux.

Le thème clair suit la préférence système : la page est ouverte au bureau
autant qu'en régie. Deux gardes le tiennent — toutes les couleurs du sombre
sont redéfinies, et --focus ne peut retomber ni sur --error ni sur --accent.

Pire contraste mesuré en thème clair : <VALEUR DE L'ÉTAPE 5>."
```

---

## Tâche 2 : la composition à deux flancs

**Fichiers :**
- Modifier : `templates/auth_base.html:15-46`, `static/css/auth.css` (bandeau, corps, pied)
- Test : `tests/test_auth_pages.py`

**Interfaces :**
- Consomme : le jeton `--focus` et le bloc clair de la tâche 1.
- Produit : les zones de grille `ident` / `form` / `plate`, consommées par la tâche 5.

- [x] **Étape 1 : écrire les tests qui échouent**

```python
def test_la_plaque_regroupe_les_quatre_temoins_dans_le_pied(etats):
    """Voyant, état, version et horloge forment UNE plaque d'appareil. Groupés
    dans le pied, ils tiennent dans la même zone de grille aux deux mises en
    page — c'est ce qui évite de les dupliquer pour le flanc d'identité."""
    for nom, html in etats.items():
        pied = html[html.index('<footer class="auth-foot"'):html.index("</footer>")]
        for identifiant in ("auth-led", "auth-state", "auth-ver", "auth-clock"):
            assert f'id="{identifiant}"' in pied, f"{identifiant} hors du pied sur {nom}"


def test_aucun_identifiant_de_temoin_n_est_duplique(etats):
    """Un doublon rendrait le pilotage par auth.js silencieusement partiel :
    getElementById ne rend que le premier."""
    for nom, html in etats.items():
        for identifiant in ("auth-led", "auth-state", "auth-ver", "auth-clock"):
            assert html.count(f'id="{identifiant}"') == 1, f"{identifiant} en double sur {nom}"


def test_l_attribut_de_theme_mort_a_disparu(etats):
    """data-theme="night" n'était lu par aucune règle de la feuille, et il
    contredit désormais le thème clair automatique."""
    for nom, html in etats.items():
        assert 'data-theme="night"' not in html, f"attribut mort encore présent sur {nom}"


def test_la_feuille_compose_deux_flancs_au_dela_de_900px():
    assert "@media (min-width: 900px)" in FEUILLE
    assert "grid-template-areas" in FEUILLE


def test_le_logo_client_garde_un_fond_sombre_dans_les_deux_themes():
    """Les logos clients sont presque toujours des PNG BLANCS, dessinés pour un
    fond sombre. Sans plaque, le thème clair les rend invisibles — et c'est un
    défaut qui n'apparaît QUE chez un client ayant téléversé son logo, jamais
    en développement. Le jeton vaut donc la même valeur dans les deux thèmes."""
    assert "background: var(--plaque);" in FEUILLE
    assert _valeur(_bloc_sombre(), "--plaque") == _valeur(_bloc_clair(), "--plaque")
```

- [x] **Étape 2 : lancer les tests pour vérifier qu'ils échouent**

Run : `.venv/bin/python -m pytest tests/test_auth_pages.py -k "plaque or duplique or theme_mort or flancs" -v`
Attendu : ÉCHEC — les témoins sont aujourd'hui répartis entre bandeau et pied, et `data-theme="night"` est présent.

- [x] **Étape 3 : regrouper la plaque dans le cadre commun**

Dans `templates/auth_base.html`, remplacer la balise `<body>` ainsi que les blocs `header` et `footer` :

```html
<body class="auth">
  {# Bandeau — IDENTITÉ seule. Les témoins d'état l'ont quitté pour le pied :
     regroupés, ils forment une plaque d'appareil qui tient dans une seule zone
     de grille, et la mise en page à deux flancs n'a donc rien à dupliquer. #}
  <header class="auth-top">
    {% if brand.active %}
      <img class="auth-mark" src="{{ url_for('display.brand_logo', v=brand.version) }}" alt="{{ brand.name }}">
      <span class="auth-by">Propulsé par ComRoster</span>
    {% else %}
      <img class="auth-glyph" src="{{ url_for('static', filename='img/comroster-glyph.svg') }}" alt="" width="17" height="17">
      <span class="auth-name">ComRoster</span>
    {% endif %}
  </header>

  <main class="auth-body">
    <div class="auth-col{% block large %}{% endblock %}">
      {% block corps %}{% endblock %}
    </div>
  </main>

  {# Plaque d'appareil — le voyant démarre en « wait » et n'est promu qu'après
     une réponse RÉELLE de /healthz : au repos il n'affirme rien. L'état en
     toutes lettres double le voyant pour qui ne lit pas les couleurs. La
     version complète reste en infobulle ; /healthz la sert déjà sans session. #}
  <footer class="auth-foot">
    <span class="auth-led" id="auth-led" data-state="wait" aria-hidden="true"></span>
    <span id="auth-state">vérification…</span>
    <span class="auth-ver" id="auth-ver"{% if appversion.label %} title="{{ appversion.label }}"{% endif %}>{{ appversion.public or '' }}</span>
    <span class="auth-clock" id="auth-clock"></span>
  </footer>
```

- [x] **Étape 4 : composer les deux flancs**

Dans `static/css/auth.css`, la version quittant le bandeau pour le pied, remplacer sa règle :

```css
.auth-ver {
    margin-left: auto;
    font-family: var(--f-mono); font-size: var(--ui-sm);
    color: var(--fg-subtle); letter-spacing: var(--track);
}
```

et celle de l'horloge, qui suit désormais la version au lieu de s'en écarter :

```css
.auth-foot .auth-clock { font-family: var(--f-mono); }
```

Puis ajouter, **avant** le bloc `@media (max-width: 620px)` existant :

```css
/* ---------- Deux flancs ----------
   Au-delà de 900 px, le cadre cesse d'être trois bandes empilées : les MÊMES
   trois enfants sont réaffectés en deux colonnes. Le vide de 1024 px que
   laissait la colonne de saisie se remplit d'identité et d'état réel, pas de
   décor. Aucun nœud n'est dupliqué, donc auth.js n'a rien à savoir de tout ça. */
@media (min-width: 900px) {
    body.auth {
        grid-template-columns: 1fr minmax(420px, 520px);
        grid-template-rows: 1fr auto;
        grid-template-areas:
            "ident form"
            "plate form";
    }
    .auth-top {
        grid-area: ident;
        flex-direction: column; align-items: flex-start; justify-content: flex-end;
        gap: 16px;
        height: auto;
        padding: var(--gut);
        background: none; border-bottom: 0;
    }
    .auth-glyph { width: 56px; height: 56px; }
    /* Le logo client est un bitmap téléversé (132×21 à l'origine) : l'agrandir
       comme le glyphe vectoriel le rendrait flou. */
    .auth-mark { max-height: 40px; max-width: 240px; }
    .auth-body {
        grid-area: form;
        border-left: 1px solid var(--border-soft);
    }
    .auth-foot {
        grid-area: plate;
        height: auto;
        padding: 0 var(--gut) var(--gut);
        background: none; border-top: 0;
    }
}

/* ---------- Plaque du logo client ----------
   Les logos clients sont presque toujours des PNG BLANCS, dessinés pour un
   fond sombre. En thème clair, un tel logo deviendrait invisible — un défaut
   qui ne se voit que chez le client, jamais en développement. Le logo garde
   donc toujours un fond sombre sous lui, dans les DEUX thèmes. */
.auth-mark {
    background: var(--plaque);
    padding: 6px 10px;
    border-radius: var(--rad);
}
```

Le jeton `--plaque` est ajouté au bloc `:root` **et** au bloc clair de la tâche 1 — il vaut `#0E1119` dans les deux, puisque c'est précisément son rôle de ne pas suivre le thème :

```css
    /* Fond permanent du logo client, identique dans les deux thèmes : voir la
       règle du logo. Un jeton plutôt qu'une valeur en dur, pour que la garde
       « toutes les couleurs du sombre sont redéfinies » le voie passer. */
    --plaque: #0E1119;
```

- [x] **Étape 5 : lancer les tests, puis toute la suite**

Run : `.venv/bin/python -m pytest tests/test_auth_pages.py -v`
Puis : `.venv/bin/python -m pytest -q` et `.venv/bin/python -m pytest -q -m e2e`
Attendu : tout passe. **Si un e2e échoue, ne pas ajuster le test avant d'avoir vérifié que la page est réellement correcte** — les huit fichiers visent des classes inchangées, un échec signale donc une régression, pas un sélecteur à suivre.

- [x] **Étape 6 : vérifier le rendu réel**

Rendre `/admin/login` à 1440×900 puis à 380×740, dans les deux thèmes, et regarder :
- le flanc gauche porte glyphe, nom, puis la plaque en bas ;
- la colonne de saisie est adossée au filet vertical ;
- sous 900 px, la page reprend la forme bandeau · corps · pied ;
- aucun débord horizontal.

- [x] **Étape 7 : committer**

```bash
git add templates/auth_base.html static/css/auth.css tests/test_auth_pages.py
git commit -m "feat(auth): le cadre se compose en deux flancs au-delà de 900 px

La colonne de saisie laissait 1024 px d'aplat sur 1440. La grille du cadre
réaffecte désormais ses trois enfants en deux colonnes : identité et plaque
d'appareil à gauche, saisie à droite.

Le voyant, l'état, la version et l'horloge migrent du bandeau vers le pied et
forment une plaque unique. C'est ce regroupement qui permet de ne rien
dupliquer : mêmes nœuds, mêmes identifiants, donc auth.js est inchangé.
L'attribut mort data-theme=night disparaît au passage."
```

---

## Tâche 3 : les cibles tactiles

**Fichiers :**
- Modifier : `static/css/auth.css`
- Test : `tests/test_auth_pages.py`

**Interfaces :** consomme les jetons de la tâche 1. Ne produit rien pour les suivantes.

- [x] **Étape 1 : écrire le test qui échoue**

```python
def test_les_cibles_tactiles_atteignent_44px_au_pointeur_grossier():
    """Champ à 38 px et bouton à 34 px : sous la barre des 44 px, sur une page
    ouverte au téléphone. C'est le POINTEUR qui décide, pas la largeur — une
    fenêtre étroite pilotée à la souris garde la densité du bureau."""
    assert "@media (pointer: coarse)" in FEUILLE
    debut = FEUILLE.index("@media (pointer: coarse)")
    bloc = FEUILLE[debut:FEUILLE.index("\n}", debut)]
    hauteurs = [int(v) for v in re.findall(r"height:\s*(\d+)px", bloc)]
    assert hauteurs, "le bloc tactile ne fixe aucune hauteur"
    assert min(hauteurs) >= 44, f"cible sous 44 px : {min(hauteurs)}px"
```

- [x] **Étape 2 : lancer le test pour vérifier qu'il échoue**

Run : `.venv/bin/python -m pytest tests/test_auth_pages.py -k tactiles -v`
Attendu : ÉCHEC — `ValueError: substring not found`.

- [x] **Étape 3 : écrire l'implémentation**

Ajouter à la fin de `static/css/auth.css` :

```css
/* ---------- Pointeur grossier ----------
   La page est ouverte au téléphone et à la tablette. C'est le POINTEUR qui
   déclenche l'élargissement, pas la largeur : une fenêtre de bureau étroite
   n'a aucune raison de perdre sa densité. */
@media (pointer: coarse) {
    .auth-field input { height: 46px; }
    .auth-go { height: 46px; padding: 0 22px; }
    /* Le lien n'a pas de boîte propre : on lui en donne une, sans le déplacer. */
    .auth-link { padding: 12px 0; }
}
```

- [x] **Étape 4 : lancer les tests pour vérifier qu'ils passent**

Run : `.venv/bin/python -m pytest tests/test_auth_pages.py -v`
Attendu : PASS.

- [x] **Étape 5 : mesurer les boîtes réelles au doigt simulé**

```bash
.venv/bin/python - <<'PY'
import socket, threading, tempfile, sys
from werkzeug.serving import make_server
from playwright.sync_api import sync_playwright
sys.path.insert(0, ".")
from comroster import create_app

app = create_app({"DATA_DIR": tempfile.mkdtemp(), "SECRET_KEY": "x", "DEBUG": True})
s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
srv = make_server("127.0.0.1", port, app, threaded=True)
threading.Thread(target=srv.serve_forever, daemon=True).start()
with sync_playwright() as p:
    nav = p.chromium.launch()
    ctx = nav.new_context(viewport={"width": 380, "height": 740}, has_touch=True, is_mobile=True)
    pg = ctx.new_page(); pg.goto(f"http://127.0.0.1:{port}/admin/setup")
    for sel in ("input[name=password]", "button.auth-go"):
        print(sel, "→", pg.locator(sel).bounding_box()["height"], "px")
    nav.close()
srv.shutdown()
PY
```

Attendu : **≥ 44** pour les deux.

- [x] **Étape 6 : committer**

```bash
git add static/css/auth.css tests/test_auth_pages.py
git commit -m "fix(auth): les cibles tactiles atteignent 44 px

Champ à 38 px et bouton à 34 px sur une page ouverte au téléphone. Le seul
point média existant ne réduisait que la gouttière. L'élargissement est
déclenché par pointer: coarse et non par la largeur : une fenêtre de bureau
étroite garde sa densité."
```

---

## Tâche 4 : le code de récupération redevient déchiffrable

**Fichiers :**
- Modifier : `static/css/auth.css:57` (jeton `--f-mono`), `static/css/auth.css:231-244` (`.auth-code`)
- Test : `tests/test_auth_pages.py`

**Interfaces :** consomme les jetons de la tâche 1.

- [x] **Étape 1 : MESURER ce que contiennent les polices embarquées**

Ne rien supposer. `fonttools` est un outil de développement, installé hors du runtime du produit :

```bash
.venv/bin/pip install fonttools brotli >/dev/null
.venv/bin/python - <<'PY'
from fontTools.ttLib import TTFont
import pathlib
for f in sorted(pathlib.Path("static/fonts").glob("inter-*.woff2")):
    police = TTFont(str(f))
    traits = set()
    if "GSUB" in police and police["GSUB"].table.FeatureList:
        traits = {e.FeatureTag for e in police["GSUB"].table.FeatureList.FeatureRecord}
    print(f.name, "→", sorted(traits) or "AUCUNE fonction OpenType")
PY
```

**Décision :**
- si `zero` **et** `ss02` sont présents → voie 1 (étape 4a), aucun asset ajouté ;
- sinon → voie 2 (étape 4b), embarquer une monospace sous-ensemblée.

Consigner le résultat de la mesure dans le message de commit.

- [x] **Étape 2 : écrire le test qui échoue**

```python
def test_le_code_de_recuperation_est_rendu_sans_glyphes_ambigus():
    """C'est le SEUL texte du produit qu'un humain recopie à la main, et un
    caractère faux ferme le boîtier définitivement. Inter est proportionnelle
    et arrivait en tête de --f-mono : 0/O et 1/l/I y sont indistincts."""
    debut = FEUILLE.index(".auth-code {")
    bloc = FEUILLE[debut:FEUILLE.index("}", debut)]
    assert ("font-feature-settings" in bloc) or ("var(--f-code)" in bloc), \
        "le code est rendu sans désambiguïsation des glyphes"
```

- [x] **Étape 3 : lancer le test pour vérifier qu'il échoue**

Run : `.venv/bin/python -m pytest tests/test_auth_pages.py -k ambigus -v`
Attendu : ÉCHEC.

- [x] **Étape 4a : implémentation — voie 1 (les fonctions existent)**

Dans `.auth-code`, ajouter juste après la ligne `font-family` :

```css
    /* Zéro barré et désambiguïsation l/I/1 : présence MESURÉE dans les woff2
       embarqués (tâche 4, étape 1). Le code est déjà en capitales, ce qui
       retire l'ambiguïté restante. */
    font-feature-settings: "zero" 1, "ss02" 1;
```

- [x] **Étape 4b : implémentation — voie 2 (les fonctions ont été purgées)**

Générer un sous-ensemble limité aux caractères du code — majuscules, chiffres, tiret :

```bash
.venv/bin/pyftsubset ~/Downloads/JetBrainsMono-SemiBold.ttf \
  --unicodes="U+0030-0039,U+0041-005A,U+002D" \
  --flavor=woff2 --output-file=static/fonts/mono-code.woff2
ls -lh static/fonts/mono-code.woff2   # attendu : de l'ordre de 8 Ko
```

Déclarer la police auprès des autres `@font-face` en tête de `auth.css` :

```css
@font-face { font-family: 'CodeMono'; font-style: normal; font-weight: 600; font-display: swap; src: url('../fonts/mono-code.woff2') format('woff2'); }
```

Ajouter le jeton dans `:root` : `--f-code: 'CodeMono', ui-monospace, monospace;`
Puis dans `.auth-code`, remplacer `font-family: var(--f-mono);` par `font-family: var(--f-code);`

- [x] **Étape 5 : corriger le jeton qui ment**

Quelle que soit la voie retenue, remplacer le commentaire du jeton `--f-mono` pour qu'il cesse d'annoncer une monospace :

```css
    /* Inter à chasse tabulaire — pour les nombres alignés (heure, version),
       PAS pour du texte recopié à la main : voir la règle du code. */
    --f-mono: 'Inter', ui-monospace, monospace;
```

- [x] **Étape 6 : lancer les tests**

Run : `.venv/bin/python -m pytest tests/test_auth_pages.py -v`
Attendu : PASS, y compris l'ancienne garde `test_la_feuille_interdit_la_coupure_du_code`.

- [x] **Étape 7 : vérifier à l'œil**

Rendre `/admin/setup`, créer un compte, lire le code affiché : `0` et `O`, `1` et `I` doivent se distinguer sans hésitation. Capturer l'image.

- [x] **Étape 8 : committer**

```bash
git add static/css/auth.css tests/test_auth_pages.py
git commit -m "fix(auth): le code de récupération redevient déchiffrable

--f-mono place Inter en tête : une proportionnelle, où 0/O et 1/l/I sont
indistincts. Elle rendait le seul texte du produit qu'un humain recopie à la
main, et dont un caractère faux ferme le boîtier définitivement. La correction
précédente avait chassé Courier New pour l'auto-hébergement, sans voir qu'elle
la remplaçait par une proportionnelle.

Mesure des woff2 embarqués : <RÉSULTAT DE L'ÉTAPE 1>."
```

---

## Tâche 5 : chaleur typographique et arrivée du panneau

**Fichiers :**
- Modifier : `static/css/auth.css`

**Interfaces :** consomme les zones de grille de la tâche 2.

- [x] **Étape 1 : écrire l'implémentation**

Ajouter à l'intérieur du bloc `@media (min-width: 900px)` créé en tâche 2 :

```css
    /* La hiérarchie était plate — tout tenait entre 11,5 et 21 px. Le nom du
       produit prend l'échelle d'une sérigraphie de face avant ; le titre du
       formulaire garde ses 21 px, la distinction de rang fait le reste. */
    .auth-name { font-size: 34px; letter-spacing: 0.10em; }
    .auth-by { font-size: var(--ui); }
```

Puis, **hors** media query, à la suite de la règle `.auth-col` :

```css
/* Une seule animation, et elle est brève : la page n'est pas un spectacle. Le
   bloc prefers-reduced-motion en tête de feuille la neutralise déjà. */
@keyframes auth-arrivee {
    from { opacity: 0; transform: translateY(6px); }
    to   { opacity: 1; transform: none; }
}
.auth-col { animation: auth-arrivee 0.16s ease-out both; }
```

- [x] **Étape 2 : lancer toute la suite**

Run : `.venv/bin/python -m pytest -q` puis `.venv/bin/python -m pytest -q -m e2e`
Attendu : tout passe. Une animation d'arrivée peut rendre un e2e instable s'il agit avant sa fin — **si un test devient intermittent, RETENIR l'animation comme le fait la leçon du 2026-08-09 (mise en file via `add_init_script`, geste, puis libération), ne pas allonger une attente.**

- [x] **Étape 3 : vérifier le rendu réel**

Rendre à 1440×900 dans les deux thèmes. La page doit se lire comme composée, pas comme centrée par défaut. Vérifier que l'animation ne rejoue pas à chaque frappe dans le champ.

- [x] **Étape 4 : committer**

```bash
git add static/css/auth.css
git commit -m "feat(auth): hiérarchie typographique et arrivée du panneau

Tout tenait entre 11,5 et 21 px : une page sans rangs se lit comme un
brouillon. Le nom du produit prend l'échelle d'une sérigraphie de face avant.
Une seule animation, 160 ms, déjà neutralisée par le prefers-reduced-motion
en tête de feuille."
```

---

## Tâche 6 : les captures qui rendent les régressions visibles

**Fichiers :**
- Modifier : `tools/captures.py`

- [x] **Étape 1 : étendre le générateur**

Dans `main()`, après le bloc de l'administration et avant celui de l'écran de régie, ajouter :

```python
            # LES PAGES D'AUTHENTIFICATION, dans les deux thèmes. Cette session
            # a montré qu'une capture voit ce que 625 tests ne voient pas : un
            # champ cerclé de la couleur d'erreur au repos ne fait tomber
            # aucune assertion.
            for theme in ("dark", "light"):
                porte = navigateur.new_context(
                    viewport={"width": 1440, "height": 900}, color_scheme=theme)
                page = porte.new_page()
                page.goto(base + "/admin/login")
                page.wait_for_selector(".auth-form")
                _prendre(page, SORTIE / f"connexion-{theme}.png")
                porte.close()
```

- [x] **Étape 2 : lancer le générateur**

Run : `.venv/bin/python tools/captures.py`
Attendu : `docs/img/connexion-dark.png` et `docs/img/connexion-light.png` sont écrits ; les captures existantes restent inchangées (`git status` ne doit pas les montrer modifiées).

- [x] **Étape 3 : regarder les deux images**

Vérifier : identité à gauche, plaque en bas à gauche, saisie à droite, champ **non** cerclé de rouge au repos, texte lisible en thème clair.

- [x] **Étape 4 : committer**

```bash
git add tools/captures.py docs/img/connexion-dark.png docs/img/connexion-light.png
git commit -m "docs: les captures couvrent la connexion, dans les deux thèmes

Le générateur ignorait les pages d'authentification. C'est précisément là
qu'un défaut a échappé à 625 tests : un champ cerclé de la couleur d'erreur
au repos ne fait tomber aucune assertion."
```

---

## Revue finale

- [x] `.venv/bin/python -m pytest -q` — attendu : **565 passed** (558 existants + 7 gardes ajoutées : 1 thème clair, 2 focus paramétrés, 1 focus mis en œuvre, 4 en tâche 2, 1 tactile, 1 code — recompter à l'exécution et corriger ce chiffre s'il diffère)
- [x] `.venv/bin/python -m pytest -q -m e2e` — attendu : **67 passed**
- [x] Les cinq états relus à l'œil, dans les deux thèmes, à 1440×900 et à 380×740
- [x] **Réserve de la spec à lever :** le clavier logiciel en PAYSAGE. `body.auth` porte `overflow: hidden` et seul `.auth-body` défile. Rendre `/admin/login` à 740×380 avec `has_touch=True`, mettre le focus dans le champ et vérifier que le bouton « Se connecter » reste atteignable. S'il ne l'est pas, la correction est `min-height: 0` sur la zone de formulaire — une piste, à confirmer par la mesure et non à appliquer d'office
- [x] Le logo client vérifié en conditions réelles : téléverser un PNG blanc, ouvrir la page en thème CLAIR, le logo doit rester lisible sur sa plaque
- [x] `git diff v1.2.0..HEAD -- static/js/auth.js` rend une sortie **vide** — c'est la preuve que la restructuration est restée une affaire de mise en page


---

## Journal d'exécution — 2026-08-11

Le plan a été suivi tel quel, à deux exceptions près, l'une et l'autre nées d'une MESURE :

**Tâche 4 retournée.** Les woff2 embarqués ne portent ni `zero` ni `ss02` (seul `tnum`
survit au sous-ensemblage), donc la voie 1 était impossible. Mais surtout,
`_gen_recovery_code` tire dans `ABCDEFGHJKLMNPQRSTUVWXYZ23456789` : `I`, `O`, `0` et `1`
en sont exclus depuis toujours. Les paires à désambiguïser NE PEUVENT PAS apparaître.
Embarquer 8 Ko de monospace pour un risque inexistant a été abandonné ; l'alphabet est
devenu une constante de module, verrouillée par une garde.

**Deux défauts vus à l'écran, invisibles pour la suite de tests.** Le glyphe portait un
`fill` quasi blanc EN DUR dans le SVG : le thème clair posé en tâche 1 l'a rendu invisible
à toutes les largeurs. Il est devenu une silhouette masquée, teintée à l'accent. Et
l'identité, collée en bas du flanc (`justify-content: flex-end`), laissait tout le haut en
aplat ; centrée, elle répond à la colonne de saisie.

**Réserves levées.** Paysage tactile 740×340 : le bouton reste dans le cadre (y=251), le
corps n'a même pas besoin de défiler. Logo client en thème clair : fond calculé
`rgb(14, 17, 25)`, la plaque s'applique. Contraste mesuré : 5,34:1 en clair, 5,54:1 en
sombre. `static/js/auth.js` n'apparaît pas dans `git diff v1.2.0..HEAD --name-only`.
