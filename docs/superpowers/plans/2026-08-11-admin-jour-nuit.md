# Administration jour · nuit · auto — plan d'implémentation

> **Pour les agents :** SOUS-COMPÉTENCE REQUISE — utiliser `superpowers:subagent-driven-development` (recommandé) ou `superpowers:executing-plans` pour exécuter ce plan tâche par tâche. Les étapes utilisent la syntaxe case à cocher (`- [ ]`).

**Objectif :** un sélecteur à trois positions dans le pied de l'administration — Auto, Clair, Sombre — qui change son apparence et s'en souvient.

**Architecture :** le choix voyage par cookie ; la vue `admin_page` le valide contre une liste blanche et le gabarit rend `data-theme`, ce qui supprime l'éclair de thème sans toucher à la CSP (qui interdit les scripts en ligne). Le mode `auto` est du CSS pur (`prefers-color-scheme`). La palette claire est écrite deux fois — aucune construction CSS ne partage un bloc entre une media query et un sélecteur — et une garde exige que les deux copies soient identiques.

**Pile technique :** Flask, Jinja2, CSS nu (aucun préprocesseur), JavaScript nu, pytest, Playwright.

**Conception de référence :** [docs/superpowers/specs/2026-08-11-admin-jour-nuit-design.md](../specs/2026-08-11-admin-jour-nuit-design.md)

## Contraintes globales

- **CSP `default-src 'self'`** (`comroster/__init__.py:160`) : aucun script en ligne. Ne pas l'affaiblir.
- **CSS nu, aucun préprocesseur. Aucune nouvelle dépendance**, aucun appel CDN.
- **Tout jeton employé doit être défini dans `admin.css`** (`test_css_tokens` lit le fichier en texte brut, commentaires compris — ne pas y écrire d'exemple d'appel de jeton).
- **Aucune classe existante n'est renommée** : 18 fichiers e2e visent l'administration.
- **Français** dans les commentaires, les noms de tests et les libellés.
- **Commits en français**, préfixés `feat:` / `fix:` / `test:` / `docs:`.
- **Valeurs admises du thème : `auto`, `day`, `night`.** Toute autre valeur retombe sur `auto`.

---

## Structure des fichiers

| Fichier | Responsabilité | Tâches |
|---|---|---|
| `comroster/api.py` | lecture et validation du cookie dans `admin_page` | 1 |
| `templates/admin.html` | `data-theme` dynamique, sélecteur dans le pied | 1, 4 |
| `static/css/admin.css` | palette claire ×2, jetons de voile et d'ombre, style du sélecteur | 2, 3, 4 |
| `static/js/admin.js` | écriture du cookie, bascule immédiate, `aria-pressed` | 4 |
| `tests/test_ui.py` | gardes serveur et feuille | 1, 2, 3, 4 |
| `README.md` | la section « Apparence de l'administration », et le changement de défaut | 4 |
| `tests/e2e/test_apparence_admin.py` | parcours des trois modes | 5 |

---

## Tâche 1 : le choix voyage par cookie, et le serveur le rend

**Fichiers :**
- Modifier : `comroster/api.py:47-50` (vue `admin_page`), `templates/admin.html:13` (`<body>`)
- Test : `tests/test_ui.py`

**Interfaces :**
- Produit : la variable de gabarit `theme_ui` (valeur `"auto"` | `"day"` | `"night"`) et l'attribut `body[data-theme]`, consommés par les tâches 2, 3, 4 et 5.

- [ ] **Étape 1 : écrire les tests qui échouent**

Ajouter à la fin de `tests/test_ui.py` :

