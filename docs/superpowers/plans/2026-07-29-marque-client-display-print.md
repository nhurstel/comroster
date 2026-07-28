# Marque client sur `/display` et `/print` — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal :** permettre au logo d'un client de remplacer celui de ComRoster sur `/display` et
`/print`, via un pack posé à la fabrication que l'administration ne peut pas modifier.

**Architecture :** un service `Branding` lit un dossier système (`COMROSTER_BRAND_DIR`) une
seule fois au démarrage et n'expose que des attributs en lecture. Deux routes servent les
fichiers ; un `context_processor` injecte l'objet dans tous les templates ; sans pack, tout
retombe au comportement d'aujourd'hui.

**Tech Stack :** Python 3.12, Flask, Jinja2, pytest, ruff, bash (script de fabrication).

**Spec de référence :**
[docs/superpowers/specs/2026-07-29-marque-client-display-print-design.md](../specs/2026-07-29-marque-client-display-print-design.md)
(commit `bad74aa`).

## Global Constraints

- **Base de code francophone** : commentaires, docstrings, libellés d'interface et **noms de
  tests** en français. Les commentaires expliquent le *pourquoi*, pas le *quoi* — c'est le
  style de tout le dépôt.
- **Politique appliance fail-safe** : un pack invalide dégrade l'apparence, **jamais** la
  disponibilité. Aucune exception ne remonte de `Branding.__init__`.
- **Non-régression absolue** : sans `BRAND_DIR`, le rendu doit être identique à l'octet près
  à celui d'aujourd'hui. Chaque tâche touchant un template porte un test qui le vérifie.
- **ruff** : jeu de règles élargi déclaré dans `pyproject.toml` (`B`, `SIM`, `BLE`, `UP`,
  `I`, `RUF`…). Pas d'`except Exception` nu. Lancer `ruff check .` avant chaque commit.
- **Couverture** : `fail_under = 88` dans `[tool.coverage.report]`. Le code ajouté doit être
  couvert, y compris ses branches d'erreur.
- **Pas de `pytest.ini`** : la configuration pytest vit dans `pyproject.toml` et nulle part
  ailleurs (elle reprendrait la priorité).
- **Extensions de logo autorisées** : `.svg` et `.png`, exactement. Pas de `.jpg`.
- **Texte du co-branding**, au mot près : `Propulsé par ComRoster` quand un pack est actif ;
  `COMROSTER par Nathan Hurstel` (pied `/display`) et `ComRoster` (pied `/print`) sinon.

---

## Structure des fichiers

| Fichier | Rôle | Tâche |
|---|---|---|
| `comroster/services/branding.py` | **Créé.** Charge et valide le pack ; expose la marque en lecture seule. | 1 |
| `comroster/config.py` | **Modifié.** Ajoute `BRAND_DIR`. | 1 |
| `tests/test_branding.py` | **Créé.** Chargement, replis, rendu, routes. | 1, 2, 3, 4 |
| `comroster/__init__.py` | **Modifié.** Instancie le service, injecte `brand` dans les templates. | 2 |
| `comroster/display.py` | **Modifié.** Deux routes servant les logos. | 2 |
| `templates/display.html` | **Modifié.** Logo conditionnel + pied co-brandé. | 3 |
| `static/css/display.css` | **Modifié.** Ratio libre + neutralisation du filtre. | 3 |
| `templates/print.html` | **Modifié.** Logo dans l'en-tête + pied co-brandé. | 4 |
| `static/css/print.css` | **Modifié.** Règle `.sheet-logo`. | 4 |
| `deploy/set-branding.sh` | **Créé.** Pose/retire un pack, avec garde-fou overlay. | 5 |
| `deploy/raspberry-pi.md` | **Modifié.** Section « Marque client ». | 5 |
| `tests/test_deploy_scripts.py` | **Créé.** Syntaxe et droits du script. | 5 |

**Découpage :** les tâches 3 et 4 sont séparées parce qu'un relecteur peut légitimement
accepter le rendu écran et rejeter le rendu papier — ce sont deux surfaces, deux feuilles de
style autonomes, deux jugements. Les tâches 1 et 2 sont séparées parce que la première est
du domaine pur (testable sans HTTP) et la seconde du câblage web.

---

## Task 1 : le service `Branding` et sa configuration

**Files:**
- Create: `comroster/services/branding.py`
- Modify: `comroster/config.py` (après la ligne `self.DATA_DIR = …`)
- Test: `tests/test_branding.py`

**Interfaces:**
- Consomme : rien (première tâche).
- Produit :
  - `Branding(brand_dir: str)` — constructeur, ne lève jamais.
  - Attributs : `active: bool`, `name: str`, `logo_path: str | None`,
    `print_logo_path: str | None`, `mono: bool`, `version: int`.
  - `Config.BRAND_DIR: str` — chemin du pack, `""` si absent.

- [ ] **Step 1 : écrire les tests du chargement et des replis**

Créer `tests/test_branding.py` :