```python
# --------------------------------------------------------------------------
# Apparence de l'administration : le choix vient d'un cookie, donc de
# l'utilisateur — il ne doit JAMAIS atterrir tel quel dans un attribut.
# `re` et `pytest` sont déjà importés en tête de ce fichier.
# --------------------------------------------------------------------------
@pytest.mark.parametrize("cookie,attendu", [
    (None, "auto"),          # aucun choix : on suit le système
    ("auto", "auto"),
    ("day", "day"),
    ("night", "night"),
])
def test_le_cookie_de_theme_pilote_l_attribut(auth_client, cookie, attendu):
    if cookie:
        auth_client.set_cookie("comroster_theme", cookie)
    html = auth_client.get("/admin").get_data(as_text=True)
    assert f'data-theme="{attendu}"' in html


@pytest.mark.parametrize("hostile", [
    'night" onload="alert(1)',        # évasion d'attribut
    "<script>alert(1)</script>",
    "jour",                            # simplement inconnue
    "",
    "DAY",                             # la casse n'est pas une valeur admise
])
def test_un_cookie_hostile_ou_inconnu_retombe_sur_auto(auth_client, hostile):
    """Une valeur de cookie est une DONNÉE UTILISATEUR. Rendue sans liste blanche
    dans un attribut HTML, elle en sort — Jinja échappe les guillemets, mais on ne
    veut pas dépendre de cet échappement pour une valeur qui n'a que trois formes
    légitimes. La liste blanche est la garde, l'échappement n'est que le filet."""
    auth_client.set_cookie("comroster_theme", hostile)
    html = auth_client.get("/admin").get_data(as_text=True)
    assert 'data-theme="auto"' in html
    assert "onload" not in html
    assert "<script>alert" not in html
```

- [ ] **Étape 2 : lancer les tests pour vérifier qu'ils échouent**

Run : `.venv/bin/python -m pytest tests/test_ui.py -k "theme" -v`
Attendu : ÉCHEC — `data-theme="night"` est écrit en dur dans le gabarit, donc `auto` et `day` ne sortent jamais.

- [ ] **Étape 3 : écrire l'implémentation — la vue**

Dans `comroster/api.py`, remplacer la vue `admin_page` :

```python
#: Les trois seules apparences admises. Le cookie est une donnée UTILISATEUR :
#: elle ne va pas dans un attribut HTML sans passer par cette liste.
THEMES_UI = ("auto", "day", "night")


@bp.get("/admin")
@login_required
def admin_page():
    choix = request.cookies.get("comroster_theme", "auto")
    return render_template(
        "admin.html",
        initial_data=_storage().load_draft(),
        theme_ui=choix if choix in THEMES_UI else "auto",
    )
```

Vérifier que `request` est bien importé depuis `flask` en tête de `comroster/api.py` ; l'ajouter à l'import existant s'il manque.

- [ ] **Étape 4 : écrire l'implémentation — le gabarit**

Dans `templates/admin.html`, remplacer la balise `<body>` :

```html
{# `data-theme` vient du COOKIE, rendu ici par le serveur et non posé par le
   JavaScript : la CSP interdit les scripts en ligne, et un script différé
   ferait clignoter l'admin en sombre avant de basculer en clair. `data-login`
   sert au bandeau « Session expirée ». #}
<body class="admin-page" data-theme="{{ theme_ui }}" data-login="{{ url_for('auth.login') }}">
```

- [ ] **Étape 5 : lancer les tests**

Run : `.venv/bin/python -m pytest tests/test_ui.py -v` puis `.venv/bin/python -m pytest -q`
Attendu : PASS. **Rien ne change encore à l'écran** — `body[data-theme="auto"]` n'a pas de règle : c'est normal, la palette arrive en tâche 2.

- [ ] **Étape 6 : committer**

```bash
git add comroster/api.py templates/admin.html tests/test_ui.py
git commit -m "feat(admin): l'apparence vient d'un cookie, validé et rendu par le serveur

data-theme était écrit en dur à night. Il vient désormais du cookie
comroster_theme, validé contre une liste blanche de trois valeurs — une valeur
de cookie est une donnée utilisateur, et elle n'atterrit pas dans un attribut
HTML sans contrôle.

Le serveur le rend plutôt qu'un script : la CSP interdit les scripts en ligne,
et un script différé ferait clignoter l'admin en sombre avant de basculer."
```

---

## Tâche 2 : la palette claire, écrite deux fois et verrouillée

**Fichiers :**
- Modifier : `static/css/admin.css` (après le bloc `:root`)
- Test : `tests/test_ui.py`

**Interfaces :**
- Consomme : l'attribut `body[data-theme]` de la tâche 1.
- Produit : le bloc de palette claire, complété par la tâche 3 avec les jetons de voile et d'ombre.

- [ ] **Étape 1 : écrire les tests qui échouent**

```python
ADMIN_CSS = (STATIC_CSS / "admin.css").read_text(encoding="utf-8")   # STATIC_CSS existe déjà (test_ui.py:8)


def _bloc(depart):
    """Le bloc CSS ouvert à `depart`, jusqu'à son accolade fermante en colonne 0."""
    d = ADMIN_CSS.index(depart)
    return ADMIN_CSS[d:ADMIN_CSS.index("\n}", d)]


def _declarations(bloc):
    """Les paires jeton/valeur, mises à plat — l'indentation et les commentaires
    diffèrent entre les deux copies, pas les valeurs."""
    return re.findall(r"(--[a-z0-9-]+)\s*:\s*([^;]+);", bloc)


def test_les_deux_palettes_claires_sont_identiques():
    """La palette claire est écrite DEUX fois : sous la media query pour le mode
    auto, sous l'attribut pour le mode forcé. Aucune construction CSS ne partage
    un bloc entre une media query et un sélecteur — c'est le coût du CSS nu.

    Deux copies qui divergent est le mode de panne garanti : cette garde est ce
    qui rend la duplication tenable."""
    auto = _declarations(_bloc('body[data-theme="auto"]'))
    force = _declarations(_bloc('body[data-theme="day"]'))
    assert auto == force, "les deux palettes claires ont divergé"


def test_le_theme_clair_redefinit_toutes_les_couleurs_du_sombre():
    """Un jeton oublié laisse un aplat sombre au milieu d'une page claire, et
    rien ne le signale — ni test, ni erreur, ni console."""
    def couleurs(bloc):
        return {n for n, v in _declarations(bloc) if v.strip().startswith(("#", "rgb"))}
    manquants = couleurs(_bloc(":root {")) - couleurs(_bloc('body[data-theme="day"]'))
    assert not manquants, f"jetons non redéfinis en clair : {sorted(manquants)}"
```

- [ ] **Étape 2 : lancer les tests pour vérifier qu'ils échouent**

Run : `.venv/bin/python -m pytest tests/test_ui.py -k "palette or theme_clair" -v`
Attendu : ÉCHEC — `ValueError: substring not found`, aucun bloc clair n'existe.

- [ ] **Étape 3 : écrire la palette claire**

Ajouter dans `static/css/admin.css`, immédiatement après l'accolade fermante du bloc `:root` :

```css
/* ---------- Apparence claire ----------
   ÉCRITE DEUX FOIS, et ce n'est pas une négligence : aucune construction CSS nu
   ne partage un bloc de déclarations entre une media query et un sélecteur. La
   première copie sert le mode « auto » (le système décide), la seconde le mode
   forcé depuis le pied. Une garde exige qu'elles restent identiques.

   Le mode « night » n'a pas de bloc : c'est le :root ci-dessus. */
@media (prefers-color-scheme: light) {
    body[data-theme="auto"] {
        --bg: #F2F4F8; --inset: #FFFFFF; --surface: #FFFFFF;
        --surface-2: #E9ECF3; --surface-3: #DFE4EE;
        --border: #C8CEDA; --border-2: #B4BCCB; --border-3: #9AA4B6;
        --border-soft: #DDE2EA;
        --fg: #151922; --fg-muted: #3F4756; --fg-subtle: #5C6575; --muted: #7A8393;
        --success: #1B8B4A; --warning: #9A6410; --error: #C0392B;
        --danger: #B33322; --danger-line: #E7C3BD; --danger-bg: #FBEDEA;
        --accent: #B23F31; --accent-lt: #8F3227; --on-accent: #FFFFFF;
    }
}

body[data-theme="day"] {
    --bg: #F2F4F8; --inset: #FFFFFF; --surface: #FFFFFF;
    --surface-2: #E9ECF3; --surface-3: #DFE4EE;
    --border: #C8CEDA; --border-2: #B4BCCB; --border-3: #9AA4B6;
    --border-soft: #DDE2EA;
    --fg: #151922; --fg-muted: #3F4756; --fg-subtle: #5C6575; --muted: #7A8393;
    --success: #1B8B4A; --warning: #9A6410; --error: #C0392B;
    --danger: #B33322; --danger-line: #E7C3BD; --danger-bg: #FBEDEA;
    --accent: #B23F31; --accent-lt: #8F3227; --on-accent: #FFFFFF;
}
```

- [ ] **Étape 4 : lancer les tests**

Run : `.venv/bin/python -m pytest tests/test_ui.py -v` puis `.venv/bin/python -m pytest -q`
Attendu : PASS.