```python
"""Marque client : le logo d'un client à la place de celui de ComRoster.

La marque est une propriété du BOÎTIER, pas une donnée d'application : elle vit dans un
dossier système que l'application lit et n'écrit jamais. Le verrou tient à l'absence de
tout chemin d'écriture — pas à un contrôle d'accès qu'on pourrait contourner.

D'où le cœur de ce fichier : les cas de REPLI. Un pack mal posé doit dégrader l'apparence
et rien d'autre. Un boîtier qui refuserait de démarrer une heure avant un show à cause
d'un logo mal nommé serait un défaut bien pire que l'absence de logo.
"""
import json

import pytest

from comroster.services.branding import Branding

SVG = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"></svg>'


def _pack(tmp_path, manifeste, fichiers=("logo.svg",)):
    """Fabrique un pack de marque sur disque et renvoie son chemin."""
    d = tmp_path / "branding"
    d.mkdir(exist_ok=True)
    for nom in fichiers:
        (d / nom).write_bytes(SVG)
    (d / "brand.json").write_text(json.dumps(manifeste), encoding="utf-8")
    return str(d)


def test_sans_dossier_la_marque_est_inactive():
    b = Branding("")
    assert b.active is False
    assert b.name == ""


def test_un_pack_valide_est_charge(tmp_path):
    b = Branding(_pack(tmp_path, {"name": "Acme Live", "logo": "logo.svg"}))
    assert b.active is True
    assert b.name == "Acme Live"
    assert b.logo_path.endswith("logo.svg")
    assert b.mono is False
    assert b.version > 0


def test_sans_logo_print_la_variante_papier_reprend_le_logo_ecran(tmp_path):
    b = Branding(_pack(tmp_path, {"name": "Acme Live", "logo": "logo.svg"}))
    assert b.print_logo_path == b.logo_path


def test_le_logo_print_est_pris_en_compte_quand_il_existe(tmp_path):
    chemin = _pack(
        tmp_path,
        {"name": "Acme Live", "logo": "logo.svg", "logo_print": "noir.svg"},
        fichiers=("logo.svg", "noir.svg"),
    )
    b = Branding(chemin)
    assert b.print_logo_path.endswith("noir.svg")
    assert b.logo_path.endswith("logo.svg")


def test_le_drapeau_mono_est_lu(tmp_path):
    b = Branding(_pack(tmp_path, {"name": "Acme", "logo": "logo.svg", "mono": True}))
    assert b.mono is True


@pytest.mark.parametrize(
    "manifeste,fichiers",
    [
        ({"logo": "logo.svg"}, ("logo.svg",)),                       # name absent
        ({"name": "  ", "logo": "logo.svg"}, ("logo.svg",)),         # name vide
        ({"name": "Acme"}, ("logo.svg",)),                           # logo absent
        ({"name": "Acme", "logo": "absent.svg"}, ("logo.svg",)),     # fichier introuvable
        ({"name": "Acme", "logo": "logo.jpg"}, ("logo.jpg",)),       # extension interdite
        ({"name": "Acme", "logo": "../logo.svg"}, ("logo.svg",)),    # échappement de dossier
        ({"name": "Acme", "logo": "sous/logo.svg"}, ("logo.svg",)),  # chemin, pas un nom
    ],
)
def test_un_pack_invalide_retombe_sur_comroster(tmp_path, manifeste, fichiers):
    """Chaque faute doit produire le MÊME résultat : marque inactive, aucune exception."""
    b = Branding(_pack(tmp_path, manifeste, fichiers))
    assert b.active is False


def test_un_manifeste_illisible_retombe_sur_comroster(tmp_path):
    d = tmp_path / "branding"
    d.mkdir()
    (d / "brand.json").write_text("{ceci n'est pas du json", encoding="utf-8")
    assert Branding(str(d)).active is False


def test_un_manifeste_non_objet_retombe_sur_comroster(tmp_path):
    d = tmp_path / "branding"
    d.mkdir()
    (d / "brand.json").write_text('["Acme"]', encoding="utf-8")
    assert Branding(str(d)).active is False


def test_un_dossier_inexistant_retombe_sur_comroster(tmp_path):
    assert Branding(str(tmp_path / "nulle-part")).active is False
```

- [ ] **Step 2 : lancer les tests pour les voir échouer**

Run : `.venv/bin/pytest tests/test_branding.py -v`
Expected : FAIL — `ModuleNotFoundError: No module named 'comroster.services.branding'`

- [ ] **Step 3 : écrire le service**

Créer `comroster/services/branding.py` :

```python
"""Marque du boîtier : le logo d'un client à la place de celui de ComRoster.

La marque n'est PAS une donnée d'application — ni brouillon, ni état publié, ni contenu de
DATA_DIR. C'est une propriété du boîtier, posée à la fabrication dans un dossier système
que l'application lit et n'écrit jamais.

C'est là tout le verrouillage demandé : le client peut disposer de la totalité de
l'administration, il n'y a rien à atteindre. Ce n'est pas un mot de passe qu'on pourrait
contourner, c'est l'ABSENCE de mutateur. D'où une classe sans aucune méthode d'écriture.

Politique appliance (fail-safe), la même que le carnet de bord : toute faute — dossier
absent, manifeste illisible, logo introuvable, extension interdite — retombe intégralement
sur ComRoster avec un avertissement journalisé. Jamais une exception : un logo mal nommé ne
doit pas empêcher un boîtier de démarrer une heure avant un show.

Chargement UNIQUE au démarrage : la marque ne change pas pendant qu'un show tourne, et
poser un pack implique de toute façon un redémarrage du service (deploy/set-branding.sh).
"""
import json
import logging
import os

log = logging.getLogger(__name__)

#: Formats acceptés pour un logo. Le JPEG est écarté volontairement : sans canal alpha, un
#: logo rend mal sur le fond sombre du tableau. La conversion appartient à la préparation
#: du pack, pas au boîtier.
EXTENSIONS_ADMISES = (".svg", ".png")

MANIFESTE = "brand.json"


class Branding:
    def __init__(self, brand_dir=""):
        self._reset()
        if not brand_dir:
            return
        try:
            self._charger(brand_dir)
        except (OSError, ValueError) as exc:
            log.warning("Pack de marque ignoré (%s) — repli sur ComRoster", exc)
            self._reset()

    def _reset(self):
        self.active = False
        self.name = ""
        self.logo_path = None
        self.print_logo_path = None
        self.mono = False
        self.version = 0

    def _charger(self, brand_dir):
        with open(os.path.join(brand_dir, MANIFESTE), encoding="utf-8") as f:
            manifeste = json.load(f)
        if not isinstance(manifeste, dict):
            raise ValueError("racine du manifeste non-objet")

        nom = (manifeste.get("name") or "").strip()
        if not nom:
            raise ValueError("champ « name » absent ou vide")

        logo = self._resoudre(brand_dir, manifeste.get("logo"))
        logo_print = logo
        if manifeste.get("logo_print"):
            logo_print = self._resoudre(brand_dir, manifeste["logo_print"])

        self.name = nom
        self.logo_path = logo
        self.print_logo_path = logo_print
        self.mono = bool(manifeste.get("mono"))
        # Une seule version pour les deux logos : le pack est posé d'un bloc, la variante
        # papier ne peut pas changer sans l'écran.
        self.version = max(int(os.stat(p).st_mtime) for p in {logo, logo_print})
        self.active = True

    @staticmethod
    def _resoudre(brand_dir, nom_fichier):
        """Transforme un nom déclaré dans le manifeste en chemin absolu vérifié.

        La source est de confiance (le pack est posé en root, à la fabrication), mais on ne
        concatène jamais un chemin non validé : exiger un simple nom de fichier coûte trois
        lignes et ferme définitivement la question de la traversée de répertoire.
        """
        if not nom_fichier or not isinstance(nom_fichier, str):
            raise ValueError("nom de fichier de logo absent")
        if nom_fichier != os.path.basename(nom_fichier):
            raise ValueError(f"« {nom_fichier} » n'est pas un simple nom de fichier")
        extension = os.path.splitext(nom_fichier)[1].lower()
        if extension not in EXTENSIONS_ADMISES:
            raise ValueError(f"extension « {extension} » non autorisée")
        chemin = os.path.join(brand_dir, nom_fichier)
        if not os.path.isfile(chemin):
            raise ValueError(f"fichier « {nom_fichier} » introuvable")
        return chemin
```

- [ ] **Step 4 : ajouter `BRAND_DIR` à la configuration**

Dans `comroster/config.py`, juste après la ligne `self.DATA_DIR = …` :

```python
        # Marque du boîtier : dossier du pack client (brand.json + logos), posé à la
        # fabrication HORS de DATA_DIR — donc hors de portée de l'administration et des
        # sauvegardes. Vide = ComRoster. Voir deploy/set-branding.sh.
        self.BRAND_DIR = os.environ.get("COMROSTER_BRAND_DIR", "")
```

- [ ] **Step 5 : lancer les tests, les voir passer**

Run : `.venv/bin/pytest tests/test_branding.py -v`
Expected : PASS (15 tests — dont les 7 variantes de pack invalide)

- [ ] **Step 6 : vérifier le linter**

Run : `.venv/bin/ruff check comroster/ tests/`
Expected : `All checks passed!`

- [ ] **Step 7 : commit**

```bash
git add comroster/services/branding.py comroster/config.py tests/test_branding.py
git commit -m "feat(marque): service de lecture du pack de marque du boîtier

Charge /etc/comroster/branding une fois au démarrage et expose la marque en
lecture seule — aucune méthode d'écriture, c'est là le verrou. Toute faute de
pack retombe sur ComRoster avec un avertissement, jamais une exception."
```

---

## Task 2 : câblage web — service partagé, injection Jinja, routes

**Files:**
- Modify: `comroster/__init__.py` (imports + bloc des services + context processor)
- Modify: `comroster/display.py` (imports + deux routes)
- Test: `tests/test_branding.py` (ajouts en fin de fichier)

**Interfaces:**
- Consomme : `Branding` et `Config.BRAND_DIR` de la Task 1.
- Produit :
  - `app.extensions["branding"]` — l'instance partagée.
  - `brand` — variable injectée dans **tous** les templates.
  - endpoints `display.brand_logo` (`GET /branding/logo`) et
    `display.brand_logo_print` (`GET /branding/logo-print`).

- [ ] **Step 1 : écrire les tests des routes**

Ajouter à la fin de `tests/test_branding.py` :

```python
# ---------------------------------------------------------------------------
# Routes de service des logos
# ---------------------------------------------------------------------------

from comroster import create_app  # noqa: E402


def _client_avec_pack(tmp_path, manifeste=None, fichiers=("logo.svg",)):
    chemin = _pack(tmp_path, manifeste or {"name": "Acme Live", "logo": "logo.svg"}, fichiers)
    app = create_app({
        "TESTING": True,
        "DATA_DIR": str(tmp_path),
        "SECRET_KEY": "test-secret",
        "BRAND_DIR": chemin,
    })
    return app.test_client()


def test_sans_pack_la_route_du_logo_repond_404(client):
    assert client.get("/branding/logo").status_code == 404
    assert client.get("/branding/logo-print").status_code == 404


def test_avec_pack_la_route_sert_le_logo(tmp_path):
    r = _client_avec_pack(tmp_path).get("/branding/logo")
    assert r.status_code == 200
    assert r.mimetype == "image/svg+xml"


def test_le_logo_papier_est_servi_sur_sa_propre_route(tmp_path):
    r = _client_avec_pack(tmp_path).get("/branding/logo-print")
    assert r.status_code == 200


def test_le_logo_est_mis_en_cache(tmp_path):
    """Un écran de régie tourne des jours d'affilée : retélécharger le logo à chaque
    rechargement de page serait du gaspillage. L'invalidation passe par `?v=`."""
    r = _client_avec_pack(tmp_path).get("/branding/logo")
    assert "max-age" in r.headers["Cache-Control"]


def test_la_marque_est_disponible_dans_les_templates(tmp_path):
    """`brand` est injecté globalement : les templates n'ont pas à se le faire passer."""
    chemin = _pack(tmp_path, {"name": "Acme Live", "logo": "logo.svg"})
    app = create_app({
        "TESTING": True,
        "DATA_DIR": str(tmp_path),
        "SECRET_KEY": "test-secret",
        "BRAND_DIR": chemin,
    })
    with app.test_request_context():
        from flask import render_template_string
        assert render_template_string("{{ brand.name }}") == "Acme Live"
```