- [ ] **Étape 5 : regarder l'écran, thème forcé clair**

Rendre `/admin` avec le cookie `comroster_theme=day` et capturer. **Attendu : une page claire mais ENCORE FAUTIVE** — les voiles blancs et les ombres n'ont pas encore de jeton, c'est l'objet de la tâche 3. Garder la capture pour comparaison.

- [ ] **Étape 6 : committer**

```bash
git add static/css/admin.css tests/test_ui.py
git commit -m "feat(admin): une palette claire, écrite deux fois et verrouillée

Le mode auto passe par une media query, le mode forcé par un sélecteur, et
aucune construction CSS nu ne partage un bloc entre les deux. La duplication
est donc inhérente : une garde exige que les deux copies restent identiques,
sans quoi elles divergeraient en silence.

Les voiles et ombres écrits en dur ne suivent pas encore — tâche suivante."
```

---

## Tâche 3 : les couleurs en dur deviennent des jetons

**Fichiers :**
- Modifier : `static/css/admin.css` (33 valeurs distinctes hors `:root`, relevées ci-dessous)
- Test : `tests/test_ui.py`

**Interfaces :**
- Consomme : les deux blocs clairs de la tâche 2, qu'il faut compléter des nouveaux jetons.

**Relevé de départ** (mesuré le 2026-08-11, lignes indicatives) :

| Famille | Valeurs | Traitement |
|---|---|---|
| Voiles blancs | `#ffffff08` (l.105, 122, 150, 164, 245, 261), `#ffffff0d` (l.207), `#ffffff14` (l.210) | `--voile-1/2/3` — **s'inversent** en clair : un blanc à 3 % éclaircit une surface sombre et disparaît sur une claire |
| Ombres | `rgb(0 0 0 / 0.5)` (l.788, 1183, 1212), `/ 0.3` (l.483, 1197), `/ 0.25` (l.854, 857), `/ 0.17` (l.383), `/ 0.35` (l.400), `/ 0.1` (l.447), `/ 0.12` (l.448), `/ 0.55` (l.774), `#00000088` (l.140), `rgb(4 6 10 / 0.62)` (l.790) | `--ombre-…` — restent noires mais **plus faibles** en clair |
| Dérivées de l'accent | `rgb(217 98 83 / 0.1)` (l.532, 887), `/ 0.12` (l.968), `/ 0.14` (l.288), `/ 0.18` (l.839), `/ 0.22` (l.1221), `/ 0.32` (l.888) | `--accent-a10/a12/a14/a18/a22/a32` — l'accent CHANGE en clair, ces teintes aussi |
| Dérivées du succès | `rgb(46 204 113 / 0.24)` (l.1230), `/ 0.45` (l.1236), `/ 0.85` (l.1235) | `--succes-a24/a45/a85` |
| Dérivées de l'erreur | `rgba(240, 77, 62, 0.12)` (l.882), `rgba(240, 77, 62, 0.4)` (l.883) | `--erreur-a12/a40` |
| Doublons de jetons | `#141005` (l.377, 550, 822) | remplacer par `var(--on-accent)` — pure dette |
| Ponctuelles | `#F4F7FB` (l.378, 551), `#FFFFFF` (l.820), `#ffffff` (l.298), `#000` (l.679, 752, 864), `#131722` (l.843), `#2A1F14` (l.262), `#E2604F` (l.821), `#F2B457` (l.823) | à décider **une par une**, au vu de leur usage réel |

- [ ] **Étape 1 : écrire le test qui échoue**

```python
#: Littéraux de couleur TOLÉRÉS hors du :root d'admin.css. La liste est CLOSE :
#: en ajouter un fera échouer ce test, ce qui force la décision au moment de
#: l'écriture. C'est la réponse directe à la leçon du 2026-08-11 — le thème clair
#: des pages d'authentification a rendu invisible un glyphe dont la couleur était
#: figée dans son fichier, sans qu'aucun des 636 tests ne bronche.
LITTERAUX_TOLERES = set()   # à compléter à l'étape 4, avec un commentaire par entrée


def test_aucune_couleur_en_dur_non_justifiee_dans_admin_css():
    hors_root = ADMIN_CSS.replace(_bloc(":root {"), "")
    hors_root = re.sub(r"/\*.*?\*/", "", hors_root, flags=re.S)   # les commentaires citent des couleurs
    for bloc in ('body[data-theme="auto"]', 'body[data-theme="day"]'):
        hors_root = hors_root.replace(_bloc(bloc), "")
    trouvees = set(re.findall(r"#[0-9A-Fa-f]{3,8}\b|rgba?\([^)]*\)", hors_root))
    surplus = trouvees - LITTERAUX_TOLERES
    assert not surplus, (
        "couleurs en dur non justifiées — les promouvoir en jetons pour "
        "qu'elles suivent le thème, ou les ajouter à LITTERAUX_TOLERES avec "
        f"un commentaire disant pourquoi elles n'en dépendent pas : {sorted(surplus)}")
```