- [ ] **Step 2 : lancer les tests pour les voir échouer**

Run : `.venv/bin/pytest tests/test_branding.py -v -k "route or cache or templates or logo_papier"`
Expected : FAIL — 404 sur toutes les routes, et `brand` indéfini dans le template
(rendu vide au lieu de « Acme Live »).

- [ ] **Step 3 : instancier le service et injecter `brand`**

Dans `comroster/__init__.py`, ajouter l'import parmi les autres services (ordre alphabétique,
ruff `I` s'en charge sinon) :

```python
from .services.branding import Branding
```

Puis, dans le bloc des services partagés, après la ligne `app.extensions["storage"] = …` :

```python
    # Marque du boîtier : lue une fois, jamais écrite. Ne dépend d'aucun autre service.
    app.extensions["branding"] = Branding(app.config["BRAND_DIR"])
```

Et, à côté des autres décorateurs d'application (près de `_bust_static_cache`) :

```python
    @app.context_processor
    def _injecter_marque():
        # Injection globale plutôt qu'un argument à chaque `render_template` : quatre
        # appels aujourd'hui, et tous ceux à venir.
        return {"brand": app.extensions["branding"]}
```

- [ ] **Step 4 : ajouter les deux routes**

Dans `comroster/display.py`, compléter l'import Flask existant avec `abort` et `send_file` :

```python
from flask import (
    Blueprint,
    Response,
    abort,
    current_app,
    render_template,
    request,
    send_file,
    stream_with_context,
)
```

Puis, juste après la route `qr_svg` :

```python
#: Une semaine. Le pack ne bouge qu'au redémarrage du service ; l'invalidation passe par
#: le `?v=<version>` que les templates ajoutent, comme le cache-buster des URLs static.
BRAND_CACHE_SECONDS = 604800


def _servir_logo(attribut):
    brand = current_app.extensions["branding"]
    if not brand.active:
        abort(404)
    reponse = send_file(getattr(brand, attribut), conditional=True)
    reponse.headers["Cache-Control"] = f"public, max-age={BRAND_CACHE_SECONDS}"
    return reponse


@bp.get("/branding/logo")
def brand_logo():
    """Logo de marque affiché en régie. 404 s'il n'y a pas de pack : les templates ne
    référencent alors pas cette route, mais elle reste honnête."""
    return _servir_logo("logo_path")


@bp.get("/branding/logo-print")
def brand_logo_print():
    """Variante encre noire, pour la feuille imprimable."""
    return _servir_logo("print_logo_path")
```

- [ ] **Step 5 : lancer toute la suite**

Run : `.venv/bin/pytest -q`
Expected : PASS — aucun test existant ne régresse (sans `BRAND_DIR`, tout est inchangé).

- [ ] **Step 6 : vérifier le linter**

Run : `.venv/bin/ruff check comroster/ tests/`
Expected : `All checks passed!`

- [ ] **Step 7 : commit**

```bash
git add comroster/__init__.py comroster/display.py tests/test_branding.py
git commit -m "feat(marque): routes de service des logos et injection dans les templates

/branding/logo et /branding/logo-print servent le pack avec ETag et cache long ;
404 sans pack. \`brand\` est injecté globalement par context_processor."
```

---

## Task 3 : rendu du `/display`

**Files:**
- Modify: `templates/display.html:33-34` (logo) et `:39` (pied)
- Modify: `static/css/display.css:111-116`
- Test: `tests/test_branding.py` (ajouts en fin de fichier)

**Interfaces:**
- Consomme : `brand` (Task 2), endpoint `display.brand_logo` (Task 2).
- Produit : la classe CSS `.brand-mark-color`, posée quand `brand.mono` est faux.

- [ ] **Step 1 : écrire les tests de rendu**

Ajouter à la fin de `tests/test_branding.py` :

```python
# ---------------------------------------------------------------------------
# Rendu du tableau de régie
# ---------------------------------------------------------------------------


def test_sans_pack_le_display_garde_le_glyphe_comroster(client):
    """Non-régression : le comportement par défaut ne bouge pas d'un octet."""
    html = client.get("/display").get_data(as_text=True)
    assert "comroster-glyph.svg" in html
    assert "COMROSTER par Nathan Hurstel" in html
    assert "/branding/logo" not in html


def test_avec_pack_le_display_affiche_le_logo_client(tmp_path):
    html = _client_avec_pack(tmp_path).get("/display").get_data(as_text=True)
    assert "/branding/logo" in html
    assert 'alt="Acme Live"' in html
    assert "comroster-glyph.svg" not in html


def test_avec_pack_le_credit_comroster_devient_discret(tmp_path):
    """Co-branding : la signature reste, elle cède la place d'honneur."""
    html = _client_avec_pack(tmp_path).get("/display").get_data(as_text=True)
    assert "Propulsé par ComRoster" in html
    assert "COMROSTER par Nathan Hurstel" not in html


def test_un_logo_couleur_est_protege_de_l_inversion_du_theme_jour(tmp_path):
    """Le thème jour inverse le glyphe monochrome de ComRoster ; appliqué à un logo
    couleur, ce filtre le rendrait en négatif."""
    html = _client_avec_pack(tmp_path).get("/display").get_data(as_text=True)
    assert "brand-mark-color" in html


def test_un_logo_monochrome_reste_inverse_en_theme_jour(tmp_path):
    html = _client_avec_pack(
        tmp_path, {"name": "Acme", "logo": "logo.svg", "mono": True}
    ).get("/display").get_data(as_text=True)
    assert "brand-mark-color" not in html
```

- [ ] **Step 2 : lancer les tests pour les voir échouer**

Run : `.venv/bin/pytest tests/test_branding.py -v -k "display or credit or logo_couleur or monochrome"`
Expected : FAIL — le template sert toujours `comroster-glyph.svg` et le pied historique.

- [ ] **Step 3 : rendre le logo conditionnel**

Dans `templates/display.html`, remplacer les lignes 33-34 :

```html
      {# Logo ComRoster en haut à droite (glyphe seul, sans le mot). #}
      <img class="brand-mark" src="{{ url_for('static', filename='img/comroster-glyph.svg') }}" alt="ComRoster" width="28" height="28">
```

par :

```html
      {# Logo en haut à droite : celui du client si un pack de marque est posé sur le
         boîtier (deploy/set-branding.sh), sinon le glyphe ComRoster. #}
      {% if brand.active %}
      <img class="brand-mark{% if not brand.mono %} brand-mark-color{% endif %}"
           src="{{ url_for('display.brand_logo', v=brand.version) }}" alt="{{ brand.name }}">
      {% else %}
      <img class="brand-mark" src="{{ url_for('static', filename='img/comroster-glyph.svg') }}" alt="ComRoster" width="28" height="28">
      {% endif %}
```

- [ ] **Step 4 : co-brander le pied**

Toujours dans `templates/display.html`, remplacer la ligne 39 :

```html
    <span class="created-by">COMROSTER par Nathan Hurstel</span>
```

par :

```html
    <span class="created-by">{% if brand.active %}Propulsé par ComRoster{% else %}COMROSTER par Nathan Hurstel{% endif %}</span>
```

- [ ] **Step 5 : adapter le CSS**

Dans `static/css/display.css`, remplacer le bloc des lignes 111-116 :

```css
/* Logo ComRoster (glyphe seul) en haut à droite, séparé par un filet des indicateurs. */
.display-page .brand-mark {
  width: 1.85rem; height: 1.85rem; flex: 0 0 auto; opacity: 0.9;
  padding-left: 1.2rem; border-left: 1px solid var(--d-line-strong); box-sizing: content-box;
}
body.display-page[data-theme="day"] .brand-mark { filter: invert(1); }
```

par :

```css
/* Logo en haut à droite, séparé par un filet des indicateurs. Hauteur FIXE, largeur
   LIBRE bornée : le glyphe ComRoster est carré, mais un logo client est presque toujours
   un wordmark horizontal, et l'en-tête est déjà dense (titre, stats, horloge, badge). */
.display-page .brand-mark {
  height: 1.85rem; width: auto; max-width: 9rem; object-fit: contain;
  flex: 0 0 auto; opacity: 0.9;
  padding-left: 1.2rem; border-left: 1px solid var(--d-line-strong); box-sizing: content-box;
}
body.display-page[data-theme="day"] .brand-mark { filter: invert(1); }
/* Un logo client EN COULEUR ne doit jamais passer dans l'inversion ci-dessus : elle le
   rendrait en négatif (le bleu vire à l'orange). Spécificité égale, posée après. */
body.display-page[data-theme="day"] .brand-mark-color { filter: none; }
```

- [ ] **Step 6 : lancer les tests, y compris le garde des jetons CSS**

Run : `.venv/bin/pytest tests/test_branding.py tests/test_css_tokens.py tests/test_ui.py -q`
Expected : PASS — aucune variable CSS nouvelle n'a été introduite.

- [ ] **Step 7 : vérifier à l'œil sur les deux thèmes**

Run : `./run-dev.sh` puis ouvrir `/display`.
Expected : sans pack, l'en-tête est identique à avant, en thème nuit comme en thème jour.

- [ ] **Step 8 : commit**

```bash
git add templates/display.html static/css/display.css tests/test_branding.py
git commit -m "feat(marque): logo client et crédit discret sur /display

Le logo passe à hauteur fixe / largeur libre : un wordmark horizontal tient dans
l'en-tête, un glyphe carré rend comme avant. Les logos couleur sont exemptés de
l'inversion du thème jour, qui les rendrait en négatif."
```

---

## Task 4 : rendu de la feuille imprimable

**Files:**
- Modify: `templates/print.html:30-32` (en-tête) et `:91-94` (pied)
- Modify: `static/css/print.css` (après le bloc `.sheet-head`)
- Test: `tests/test_branding.py` (ajouts en fin de fichier)

**Interfaces:**
- Consomme : `brand` (Task 2), endpoint `display.brand_logo_print` (Task 2).
- Produit : la classe CSS `.sheet-logo`.

- [ ] **Step 1 : écrire les tests**

Ajouter à la fin de `tests/test_branding.py` :