- [ ] **Étape 2 : lancer le test pour vérifier qu'il échoue**

Run : `.venv/bin/python -m pytest tests/test_ui.py -k couleur_en_dur -v`
Attendu : ÉCHEC listant les 33 valeurs.

- [ ] **Étape 3 : promouvoir les familles en jetons**

Ajouter au bloc `:root` (valeurs sombres actuelles, inchangées à l'œil) :

```css
    /* Voiles et ombres : ils s'INVERSENT avec le thème. Un blanc à 3 % éclaircit
       une surface sombre et disparaît sur une surface claire ; une ombre noire à
       50 % écrase une page claire. Jetons, donc — pas des littéraux. */
    --voile-1: #ffffff08; --voile-2: #ffffff0d; --voile-3: #ffffff14;
    --ombre-faible: rgb(0 0 0 / 0.17); --ombre: rgb(0 0 0 / 0.3);
    --ombre-forte: rgb(0 0 0 / 0.5); --ombre-portee: rgb(0 0 0 / 0.25);
    /* Teintes dérivées de l'accent, du succès et de l'erreur : leurs bases
       changent en clair, ces dérivées doivent suivre. */
    --accent-a10: rgb(217 98 83 / 0.1); --accent-a12: rgb(217 98 83 / 0.12);
    --accent-a14: rgb(217 98 83 / 0.14); --accent-a18: rgb(217 98 83 / 0.18);
    --accent-a22: rgb(217 98 83 / 0.22); --accent-a32: rgb(217 98 83 / 0.32);
    --succes-a24: rgb(46 204 113 / 0.24); --succes-a45: rgb(46 204 113 / 0.45);
    --succes-a85: rgb(46 204 113 / 0.85);
    --erreur-a12: rgb(240 77 62 / 0.12); --erreur-a40: rgb(240 77 62 / 0.4);
```

Et leurs équivalents clairs, dans **les deux** blocs de la tâche 2 :

```css
    /* Le voile s'inverse : du noir très dilué sur des surfaces claires. */
    --voile-1: #00000008; --voile-2: #0000000d; --voile-3: #00000014;
    /* Les ombres s'allègent : sur fond clair, les mêmes opacités écrasent. */
    --ombre-faible: rgb(0 0 0 / 0.06); --ombre: rgb(0 0 0 / 0.10);
    --ombre-forte: rgb(0 0 0 / 0.18); --ombre-portee: rgb(0 0 0 / 0.09);
    /* Dérivées de l'accent clair #B23F31 = rgb(178 63 49). */
    --accent-a10: rgb(178 63 49 / 0.1); --accent-a12: rgb(178 63 49 / 0.12);
    --accent-a14: rgb(178 63 49 / 0.14); --accent-a18: rgb(178 63 49 / 0.18);
    --accent-a22: rgb(178 63 49 / 0.22); --accent-a32: rgb(178 63 49 / 0.32);
    /* Dérivées du succès clair #1B8B4A = rgb(27 139 74). */
    --succes-a24: rgb(27 139 74 / 0.24); --succes-a45: rgb(27 139 74 / 0.45);
    --succes-a85: rgb(27 139 74 / 0.85);
    /* Dérivées de l'erreur claire #C0392B = rgb(192 57 43). */
    --erreur-a12: rgb(192 57 43 / 0.12); --erreur-a40: rgb(192 57 43 / 0.4);
```

Puis remplacer chaque occurrence hors `:root` par son jeton. Les ombres qui ne
tombent sur aucune des quatre intensités retenues (`/ 0.1`, `/ 0.12`, `/ 0.35`,
`/ 0.55`, `#00000088`, `rgb(4 6 10 / 0.62)`) sont rapprochées du jeton le plus
proche — **sauf** si l'écart se voit à l'écran, auquel cas ajouter un jeton
plutôt que de forcer.

Remplacer les trois `#141005` par `var(--on-accent)` : c'est exactement sa valeur.

- [ ] **Étape 4 : décider des huit ponctuelles, une par une**

Pour chacune — `#F4F7FB` (l.378, 551), `#FFFFFF` (l.820), `#ffffff` (l.298), `#000` (l.679, 752, 864), `#131722` (l.843), `#2A1F14` (l.262), `#E2604F` (l.821), `#F2B457` (l.823) — **lire la règle qui la porte** et trancher :

- elle habille une surface, un texte ou une bordure → **jeton**, redéfini en clair ;
- elle est structurellement invariante (encre d'un badge coloré, couleur de marque, valeur de repli d'un canevas) → **la garder**, l'ajouter à `LITTERAUX_TOLERES` avec un commentaire disant pourquoi.

Ne pas trancher au vu de la valeur seule : `#FFFFFF` peut être une surface (à basculer) ou l'encre d'une pastille colorée (invariante).

- [ ] **Étape 5 : lancer les tests**

Run : `.venv/bin/python -m pytest tests/test_ui.py -v` puis `.venv/bin/python -m pytest -q`
Attendu : PASS, y compris `test_les_deux_palettes_claires_sont_identiques` — les nouveaux jetons ont été ajoutés aux DEUX copies.

- [ ] **Étape 6 : comparer les deux captures**

Reprendre la capture de la tâche 2 (étape 5) et en refaire une. Les voiles et ombres doivent avoir disparu du rendu clair. Parcourir aussi les panneaux Historique, Configurations et Impression : ce sont eux qui portent l'essentiel des dérivées d'accent et de succès.

- [ ] **Étape 7 : committer**

```bash
git add static/css/admin.css tests/test_ui.py
git commit -m "fix(admin): les voiles, ombres et teintes dérivées suivent le thème

33 couleurs étaient écrites en dur hors du :root. La plupart sont des voiles
semi-transparents et des ombres — précisément ce qui s'inverse : un blanc à 3 %
éclaircit une surface sombre et DISPARAÎT sur une surface claire.

Elles deviennent des jetons, redéfinis dans les deux palettes claires. Une garde
tient désormais la liste close des littéraux tolérés : en ajouter un fera
échouer le test et forcera la décision à l'écriture, au lieu de laisser passer
un aplat qui ne se verrait que chez l'utilisateur."
```

---

## Tâche 4 : le sélecteur dans le pied

**Fichiers :**
- Modifier : `templates/admin.html:340-350` (pied), `static/css/admin.css` (fin), `static/js/admin.js` (près de l'init)
- Test : `tests/test_ui.py`

**Interfaces :**
- Consomme : `body[data-theme]` (tâche 1), les palettes (tâches 2 et 3).
- Produit : le groupe `.theme-switch` et ses trois boutons `[data-theme-choice]`, visés par l'e2e de la tâche 5.

- [ ] **Étape 1 : écrire les tests qui échouent**

```python
def test_le_pied_porte_un_selecteur_d_apparence_accessible(auth_client):
    """Trois boutons nommés, pas trois pictogrammes : un soleil et une lune ne
    disent pas laquelle est active."""
    html = auth_client.get("/admin").get_data(as_text=True)
    pied = html[html.index('<footer class="admin-status"'):html.index("</footer>")]
    assert 'class="s theme-switch"' in pied
    assert 'role="group"' in pied
    assert "aria-label" in pied
    for valeur, libelle in (("auto", "Auto"), ("day", "Clair"), ("night", "Sombre")):
        assert f'data-theme-choice="{valeur}"' in pied
        assert f">{libelle}<" in pied


def test_le_segment_actif_reflete_le_cookie(auth_client):
    """aria-pressed doit dire la vérité dès le rendu serveur : sans cela, un
    lecteur d'écran annonce trois boutons non pressés sur une page qui EST claire."""
    auth_client.set_cookie("comroster_theme", "day")
    html = auth_client.get("/admin").get_data(as_text=True)
    assert 'data-theme-choice="day" aria-pressed="true"' in html
    assert 'data-theme-choice="auto" aria-pressed="false"' in html
```

- [ ] **Étape 2 : lancer les tests pour vérifier qu'ils échouent**

Run : `.venv/bin/python -m pytest tests/test_ui.py -k "selecteur or segment" -v`
Attendu : ÉCHEC — le pied ne contient aucun sélecteur.

- [ ] **Étape 3 : le gabarit**

Dans `templates/admin.html`, à l'intérieur du `<footer class="admin-status">`, **avant** `<span class="s status-right">` :

```html
      {# Trois segments plats — le vocabulaire de l'admin, qui a abandonné les
         pilules. `aria-pressed` est posé PAR LE SERVEUR : il doit être vrai dès
         le premier rendu, avant que le moindre script ne tourne. #}
      <span class="s theme-switch" role="group" aria-label="Apparence de l'administration">
        <button type="button" data-theme-choice="auto" aria-pressed="{{ 'true' if theme_ui == 'auto' else 'false' }}">Auto</button>
        <button type="button" data-theme-choice="day" aria-pressed="{{ 'true' if theme_ui == 'day' else 'false' }}">Clair</button>
        <button type="button" data-theme-choice="night" aria-pressed="{{ 'true' if theme_ui == 'night' else 'false' }}">Sombre</button>
      </span>
```

- [ ] **Étape 4 : le style**

Ajouter à la fin de `static/css/admin.css` :

```css
/* ---------- Sélecteur d'apparence ---------- */
.theme-switch { display: inline-flex; gap: 2px; }
.theme-switch button {
    padding: 2px 9px;
    border: 1px solid var(--border-soft); border-radius: 5px;
    background: none; color: var(--fg-subtle);
    font: inherit; cursor: pointer;
}
.theme-switch button:hover { color: var(--fg); border-color: var(--border-2); }
.theme-switch button[aria-pressed="true"] {
    background: var(--surface-3); color: var(--fg); border-color: var(--border-2);
}
```

- [ ] **Étape 5 : le comportement**

Dans `static/js/admin.js`, ajouter juste avant le bloc `/* ---------- Init ---------- */` :

```js
  /* ---------- Sélecteur d'apparence ----------
     Le cookie, et non localStorage : c'est le SERVEUR qui rend `data-theme`, ce
     qui supprime l'éclair de thème au chargement. La CSP interdisant les scripts
     en ligne, aucun script ne peut s'exécuter avant le premier rendu. */
  function poserTheme(choix) {
    const an = 60 * 60 * 24 * 365;
    document.cookie = `comroster_theme=${choix}; path=/; max-age=${an}; SameSite=Lax`;
    document.body.dataset.theme = choix;      // bascule immédiate, sans rechargement
    document.querySelectorAll("[data-theme-choice]").forEach((b) => {
      b.setAttribute("aria-pressed", String(b.dataset.themeChoice === choix));
    });
  }
  document.querySelectorAll("[data-theme-choice]").forEach((bouton) => {
    bouton.addEventListener("click", () => poserTheme(bouton.dataset.themeChoice));
  });
```

- [ ] **Étape 6 : lancer les tests**

Run : `.venv/bin/python -m pytest -q`
Attendu : PASS.

- [ ] **Étape 7 : documenter le changement de comportement**

Ajouter au `README.md`, dans la section « Premier démarrage », juste après la liste numérotée :

```markdown
### Apparence de l'administration

Trois positions dans le pied : **Auto** (défaut), **Clair**, **Sombre**. Le choix est
propre à ce navigateur — il ne modifie pas ce que voit la salle. Le mode de luminosité
de l'écran de régie reste dans Réglages → Écran, et voyage avec l'état publié.

> Depuis l'introduction de ce réglage, un poste dont le système est en clair ouvrira
> l'administration **en clair** : c'est le mode Auto. Deux clics dans le pied suffisent
> à forcer le sombre, et le choix est mémorisé.
```

Cette note n'est pas décorative : jusqu'ici tout le monde voyait l'administration en
sombre sans exception. Le défaut change pour les utilisateurs existants.

- [ ] **Étape 8 : committer**

```bash
git add templates/admin.html static/css/admin.css static/js/admin.js tests/test_ui.py README.md
git commit -m "feat(admin): un sélecteur Auto · Clair · Sombre dans le pied

Trois segments plats, role=group et aria-pressed posé par le SERVEUR : il doit
dire la vérité dès le premier rendu, avant qu'aucun script ne tourne. Libellés
en toutes lettres — un soleil et une lune ne disent pas laquelle est active.

Au clic, le cookie est écrit et l'attribut change : la bascule est immédiate,
sans rechargement."
```

---

## Tâche 5 : le parcours des trois modes, vu du navigateur

**Fichiers :**
- Créer : `tests/e2e/test_apparence_admin.py`

- [ ] **Étape 1 : écrire le test**

```python
"""Le sélecteur d'apparence de l'administration, éprouvé au navigateur.

L'attribut seul ne prouve rien : il faut vérifier que la PALETTE s'applique,
c'est-à-dire que le fond calculé change réellement. Et « auto » ne se teste
qu'en simulant la préférence système, ce que seul un vrai navigateur permet.

Exclus par défaut (marqueur `e2e`). Lancer :
    .venv/bin/pytest tests/e2e -m e2e
"""
import pytest

from helpers import enter_admin

pytestmark = pytest.mark.e2e


def _fond(page):
    return page.evaluate("getComputedStyle(document.body).backgroundColor")


def test_les_trois_modes_changent_reellement_la_palette(page, live_server):
    enter_admin(page, live_server)
    page.click('[data-theme-choice="night"]')
    sombre = _fond(page)

    page.click('[data-theme-choice="day"]')
    clair = _fond(page)
    assert clair != sombre, "le mode clair ne change pas le fond réel"
    assert page.get_attribute('[data-theme-choice="day"]', "aria-pressed") == "true"
    assert page.get_attribute('[data-theme-choice="night"]', "aria-pressed") == "false"

    # Le choix survit au rechargement — c'est le cookie, rendu par le serveur.
    page.reload()
    page.wait_for_selector("#add-block-btn")
    assert _fond(page) == clair, "le choix n'a pas survécu au rechargement"
    assert page.evaluate("document.body.dataset.theme") == "day"


def test_le_mode_auto_suit_la_preference_du_systeme(page, live_server):
    """« auto » est du CSS pur : c'est la media query qui tranche, sans JS."""
    enter_admin(page, live_server)
    page.click('[data-theme-choice="auto"]')

    page.emulate_media(color_scheme="dark")
    sombre = _fond(page)
    page.emulate_media(color_scheme="light")
    clair = _fond(page)
    assert clair != sombre, "en mode auto, la préférence système ne change rien"

    # Forcer « Sombre » doit IGNORER un système réglé en clair.
    page.click('[data-theme-choice="night"]')
    assert _fond(page) == sombre, "le mode forcé se laisse dicter par le système"
```

- [ ] **Étape 2 : lancer le test**

Run : `.venv/bin/python -m pytest tests/e2e/test_apparence_admin.py -m e2e -q`
Attendu : PASS. En cas d'échec sur `_fond`, vérifier que `body` porte bien un fond (et non `html`) — auquel cas lire `getComputedStyle(document.documentElement).backgroundColor`.

- [ ] **Étape 3 : committer**

```bash
git add tests/e2e/test_apparence_admin.py
git commit -m "test(e2e): les trois apparences de l'admin, éprouvées au navigateur

L'attribut ne prouve pas que la palette s'applique : ces tests lisent le fond
CALCULÉ. Le mode auto est vérifié en simulant la préférence système dans les
deux sens, et le mode forcé en vérifiant qu'il l'ignore."
```

---

## Revue finale

- [ ] `.venv/bin/python -m pytest -q` — attendu : 570 plus les gardes ajoutées (recompter à l'exécution)
- [ ] `.venv/bin/python -m pytest -q -m e2e` — attendu : 69 plus 2
- [ ] Les quatre onglets (Affectations, Écran, Intercom, Réglages) et les trois panneaux (Historique, Configurations, Impression) relus **à l'œil en mode clair** — c'est là que se cachent les dérivées d'accent et de succès
- [ ] Le dialogue d'ajout de beltpack et le menu contextuel, ouverts en clair : ils portent des voiles et des ombres
- [ ] La bascule ne provoque **aucun éclair** au rechargement, sur un système réglé en clair
- [ ] `git grep -n 'data-theme="night"' -- templates/` ne rend plus que `display.html`, dont le thème est publié et hors périmètre