```python
# ---------------------------------------------------------------------------
# Rendu de la feuille imprimable
# ---------------------------------------------------------------------------


def _client_admin_avec_pack(tmp_path):
    c = _client_avec_pack(tmp_path)
    c.post("/admin/setup", data={"password": "motdepasse8"})
    return c


def test_sans_pack_la_feuille_garde_le_pied_comroster(auth_client):
    """Non-régression sur le document papier."""
    html = auth_client.get("/admin/print").get_data(as_text=True)
    assert "ComRoster" in html
    assert "/branding/logo-print" not in html


def test_avec_pack_la_feuille_porte_le_logo_client(tmp_path):
    html = _client_admin_avec_pack(tmp_path).get("/admin/print").get_data(as_text=True)
    assert "/branding/logo-print" in html
    assert "Acme Live" in html


def test_avec_pack_le_pied_de_la_feuille_est_co_brande(tmp_path):
    html = _client_admin_avec_pack(tmp_path).get("/admin/print").get_data(as_text=True)
    assert "Propulsé par ComRoster" in html
```

- [ ] **Step 2 : lancer les tests pour les voir échouer**

Run : `.venv/bin/pytest tests/test_branding.py -v -k "feuille"`
Expected : FAIL — aucune référence à `/branding/logo-print` dans la feuille.

- [ ] **Step 3 : poser le logo dans l'en-tête de la feuille**

Dans `templates/print.html`, remplacer les lignes 30-32 :

```html
  <header class="sheet-head">
    <div class="sheet-title">
      <h1>{{ state.production_name or state.title or 'Affectation Intercom' }}</h1>
```

par :

```html
  <header class="sheet-head">
    {# Logo du client, s'il y en a un : la place naturelle d'un logo sur un document.
       Variante encre noire du pack, à défaut le logo d'écran. #}
    {% if brand.active %}
    <img class="sheet-logo" src="{{ url_for('display.brand_logo_print', v=brand.version) }}"
         alt="{{ brand.name }}">
    {% endif %}
    <div class="sheet-title">
      <h1>{{ state.production_name or state.title or 'Affectation Intercom' }}</h1>
```

- [ ] **Step 4 : co-brander le pied de la feuille**

Remplacer les lignes 91-94 :

```html
  <footer class="sheet-foot">
    ComRoster · {{ state.title or 'Affectation Intercom' }} ·
    {% if state.updated_at %}dernière modification {{ state.updated_at }}{% endif %}
  </footer>
```

par :

```html
  <footer class="sheet-foot">
    {% if brand.active %}{{ brand.name }}{% else %}ComRoster{% endif %} ·
    {{ state.title or 'Affectation Intercom' }}
    {%- if state.updated_at %} · dernière modification {{ state.updated_at }}{% endif %}
    {%- if brand.active %} · Propulsé par ComRoster{% endif %}
  </footer>
```

Le séparateur `·` passe À L'INTÉRIEUR de chaque condition : la version d'origine laissait un
séparateur orphelin quand `updated_at` était vide.

- [ ] **Step 5 : ajouter la règle CSS**

Dans `static/css/print.css`, juste après le bloc `.sheet-head { … }` :

```css
/* Logo du client. `print.css` est AUTONOME (elle ne charge pas main.css) : dimensions en
   millimètres, comme le reste de la feuille. Hauteur fixe, largeur libre bornée — un
   wordmark horizontal comme un logo carré tiennent tous deux dans l'en-tête. */
.sheet-logo { height: 13mm; width: auto; max-width: 55mm; object-fit: contain; }
```

- [ ] **Step 6 : lancer les tests**

Run : `.venv/bin/pytest tests/test_branding.py tests/test_print.py tests/test_css_tokens.py -q`
Expected : PASS

- [ ] **Step 7 : vérifier l'aperçu d'impression**

Run : `./run-dev.sh`, se connecter, ouvrir `/admin/print`, lancer l'aperçu d'impression.
Expected : sans pack, la feuille est identique à avant ; l'en-tête ne déborde pas d'une page.

- [ ] **Step 8 : commit**

```bash
git add templates/print.html static/css/print.css tests/test_branding.py
git commit -m "feat(marque): logo client et pied co-brandé sur la feuille imprimable

Le logo prend la place naturelle d'un logo sur un document, à gauche du titre.
Le pied porte le nom du client et garde la signature ComRoster en discret ; au
passage, plus de séparateur orphelin quand la date de modification est absente."
```

---

## Task 5 : outil de fabrication et documentation

**Files:**
- Create: `deploy/set-branding.sh`
- Create: `tests/test_deploy_scripts.py`
- Modify: `deploy/raspberry-pi.md`

**Interfaces:**
- Consomme : `COMROSTER_BRAND_DIR` (Task 1), la structure du pack (Task 1).
- Produit : rien pour le code — c'est l'outil qui pose ce que les tâches 1 à 4 consomment.

- [ ] **Step 1 : écrire le test du script**

Créer `tests/test_deploy_scripts.py` :

```python
"""Garde : les scripts de déploiement doivent au moins être syntaxiquement valides.

Un script de terrain n'est lancé qu'une fois, en root, sur un boîtier en préparation —
c'est-à-dire au pire endroit pour découvrir une accolade manquante. `bash -n` analyse sans
exécuter : c'est peu, mais c'est ce qui attrape la faute la plus coûteuse.
"""
import os
import subprocess

import pytest

DEPLOY = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "deploy"
)
SCRIPTS = sorted(f for f in os.listdir(DEPLOY) if f.endswith(".sh"))


@pytest.mark.parametrize("script", SCRIPTS)
def test_la_syntaxe_du_script_est_valide(script):
    r = subprocess.run(
        ["bash", "-n", os.path.join(DEPLOY, script)],
        capture_output=True, text=True, check=False,
    )
    assert r.returncode == 0, r.stderr


def test_le_script_de_marque_existe_et_est_executable():
    """Il est le seul chemin prévu pour poser une marque : s'il disparaît ou perd son bit
    d'exécution, la fonctionnalité n'est plus livrable.

    Le contrôle vise CE script seul, volontairement : `deploy/apply-network.sh` n'a pas
    son bit d'exécution aujourd'hui, et le rendre exécutable n'a rien à voir avec la
    marque client. À traiter séparément si c'est un oubli.
    """
    assert "set-branding.sh" in SCRIPTS
    assert os.access(os.path.join(DEPLOY, "set-branding.sh"), os.X_OK)
```

- [ ] **Step 2 : lancer le test pour le voir échouer**

Run : `.venv/bin/pytest tests/test_deploy_scripts.py -v`
Expected : FAIL sur `test_le_script_de_marque_existe_et_est_executable` ; les contrôles
`bash -n` des scripts existants passent déjà.

- [ ] **Step 3 : écrire le script**

Créer `deploy/set-branding.sh` :

```bash
#!/usr/bin/env bash
#
# MARQUE CLIENT — pose ou retire le pack de marque du boîtier.
#
#     sudo deploy/set-branding.sh ~/packs/acme-live/   # pose la marque
#     sudo deploy/set-branding.sh --reset              # revient à ComRoster
#
# Un pack contient brand.json et ses logos :
#     brand.json  {"name": "Acme Live", "logo": "logo.svg",
#                  "logo_print": "logo-noir.svg", "mono": false}
#     logo.svg  logo-noir.svg          (.svg ou .png ; pas de .jpg)
#
# Le pack vit dans /etc/comroster/branding — HORS de DATA_DIR, donc hors de portée de
# l'administration et des sauvegardes. C'est là le verrou : l'application n'a aucun chemin
# d'écriture vers la marque, et `ProtectSystem=full` dans l'unité systemd rend /etc en
# lecture seule pour le service lui-même.
#
# ⚠️ À POSER AVANT d'activer l'overlay lecture seule (deploy/readonly-fs.sh) : sous
#    overlay, toute écriture dans /etc part en RAM et disparaît au redémarrage.
set -euo pipefail

DEST=/etc/comroster/branding
UNIT=/etc/systemd/system/comroster.service
ENV_LINE="Environment=COMROSTER_BRAND_DIR=$DEST"

[ "$(id -u)" -eq 0 ] || { echo "Lancer avec sudo : sudo deploy/set-branding.sh …"; exit 1; }
[ -f "$UNIT" ] || { echo "Unité systemd introuvable ($UNIT) — ComRoster est-il installé ?"; exit 1; }

# Garde-fou overlay, dans l'esprit de celui de readonly-fs.sh : mieux vaut refuser que
# poser une marque qui s'évaporerait au prochain redémarrage.
if [ "$(findmnt -no FSTYPE / 2>/dev/null || echo '')" = "overlay" ]; then
  cat <<'MSG'
⚠️  REFUS — la racine est montée en overlay (lecture seule).

    Toute écriture dans /etc part en RAM et serait PERDUE au redémarrage : la marque
    ne tiendrait pas. Ordre correct :

      sudo deploy/readonly-fs.sh off && sudo reboot
      sudo deploy/set-branding.sh <pack>
      sudo deploy/readonly-fs.sh on  && sudo reboot

    (Rien n'a été modifié.)
MSG
  exit 1
fi

# ---------- retrait ----------
if [ "${1:-}" = "--reset" ]; then
  rm -rf "$DEST"
  sed -i "\|^${ENV_LINE}\$|d" "$UNIT"
  systemctl daemon-reload
  systemctl restart comroster
  echo "✅ Marque retirée — le boîtier réaffiche ComRoster."
  exit 0
fi

SRC="${1:-}"
if [ -z "$SRC" ] || [ ! -d "$SRC" ]; then
  echo "Usage : sudo deploy/set-branding.sh <dossier-du-pack> | --reset"
  exit 1
fi

# ---------- validation AVANT de toucher au système ----------
# Un pack invalide est refusé ici, bruyamment, plutôt qu'ignoré en silence au prochain
# démarrage (l'application, elle, retombe sur ComRoster sans rien casser — mais on ne veut
# pas le découvrir le jour du show).
python3 - "$SRC" <<'PY'
import json, os, sys

src = sys.argv[1]

def refus(motif):
    print(f"⚠️  REFUS — pack invalide : {motif}")
    print("    (Rien n'a été modifié.)")
    sys.exit(1)

try:
    with open(os.path.join(src, "brand.json"), encoding="utf-8") as f:
        manifeste = json.load(f)
except FileNotFoundError:
    refus("brand.json absent du dossier")
except ValueError as exc:
    refus(f"brand.json illisible ({exc})")

if not isinstance(manifeste, dict):
    refus("brand.json : la racine doit être un objet")
if not (manifeste.get("name") or "").strip():
    refus("champ « name » absent ou vide")
if not manifeste.get("logo"):
    refus("champ « logo » absent")

for cle in ("logo", "logo_print"):
    nom = manifeste.get(cle)
    if not nom:
        continue
    if nom != os.path.basename(nom):
        refus(f"« {nom} » doit être un simple nom de fichier, pas un chemin")
    if os.path.splitext(nom)[1].lower() not in (".svg", ".png"):
        refus(f"« {nom} » : seuls .svg et .png sont acceptés")
    if not os.path.isfile(os.path.join(src, nom)):
        refus(f"« {nom} » introuvable dans le pack")

print(f"Pack valide : {manifeste['name']}")
PY

# ---------- pose ----------
install -d -o root -g root -m 0755 "$DEST"
rm -f "$DEST"/*
find "$SRC" -maxdepth 1 -type f \
     \( -name 'brand.json' -o -name '*.svg' -o -name '*.png' \) \
     -exec install -o root -g root -m 0644 {} "$DEST"/ \;

grep -qxF "$ENV_LINE" "$UNIT" || sed -i "\|^Environment=DATA_DIR=|a ${ENV_LINE}" "$UNIT"

systemctl daemon-reload
systemctl restart comroster

echo "✅ Marque posée dans $DEST."
echo "   Vérifie /display, puis /admin/print."
```

- [ ] **Step 4 : rendre le script exécutable**

```bash
chmod +x deploy/set-branding.sh
```

- [ ] **Step 5 : lancer les tests**

Run : `.venv/bin/pytest tests/test_deploy_scripts.py -v`
Expected : PASS — tous les scripts de `deploy/` passent `bash -n`, et `set-branding.sh` est
bien exécutable.

- [ ] **Step 6 : documenter dans `deploy/raspberry-pi.md`**

Ajouter une section « Marque client », après la section d'installation :

````markdown
## Marque client

Le logo d'un client peut remplacer celui de ComRoster sur `/display` et sur la feuille
imprimable. C'est une propriété du **boîtier**, pas un réglage : elle se pose à la
fabrication et l'administration n'y a aucun accès — il n'existe aucun chemin d'écriture
depuis l'application vers la marque.

### Composer un pack

```
acme-live/
├── brand.json
├── logo.svg          ← affiché en régie
└── logo-noir.svg     ← optionnel, pour le papier
```

```json
{
  "name": "Acme Live",
  "logo": "logo.svg",
  "logo_print": "logo-noir.svg",
  "mono": false
}
```

| Champ | Rôle |
|---|---|
| `name` | Nom affiché en `alt` et porté par la feuille imprimée. |
| `logo` | Logo d'écran. Simple nom de fichier, `.svg` ou `.png`. |
| `logo_print` | Variante encre noire. Absent → on réutilise `logo`. |
| `mono` | `true` pour un logo monochrome (il sera inversé en thème jour, comme le glyphe ComRoster) ; `false` pour un logo couleur (aucun filtre). |

Un logo horizontal est préférable : l'en-tête du tableau est dense, la largeur est bornée.
Le JPEG est refusé — sans transparence, un logo rend mal sur le fond sombre.

### Poser la marque

```bash
sudo deploy/set-branding.sh ~/packs/acme-live/
sudo deploy/set-branding.sh --reset      # revenir à ComRoster
```

Le script valide le pack avant de toucher au système, le copie dans
`/etc/comroster/branding`, complète l'unité systemd et redémarre le service.

⚠️ **À faire AVANT d'activer l'overlay lecture seule** (`deploy/readonly-fs.sh`). Sous
overlay, `/etc` est volatile : la marque serait perdue au redémarrage. Le script détecte ce
cas et refuse. Corollaire utile : sur un boîtier livré overlay actif, la marque devient
inaltérable — même un accès root ne la change pas durablement.

### Co-branding

Un pack actif ne fait pas disparaître ComRoster : le pied du tableau affiche « Propulsé par
ComRoster » et celui de la feuille imprimée porte le nom du client suivi de la même mention.
````

- [ ] **Step 7 : lancer toute la suite et le linter**

Run : `.venv/bin/pytest -q && .venv/bin/ruff check .`
Expected : PASS, `All checks passed!`

- [ ] **Step 8 : vérifier la couverture**

Run : `.venv/bin/pytest --cov -q`
Expected : couverture ≥ 88 % (`fail_under`).

- [ ] **Step 9 : commit**

```bash
git add deploy/set-branding.sh deploy/raspberry-pi.md tests/test_deploy_scripts.py
git commit -m "feat(marque): outil de pose du pack de marque et documentation terrain

set-branding.sh valide le pack avant de toucher au système et refuse si l'overlay
lecture seule est actif — la marque y serait perdue au redémarrage. En contrepartie,
un boîtier livré overlay actif a une marque inaltérable."
```

---

## Vérification finale

- [ ] `.venv/bin/pytest -q` — suite complète au vert
- [ ] `.venv/bin/pytest --cov -q` — couverture ≥ 88 %
- [ ] `.venv/bin/ruff check .` — aucun signalement
- [ ] Sans `BRAND_DIR` : `/display` et `/admin/print` sont **identiques** à avant, thème
      nuit et thème jour, sur les trois apparences (`basique`, `lineaire`, `grille`)
- [ ] Avec un pack de test : logo client visible en régie et sur la feuille, crédit
      ComRoster discret aux deux endroits
- [ ] Avec un pack volontairement cassé (logo renommé) : l'application démarre, `/display`
      affiche le glyphe ComRoster, un avertissement figure dans le journal technique
- [ ] Ajouter une entrée à `tasks/lessons.md` si une correction a été nécessaire en route

## Notes pour l'implémenteur

- **`ProtectSystem=full`** est déjà présent dans `deploy/comroster.service` : le processus
  ComRoster ne peut pas écrire dans `/etc`, même s'il le voulait. Le verrouillage est donc
  doublé au niveau du noyau, gratuitement. Ne pas retirer cette directive.
- **Deux valeurs sont des paris**, signalées telles quelles dans la spec : `max-width: 9rem`
  sur l'écran et `13mm / 55mm` sur le papier. Elles sont à caler avec un vrai logo client ;
  les modifier ne demande aucun changement de code.
- **Ne pas ajouter d'interface d'administration**, même « juste pour tester ». Toute la
  valeur de ce design tient à l'absence de chemin d'écriture.
