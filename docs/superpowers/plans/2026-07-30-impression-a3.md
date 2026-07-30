# Impression A3 — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Renommer « Feuille imprimable » en « Impression », doter la page d'une barre de six réglages mémorisés, et refondre le format papier en document A3 de production.

**Architecture :** Les réglages sont entièrement clients. Chacun est un `data-*` posé sur `<html>`, lu par des sélecteurs d'attribut écrits d'avance dans `print.css` ; seul le format papier passe par une règle `@page` insérée en CSSOM (mesuré : `insertRule` change bien le format à chaud). **Le défaut est l'ABSENCE d'attribut** — les règles de base de `print.css` valent A3 portrait / 3 colonnes / visa, et chaque `data-*` n'est qu'un dépassement. Une seule source pour le défaut, aucun scintillement au chargement, aucune valeur par défaut dupliquée entre Python et JS. La logique (allowlist, normalisation, persistance) vit dans un module **pur** testable sous Node ; `print.js` ne fait que le câblage DOM.

**Tech Stack :** Flask + Jinja2, JavaScript nu en modules ES, CSS Paged Media, pytest, vitest, Playwright.

## Global Constraints

Ces contraintes valent pour **toutes** les tâches.

- **CSP stricte.** Aucun `<style>` inline, aucun attribut `style="`, aucun `onclick`. Verrouillé par `tests/test_print.py:50-55` — les réglages doivent passer par `data-*` et CSSOM, jamais par un attribut de style (leçon 2026-07-07).
- **`print.css` est AUTONOME** : elle ne charge pas `main.css`. Tout `var(--x)` utilisé doit y être défini, sinon il retombe en silence sur son repli (leçon 2026-07-28 n°62). Verrouillé par `tests/test_css_tokens.py`.
- **Le pied ne doit pas régresser** : `.sheet-foot` contient « ComRoster », et « Propulsé par ComRoster » quand un pack de marque est actif. Trois tests de `tests/test_branding.py` l'imposent et **ne doivent pas être modifiés**.
- **vitest tourne en `environment: "node"`, sans jsdom.** Toute logique vérifiée en JS doit être pure et sans DOM ; c'est écrit dans `vitest.config.js`.
- **Français partout** : dates formatées côté serveur (jamais d'ISO à l'écran), pluriels accordés (leçon 2026-07-28 n°56).
- **Le marqueur `e2e` est exclu par défaut** : les tests bout-en-bout se lancent avec `pytest -m e2e`, sinon on lit « N deselected » et un code retour 0 qui ressemble à un succès (leçon 2026-07-30 n°73).
- **Ne jamais enchaîner un commit derrière `pytest | tail` avec `&&`** : le pipe masque le code retour. Lancer les tests, LIRE le résultat, puis committer (leçon 2026-07-26 n°43).
- **Commandes de contrôle** : `.venv/bin/pytest -q` · `.venv/bin/pytest -m e2e -q` · `npm test` · `.venv/bin/ruff check .`

---

### Task 1 : Renommer « Feuille imprimable » en « Impression »

`/admin/print` **reste l'URL** : `deploy/aide-memoire-terrain.md` la diffuse sur le terrain. Seul le libellé change. Vérifié au préalable : aucun test n'attend le libellé littéral, le renommage ne casse donc aucune suite.

**Files:**
- Modify: `templates/admin.html:95-96`
- Modify: `templates/print.html:6`
- Modify: `comroster/api.py:80`
- Modify: `comroster/display.py:106`
- Modify: `README.md:167,218`
- Modify: `deploy/aide-memoire-terrain.md:73`
- Modify: `tests/test_css_tokens.py:28`
- Test: `tests/test_print.py`

**Interfaces:**
- Consumes: rien.
- Produces: aucun symbole. Les tâches suivantes s'appuient sur le fait que le `<title>` de la feuille commence par « Impression ».

- [ ] **Step 1 : Écrire le test qui échoue**

Ajouter à la fin de `tests/test_print.py` :

```python
def test_l_admin_nomme_la_fonction_impression(auth_client):
    """« Feuille imprimable » décrivait l'objet produit ; « Impression » décrit ce que
    l'utilisateur vient faire. Nommer par la fonction, pas par l'artefact (leçon 37)."""
    html = auth_client.get("/admin").get_data(as_text=True)
    assert ">Impression</a>" in html
    assert "Feuille imprimable" not in html


def test_le_titre_de_la_page_porte_le_nouveau_nom(plateau):
    html = plateau.get("/admin/print").get_data(as_text=True)
    titre = html.split("<title>", 1)[1].split("</title>", 1)[0]
    assert titre.startswith("Impression")
    assert "Feuille d'affectation" not in titre
```

- [ ] **Step 2 : Lancer le test et vérifier qu'il échoue**

Run : `.venv/bin/pytest tests/test_print.py -k "impression or nouveau_nom" -v`
Attendu : 2 FAILED — l'admin contient encore « Feuille imprimable », le titre commence par « Feuille d'affectation ».

- [ ] **Step 3 : Renommer dans le template de l'admin**

Dans `templates/admin.html`, remplacer les lignes 95-96 :

```html
            <a class="nav-item" href="{{ url_for('api.admin_print') }}" target="_blank"
               rel="noopener" title="Ouvrir la feuille d'affectation à imprimer">Impression</a>
```

- [ ] **Step 4 : Renommer le titre de la feuille**

Dans `templates/print.html`, remplacer la ligne 6 :

```html
  <title>Impression · {{ state.production_name or state.title or 'ComRoster' }}</title>
```

- [ ] **Step 5 : Renommer dans les docstrings et la doc**

Dans `comroster/api.py`, première ligne de la docstring d'`admin_print` (l. 80) :

```python
    """Feuille d'affectation à imprimer (fonction « Impression » de l'admin).
```

Dans `comroster/display.py` l. 106 :

```python
    """Variante encre noire, pour la feuille à imprimer."""
```

Dans `tests/test_css_tokens.py` l. 28, la clé du dict `GROUPES` :

```python
    "impression": ["print.css"],
```

Dans `README.md` l. 218, remplacer `` `Feuille imprimable` (section « Données ») `` par `` `Impression` (section « Données ») ``. Dans `deploy/aide-memoire-terrain.md` l. 73, remplacer `**Feuille imprimable**` par `**Impression**`.

- [ ] **Step 6 : Lancer les tests et vérifier qu'ils passent**

Run : `.venv/bin/pytest tests/test_print.py tests/test_css_tokens.py tests/test_branding.py -q`
Attendu : tout PASSE (12 tests print + tokens + branding).

- [ ] **Step 7 : Vérifier qu'il ne reste aucune occurrence**

Run : `rtk proxy grep -rn "Feuille imprimable" --include="*.py" --include="*.html" --include="*.md" comroster/ templates/ tests/ README.md deploy/`
Attendu : **aucune ligne**. Le proxy court-circuite le filtrage du hook : un résultat négatif d'un grep filtré ne prouverait rien (leçon 2026-07-27 n°49). `docs/superpowers/` est volontairement exclu — les plans passés sont des archives datées, on ne réécrit pas l'histoire.

- [ ] **Step 8 : Commit**

```bash
git add templates/admin.html templates/print.html comroster/api.py comroster/display.py \
        README.md deploy/aide-memoire-terrain.md tests/test_css_tokens.py tests/test_print.py
git commit -m "refactor: « Feuille imprimable » devient « Impression »

Nommer par ce que l'utilisateur vient faire, pas par l'artefact produit
(leçon 37). L'URL /admin/print ne change pas : l'aide-mémoire terrain la
diffuse imprimée."
```

---

### Task 2 : Trois corrections factuelles côté serveur

La colonne dit « NOM » et affiche le RÔLE — le champ nom n'existe plus dans le modèle (`{id, role, beltpack, group_id}`), c'est la récidive de la leçon 32. Le pied affiche de l'ISO UTC brut dans une interface francophone. Et `break-inside: avoid` sur tous les groupes creuse le vide de ~100 px mesuré sur la capture : les groupes longs doivent redevenir coupables, ce que le CSS ne sait pas décider puisqu'il ne compte pas les lignes.

**Files:**
- Modify: `comroster/api.py` (fonction `admin_print`, + une constante et une fonction de module)
- Modify: `templates/print.html:41-46,64-71,85-92,97-102`
- Test: `tests/test_print.py`

**Interfaces:**
- Consumes: `_beltpack_sort_key` (existant).
- Produces: `comroster.api._date_fr(iso: str | None) -> str` — « 30/07/2026 à 15:13 » ou `""`. Constante `comroster.api.SEUIL_GROUPE_LONG: int = 12`. Le template reçoit deux variables de plus : `updated_fr: str` et `seuil_long: int`.

- [ ] **Step 1 : Écrire les tests qui échouent**

Ajouter à `tests/test_print.py` (l'import `pytest` y est déjà ; ajouter `import re` en tête) :

```python
from comroster.api import SEUIL_GROUPE_LONG, _date_fr


def test_la_colonne_annonce_le_role_et_non_le_nom(plateau):
    """Une personne, c'est {id, role, beltpack, group_id} : le champ nom n'existe plus.
    L'en-tête « NOM » affichait donc le rôle — récidive de la leçon 2026-07-23 n°32."""
    html = plateau.get("/admin/print").get_data(as_text=True)
    assert ">Rôle<" in html
    assert ">Nom<" not in html


def test_le_pied_date_en_francais_et_jamais_en_iso(plateau):
    """« 2026-07-30T13:13:59Z » dans une interface francophone (leçon n°56).

    On cherche le MOTIF ISO, pas la lettre « Z » : un nom de production ou de marque
    peut légitimement en contenir une, et le test se mettrait à mentir au premier
    client dont le nom porte un Z."""
    html = plateau.get("/admin/print").get_data(as_text=True)
    pied = html.split('class="sheet-foot"', 1)[1].split("</footer>", 1)[0]
    assert not re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", pied), "horodatage ISO au pied"
    assert re.search(r"\d{2}/\d{2}/\d{4} à \d{2}:\d{2}", pied), "date française attendue"


def test_date_fr_convertit_l_horodatage_du_modele():
    assert _date_fr("2026-07-30T13:13:59Z").startswith("30/07/2026 à ")


@pytest.mark.parametrize("valeur", [None, 123, "", "pas une date", {"a": 1}])
def test_date_fr_ne_leve_jamais_sur_une_donnee_externe(valeur):
    """`updated_at` vient d'un fichier d'état : une valeur absente ou mal typée ne doit
    pas empêcher d'imprimer la conduite. Le `or ""` protège du None, pas du int
    (leçon 2026-07-29 n°68)."""
    assert _date_fr(valeur) == ""


def test_un_groupe_long_devient_coupable_et_un_groupe_court_non(auth_client):
    """`break-inside: avoid` sur TOUS les groupes est ce qui creuse une demi-colonne
    de vide. Le CSS ne sait pas compter des lignes : le seuil vit côté serveur."""
    court = auth_client.post("/api/groups", json={"name": "Court"}).get_json()["id"]
    long_ = auth_client.post("/api/groups", json={"name": "Long"}).get_json()["id"]
    for i in range(SEUIL_GROUPE_LONG):
        auth_client.post("/api/people", json={"beltpack": f"1{i:02d}", "group_id": court})
    for i in range(SEUIL_GROUPE_LONG + 1):
        auth_client.post("/api/people", json={"beltpack": f"2{i:02d}", "group_id": long_})
    auth_client.post("/api/publish")

    html = auth_client.get("/admin/print").get_data(as_text=True)
    bloc_court = html.split("Court", 1)[0].rsplit("<section", 1)[1]
    bloc_long = html.split("Long", 1)[0].rsplit("<section", 1)[1]
    assert "sheet-group-long" not in bloc_court, "un groupe au seuil reste insécable"
    assert "sheet-group-long" in bloc_long, "au-delà du seuil, le groupe doit pouvoir se couper"
```

- [ ] **Step 2 : Lancer les tests et vérifier qu'ils échouent**

Run : `.venv/bin/pytest tests/test_print.py -q`
Attendu : ÉCHEC à l'import (`cannot import name 'SEUIL_GROUPE_LONG'`). C'est l'échec attendu — il prouve que rien n'existe encore.

- [ ] **Step 3 : Ajouter la constante et le formateur dans `comroster/api.py`**

Juste au-dessus de `_beltpack_sort_key` :

```python
#: Au-delà de ce nombre de membres, un groupe a le droit d'être coupé entre deux colonnes
#: ou deux pages. En deçà, il reste insécable : lire la moitié d'un groupe au verso est
#: précisément ce qui fait rater une affectation. Le seuil vit ici et non dans le CSS,
#: qui ne sait pas compter des lignes.
SEUIL_GROUPE_LONG = 12


def _date_fr(iso):
    """« 30/07/2026 à 15:13 » à partir de l'horodatage ISO UTC du modèle, en heure locale.

    Fail-safe : `updated_at` est lu dans un fichier d'état, donc une donnée EXTERNE.
    Absent, mal typé ou illisible, il ne doit pas empêcher d'imprimer la conduite —
    on rend une chaîne vide et le template omet la mention. Le `or ""` habituel ne
    suffirait pas : il protège du None, pas d'un int (leçon 2026-07-29 n°68).
    """
    if not isinstance(iso, str):
        return ""
    try:
        horodatage = datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return ""
    return horodatage.replace(tzinfo=timezone.utc).astimezone().strftime("%d/%m/%Y à %H:%M")
```

- [ ] **Step 4 : Passer les deux variables au template**

Dans `admin_print`, remplacer l'appel `render_template` par :

```python
    return render_template(
        "print.html", state=state, groups=groups, by_group=by_group,
        reserve=reserve, is_draft=draft, seuil_long=SEUIL_GROUPE_LONG,
        updated_fr=_date_fr(state.get("updated_at")),
        printed_at=datetime.now(timezone.utc).astimezone().strftime("%d/%m/%Y à %H:%M"),
    )
```

- [ ] **Step 5 : Corriger le template**

Dans `templates/print.html`, les deux `<thead>` (l. 65 et l. 86) deviennent :

```html
            <thead><tr><th class="c-bp">N°</th><th class="c-role">Rôle</th><th class="c-sign">Visa</th></tr></thead>
```

La `<section>` de groupe (l. 55) porte la classe conditionnelle :

```html
      <section class="sheet-group{% if membres|length > seuil_long %} sheet-group-long{% endif %}">
```

Le bloc de méta (l. 41-45) gagne le nombre de groupes, que la spec demande à l'en-tête.
Les deux pluriels sont accordés — « 1 groupes » trahit la machine (leçon n°51) :

```html
    <dl class="sheet-meta">
      <div><dt>Édité le</dt><dd>{{ printed_at }}</dd></div>
      <div><dt>Source</dt><dd>{% if is_draft %}Brouillon{% else %}Publié{% endif %}</dd></div>
      <div><dt>Groupes</dt><dd>{{ groups|length }}</dd></div>
      <div><dt>Total</dt><dd>{{ state.people|length }} beltpack{{ 's' if state.people|length > 1 }}</dd></div>
    </dl>
```

Et le pied (l. 97-102) cesse d'afficher l'ISO :

```html
  <footer class="sheet-foot">
    {% if brand.active %}{{ brand.name }}{% else %}ComRoster{% endif %} ·
    {{ state.title or 'Affectation Intercom' }}
    {%- if updated_fr %} · dernière modification {{ updated_fr }}{% endif %}
    {%- if brand.active %} · Propulsé par ComRoster{% endif %}
  </footer>
```

- [ ] **Step 6 : Lancer les tests et vérifier qu'ils passent**

Run : `.venv/bin/pytest tests/test_print.py tests/test_branding.py -q`
Attendu : tout PASSE. Les trois tests de branding sur `.sheet-foot` restent verts **sans avoir été modifiés** — c'est ce qui prouve que la refonte du pied n'a rien cassé.

- [ ] **Step 7 : Confronter le test de seuil à un cas qui échoue volontairement**

Remplacer temporairement `membres|length > seuil_long` par `membres|length > 0` dans le template, relancer `.venv/bin/pytest tests/test_print.py -k groupe_long -v` : le test doit ÉCHOUER sur `un groupe au seuil reste insécable`. Rétablir ensuite. Une assertion qu'on n'a jamais vue tomber ne prouve rien (leçon 2026-07-27 n°48).

- [ ] **Step 8 : Commit**

```bash
git add comroster/api.py templates/print.html tests/test_print.py
git commit -m "fix(impression): en-tête « Rôle », date française, groupes longs coupables

Trois défauts vus sur le rendu réel, pas dans le CSS. L'en-tête disait « Nom »
et affichait le rôle — le champ nom n'existe plus dans le modèle, récidive de
la leçon 32. Le pied sortait de l'ISO UTC brut en interface francophone. Et
break-inside: avoid sur tous les groupes creusait une demi-colonne de vide."
```

---

### Task 3 : Module pur des réglages

`vitest.config.js` est explicite : pas de jsdom, et « le jour où un test réclamerait un DOM, c'est le signe que la logique visée doit d'abord en sortir ». La table des réglages, la normalisation et la persistance vivent donc dans un module pur ; `print.js` (Task 5) n'en sera que le câblage.

**Files:**
- Create: `static/js/printopts.js`
- Test: `tests/js/printopts.test.js`

**Interfaces:**
- Consumes: rien.
- Produces:
  - `REGLAGES` — objet `{ cle: { attr, valeurs: string[], defaut } }`
  - `CLE_STOCKAGE: string`
  - `normalise(brut: object) => object` — toutes les clés, valeurs légales garanties
  - `effectif(opts: object) => object` — applique les contraintes entre réglages
  - `attributs(opts: object) => object` — `{ "data-cols": "1" }`, **uniquement les non-défauts**
  - `lire(store: Storage) => object` · `ecrire(store: Storage, opts: object) => void`

- [ ] **Step 1 : Écrire les tests qui échouent**

Créer `tests/js/printopts.test.js` :

```js
/* Réglages de la feuille d'impression — logique pure.

   Le point non évident que ces tests verrouillent : le DÉFAUT est l'ABSENCE
   d'attribut. `print.css` porte A3 / 3 colonnes / visa dans ses règles de base,
   chaque data-* n'étant qu'un dépassement. Une seule source pour le défaut, et
   rien à recopier entre Python et JS (leçon 2026-07-28 n°58). */
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

import { attributs, CLE_STOCKAGE, ecrire, effectif, lire, normalise, REGLAGES }
  from "../../static/js/printopts.js";

/** Faux Storage : le module ne doit dépendre que de getItem/setItem. */
function fauxStore(initial = {}) {
  const donnees = { ...initial };
  return {
    getItem: (k) => (k in donnees ? donnees[k] : null),
    setItem: (k, v) => { donnees[k] = String(v); },
  };
}

describe("normalise", () => {
  it("rend tous les réglages à leur défaut quand on ne lui donne rien", () => {
    const opts = normalise({});
    for (const [cle, def] of Object.entries(REGLAGES)) {
      expect(opts[cle]).toBe(def.defaut);
    }
  });

  it("rejette une valeur hors allowlist au lieu de la propager", () => {
    // localStorage est une donnée EXTERNE : fail-safe, jamais fail-loud (leçon n°11).
    expect(normalise({ colonnes: "12" }).colonnes).toBe(REGLAGES.colonnes.defaut);
    expect(normalise({ format: "<script>" }).format).toBe(REGLAGES.format.defaut);
    expect(normalise({ colonnes: null }).colonnes).toBe(REGLAGES.colonnes.defaut);
  });

  it("conserve une valeur légale", () => {
    expect(normalise({ colonnes: "1" }).colonnes).toBe("1");
  });
});

describe("effectif", () => {
  it("force la colonne unique quand « un groupe par page » est actif", () => {
    // Un saut de page DANS un conteneur multi-colonnes est mal supporté : plutôt que
    // de rendre un résultat imprévisible, la contrainte est explicite et testée.
    expect(effectif(normalise({ parPage: "oui", colonnes: "3" })).colonnes).toBe("1");
  });

  it("laisse les colonnes tranquilles sinon", () => {
    expect(effectif(normalise({ parPage: "non", colonnes: "3" })).colonnes).toBe("3");
  });
});

describe("attributs", () => {
  it("n'émet AUCUN attribut pour les valeurs par défaut", () => {
    expect(attributs(normalise({}))).toEqual({});
  });

  it("n'émet que les réglages qui s'écartent du défaut", () => {
    expect(attributs(normalise({ colonnes: "1" }))).toEqual({ "data-cols": "1" });
  });
});

describe("persistance", () => {
  it("relit ce qu'elle a écrit", () => {
    const store = fauxStore();
    ecrire(store, normalise({ colonnes: "2", visa: "non" }));
    const relu = lire(store);
    expect(relu.colonnes).toBe("2");
    expect(relu.visa).toBe("non");
  });

  it("retombe sur les défauts si le stockage est vide ou illisible", () => {
    expect(lire(fauxStore()).colonnes).toBe(REGLAGES.colonnes.defaut);
    expect(lire(fauxStore({ [CLE_STOCKAGE]: "{ pas du json" })).colonnes)
      .toBe(REGLAGES.colonnes.defaut);
  });
});

describe("garde structurelle", () => {
  it("chaque valeur non-défaut a un sélecteur correspondant dans print.css", () => {
    /* Sans cette garde, ajouter une valeur à l'allowlist donnerait un réglage
       cliquable SANS effet — un contrôle qui ne fait rien ment. Même famille que
       le test des jetons CSS (leçon n°62) : on vérifie l'inclusion. */
    const css = readFileSync(new URL("../../static/css/print.css", import.meta.url), "utf8");
    const manquants = [];
    for (const def of Object.values(REGLAGES)) {
      for (const valeur of def.valeurs) {
        if (valeur === def.defaut) continue;       // le défaut vit dans les règles de base
        if (!css.includes(`[${def.attr}="${valeur}"]`)) manquants.push(`${def.attr}="${valeur}"`);
      }
    }
    expect(manquants).toEqual([]);
  });
});
```

- [ ] **Step 2 : Lancer les tests et vérifier qu'ils échouent**

Run : `npm test`
Attendu : ÉCHEC de résolution du module `printopts.js`. Lire le **nombre de tests exécutés**, pas le code retour : « 0 passed » est un échec déguisé (leçon n°73).

- [ ] **Step 3 : Écrire le module**

Créer `static/js/printopts.js` :

```js
/* Réglages de la feuille d'impression — logique PURE, sans DOM.

   Séparé de print.js parce que le harnais vitest tourne en `environment: "node"` :
   sa config le dit, « le jour où un test réclamerait un DOM, c'est le signe que la
   logique visée doit d'abord en sortir ».

   UNE table décrit chaque réglage. La lecture, l'écriture, la persistance et le
   câblage la PARCOURENT : ajouter un réglage ne demande de le recopier nulle part
   (leçon 2026-07-28 n°58, où deux champs oubliés d'une énumération manuelle
   s'effaçaient en silence).

   LE DÉFAUT N'EST PAS UN ATTRIBUT : c'est son absence. Les règles de base de
   print.css valent A3 portrait / 3 colonnes / visa ; chaque data-* est un
   DÉPASSEMENT. D'où une seule source pour le défaut, aucune duplication entre
   Python et JS, et aucun scintillement au chargement. */

export const REGLAGES = {
  format: {
    attr: "data-format",
    valeurs: ["a3-portrait", "a3-paysage", "a4-portrait", "a4-paysage", "a5-portrait"],
    defaut: "a3-portrait",
  },
  colonnes: { attr: "data-cols", valeurs: ["1", "2", "3"], defaut: "3" },
  visa: { attr: "data-visa", valeurs: ["oui", "non"], defaut: "oui" },
  cases: { attr: "data-cases", valeurs: ["oui", "non"], defaut: "non" },
  reserve: { attr: "data-reserve", valeurs: ["oui", "non"], defaut: "oui" },
  parPage: { attr: "data-par-page", valeurs: ["oui", "non"], defaut: "non" },
};

export const CLE_STOCKAGE = "comroster.impression";

/** Toutes les clés présentes, toutes les valeurs légales. Une valeur inconnue
 *  retombe sur le défaut sans lever : le stockage est une donnée externe, donc
 *  fail-safe et jamais fail-loud (leçon n°11). */
export function normalise(brut) {
  const source = brut && typeof brut === "object" ? brut : {};
  const opts = {};
  for (const [cle, def] of Object.entries(REGLAGES)) {
    opts[cle] = def.valeurs.includes(source[cle]) ? source[cle] : def.defaut;
  }
  return opts;
}

/** Contraintes ENTRE réglages, appliquées après normalisation.
 *  Un saut de page à l'intérieur d'un conteneur multi-colonnes est mal supporté :
 *  « un groupe par page » impose donc la colonne unique. La barre désactive le
 *  segment Colonnes en conséquence — un contrôle qui ne ferait rien mentirait. */
export function effectif(opts) {
  return opts.parPage === "oui" ? { ...opts, colonnes: "1" } : { ...opts };
}

/** Uniquement les réglages qui S'ÉCARTENT du défaut : le défaut est l'absence. */
export function attributs(opts) {
  const sortie = {};
  for (const [cle, def] of Object.entries(REGLAGES)) {
    if (opts[cle] !== def.defaut) sortie[def.attr] = opts[cle];
  }
  return sortie;
}

export function lire(store) {
  let brut = null;
  try {
    brut = JSON.parse(store.getItem(CLE_STOCKAGE) || "{}");
  } catch {
    brut = null;                        // stockage illisible : on repart des défauts
  }
  return normalise(brut);
}

export function ecrire(store, opts) {
  try {
    store.setItem(CLE_STOCKAGE, JSON.stringify(normalise(opts)));
  } catch {
    /* Quota plein ou stockage refusé (navigation privée) : ne pas perdre l'impression
       en cours pour un réglage non mémorisé. */
  }
}
```

- [ ] **Step 4 : Lancer les tests**

Run : `npm test`
Attendu : tous les tests de `printopts.test.js` PASSENT **sauf** « garde structurelle », qui échoue en listant les sélecteurs absents de `print.css` — normal, Task 4 ne les a pas encore écrits. Noter la liste : elle est le cahier des charges de Task 4.

- [ ] **Step 5 : Neutraliser temporairement la garde structurelle**

Ajouter `.skip` à ce seul test (`it.skip("chaque valeur non-défaut…")`) avec le commentaire `// Réactivé en Task 4, une fois les sélecteurs écrits.` Ne jamais committer une suite rouge (leçon n°43).

- [ ] **Step 6 : Lancer les tests et vérifier qu'ils passent**

Run : `npm test`
Attendu : les 30 tests existants + les nouveaux, tous verts, 1 skipped. **Lire le nombre exécuté**, pas le code retour.

- [ ] **Step 7 : Commit**

```bash
git add static/js/printopts.js tests/js/printopts.test.js
git commit -m "feat(impression): table des réglages, pure et testable sous Node

Une seule table décrit les six réglages ; lecture, persistance et câblage la
parcourent, donc ajouter un réglage ne demande de le recopier nulle part
(leçon 58). Le défaut est l'ABSENCE d'attribut : print.css porte A3 / 3
colonnes / visa dans ses règles de base, chaque data-* est un dépassement."
```

---

### Task 4 : Refonte de `print.css`

**Files:**
- Modify: `static/css/print.css` (réécriture large)
- Modify: `tests/js/printopts.test.js` (réactiver la garde)

**Interfaces:**
- Consumes: les noms d'attributs de `REGLAGES` (Task 3) — `data-format`, `data-cols`, `data-visa`, `data-cases`, `data-reserve`, `data-par-page`.
- Produces: les classes attendues par le template de Task 5 — `.sheet-band` (bandeau répété), `.print-opts` / `.opt` / `.opt-seg` (barre), `.c-remis` (colonne des cases). `.sheet-group-long` est déjà posée en Task 2.

- [ ] **Step 1 : Réactiver la garde structurelle**

Retirer le `.skip` posé en Task 3, Step 5. Run : `npm test` → ÉCHEC listant les sélecteurs manquants. C'est ce test qui pilote la tâche.

- [ ] **Step 2 : Poser les règles de base (le défaut A3 / 3 colonnes)**

Dans `static/css/print.css`, remplacer le commentaire d'en-tête (l. 1-11) et le bloc `@page` (l. 172-175) :

```css
/* ============================================================================
   Feuille d'affectation à imprimer.

   Registre volontairement DIFFÉRENT de l'écran de régie : encre noire sur blanc et
   pas d'indicateur temps réel — le papier ne se met pas à jour, prétendre le
   contraire serait mentir.

   Défaut : A3 portrait sur trois colonnes, parce que c'est ainsi que la conduite
   est tirée en pratique. Ce défaut vit UNIQUEMENT ici, dans les règles de base :
   chaque `data-*` posé par printopts.js n'est qu'un DÉPASSEMENT. Rien à recopier
   côté serveur, et rien qui scintille au chargement.

   La couleur de groupe survit sous forme de FILET : elle identifie sans coûter
   d'encre et reste lisible sur une imprimante monochrome.

   ÉCART ASSUMÉ au principe « aucun aplat de couleur » qui figurait ici : la zébrure
   est rétablie EN COLONNE UNIQUE seulement. Sur 27 cm de large l'œil dérive d'une
   ligne à l'autre et elle sert ; en trois colonnes les lignes sont courtes et elle
   ne coûterait que de l'encre. Elle n'est donc pas un réglage — elle découle du
   nombre de colonnes.
   ========================================================================== */

@page { size: A3 portrait; margin: 12mm 10mm 16mm; }
```

- [ ] **Step 3 : Écrire les sélecteurs de format**

```css
/* Formats. `printopts.js` insère la règle @page correspondante en CSSOM (une @page ne
   peut pas être conditionnée par un sélecteur) ; ces règles-ci pilotent ce qui, dans
   le CORPS, dépend du format — l'échelle typographique sur une surface plus petite. */
[data-format="a3-paysage"] .print-page { font-size: 10.5pt; }
[data-format="a4-portrait"] .print-page { font-size: 9.5pt; }
[data-format="a4-paysage"] .print-page { font-size: 9.5pt; }
[data-format="a5-portrait"] .print-page { font-size: 8.5pt; }
```

- [ ] **Step 4 : Écrire les sélecteurs de colonnes, visa, cases, réserve, page par groupe**

Remplacer la règle `.sheet-groups` existante (l. 95-101), puis ajouter à la suite :

```css
/* Colonnes. Le défaut (3) est ici ; les règles suivantes ne sont que des dépassements. */
.sheet-groups { padding: 0; column-count: 3; column-gap: 8mm; }
[data-cols="1"] .sheet-groups { column-count: 1; }
[data-cols="2"] .sheet-groups { column-count: 2; }

/* Zébrure : en colonne unique SEULEMENT, où la ligne fait 27 cm et où l'œil dérive.
   Sans print-color-adjust le navigateur supprime les fonds pour économiser l'encre. */
[data-cols="1"] .sheet-table tbody tr:nth-child(even) td {
  background: var(--zebre);
  -webkit-print-color-adjust: exact;
  print-color-adjust: exact;
}

/* Visa : colonne large de 28 mm — à 3,2 em on ne pouvait rien y signer. */
.c-sign { width: 28mm; }
[data-visa="non"] .c-sign { display: none; }

/* Case « Remis », à cocher au crayon pendant la distribution. */
.c-remis { display: none; width: 12mm; text-align: center; }
[data-cases="oui"] .c-remis { display: table-cell; }

[data-reserve="non"] .sheet-reserve { display: none; }

/* Un groupe par page. `printopts.effectif()` force déjà data-cols="1" : un saut de page
   dans un conteneur multi-colonnes est mal supporté. */
[data-par-page="oui"] .sheet-group { break-before: page; page-break-before: always; }
[data-par-page="oui"] .sheet-group:first-child { break-before: auto; page-break-before: auto; }
```

- [ ] **Step 5 : Rendre les groupes longs coupables**

Remplacer la règle `.sheet-group` existante (l. 102-108) :

```css
.sheet-group {
  /* Un groupe court ne doit JAMAIS être coupé : lire la moitié d'un groupe au verso
     est précisément ce qui fait rater une affectation. Mais l'imposer à TOUS creusait
     une demi-colonne de vide — au-delà du seuil serveur (SEUIL_GROUPE_LONG), le groupe
     se coupe, en répétant son en-tête de tableau. */
  break-inside: avoid;
  page-break-inside: avoid;
  margin: 0 0 6mm;
}
.sheet-group-long { break-inside: auto; page-break-inside: auto; }
.sheet-group-long .sheet-table thead { display: table-header-group; }
```

- [ ] **Step 6 : Poser les jetons et le bandeau répété**

Compléter le `:root` (l. 13-19). **Tout `var(--x)` doit y être défini** : `print.css` est autonome et une variable absente retombe en silence sur son repli (leçon n°62).

```css
:root {
  --ink: #14181f;
  --ink-soft: #4a5462;
  --ink-faint: #8a94a6;
  --rule: #d5dae2;
  --paper: #ffffff;
  --zebre: #f4f6f8;
}

/* Bandeau d'identification, répété sur CHAQUE page (mesuré : Chromium répète les
   éléments `position: fixed` à l'impression). Une conduite qui se sépare garde son
   identité feuille par feuille — c'est tout l'objet d'un document « filet ». */
.sheet-band { display: none; }
```

- [ ] **Step 7 : Compléter le bloc `@media print` et ajouter le numéro de page**

Remplacer le bloc `@media print` existant (l. 177-187) :

```css
@media print {
  /* Ce qui n'a de sens qu'à l'écran disparaît : la barre d'action et ses réglages. */
  .print-bar { display: none; }
  .print-page { padding: 0; }
  .sheet-head { padding: 0 0 4mm; }
  .sheet-groups { padding: 4mm 0 0; }
  .sheet-foot { padding: 3mm 0 0; }
  /* L'en-tête de groupe ne doit pas rester seul en bas de colonne. */
  .sheet-group-name { break-after: avoid; page-break-after: avoid; }

  .sheet-band {
    display: block;
    position: fixed;
    bottom: 0; left: 0; right: 0;
    padding-top: 1.5mm;
    border-top: 1px solid var(--rule);
    font-size: 7.5pt;
    color: var(--ink-faint);
  }
}

/* Numéro de page en boîte de marge. Mesuré supporté par Chromium (le boîtier en est
   un) ; Firefox et Safari l'ignorent en silence et leur pied natif le fournit. */
@page {
  @bottom-right { content: "page " counter(page) " / " counter(pages); }
}
```

- [ ] **Step 8 : Aérer l'en-tête et la grille**

Remplacer les règles `.sheet-head`, `.sheet-head h1`, `.sheet-meta` et `.sheet-table td` :

```css
.sheet-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 12mm;
  padding: 6mm 0 4mm;
  border-bottom: 2px solid var(--ink);
}
.sheet-head h1 { margin: 0; font-size: 22pt; letter-spacing: -0.015em; }
.sheet-meta { display: flex; gap: 8mm; margin: 0; text-align: right; }
.sheet-table td {
  padding: 1.4mm .4rem 1.4mm 0;
  border-bottom: 1px solid var(--rule);
  vertical-align: baseline;
}
```

- [ ] **Step 9 : Lancer la garde et le contrôle des jetons**

Run : `npm test` puis `.venv/bin/pytest tests/test_css_tokens.py -q`
Attendu : la garde structurelle PASSE (chaque valeur non-défaut a son sélecteur) et `--zebre` est bien déclaré.

- [ ] **Step 10 : Confronter la garde à un cas qui échoue volontairement**

Ajouter `"4"` aux valeurs de `colonnes` dans `printopts.js`, relancer `npm test` : la garde doit ÉCHOUER en signalant `data-cols="4"`. Retirer ensuite. Sans ça, on ne saurait pas qu'elle mord (leçon n°33).

- [ ] **Step 11 : Commit**

```bash
git add static/css/print.css tests/js/printopts.test.js
git commit -m "feat(impression): format A3 de production, réglé par attributs

Défaut A3 portrait sur trois colonnes, posé UNIQUEMENT dans les règles de base :
chaque data-* n'est qu'un dépassement. Bandeau d'identification répété par page
et numéro de page en boîte de marge, deux capacités mesurées sur PDF réel avant
d'être promises. Zébrure rétablie en colonne unique seulement — écart assumé au
« aucun aplat », et le commentaire d'en-tête le dit désormais."
```

---

### Task 5 : La barre de réglages

**Files:**
- Modify: `templates/print.html:14-28` (la barre), les deux tableaux, le script, le bandeau
- Modify: `static/js/print.js` (réécriture)
- Modify: `static/css/print.css` (habillage de la barre)

**Interfaces:**
- Consumes: `printopts.js` — `REGLAGES`, `attributs`, `effectif`, `ecrire`, `lire`.
- Produces: les `id` consommés par les tests e2e de Task 6 — `#opt-format`, `#opt-cols` (conteneur de trois `button[data-valeur]`), `#opt-visa`, `#opt-cases`, `#opt-reserve`, `#opt-par-page`, `#print-now`.

- [ ] **Step 1 : Remplacer la barre dans `templates/print.html`**

```html
  {# Barre d'action et de réglages : à l'écran seulement, `@media print` la retire.
     Tout est visible d'un coup — replier ces options dans un menu déroulant irait
     contre la demande, qui était justement que le menu n'était pas assez complet. #}
  <div class="print-bar">
    <a class="print-back" href="{{ url_for('api.admin_page') }}">← Administration</a>
    <span class="print-source">
      {% if is_draft %}Brouillon en préparation{% else %}État publié — ce que la salle voit{% endif %}
    </span>
    <span class="print-swap">
      {% if is_draft %}
        <a href="{{ url_for('api.admin_print') }}">Imprimer l'état publié</a>
      {% else %}
        <a href="{{ url_for('api.admin_print', draft=1) }}">Imprimer le brouillon</a>
      {% endif %}
    </span>

    <div class="print-opts">
      <label class="opt"><span>Format</span>
        <select id="opt-format">
          <option value="a3-portrait">A3 portrait</option>
          <option value="a3-paysage">A3 paysage</option>
          <option value="a4-portrait">A4 portrait</option>
          <option value="a4-paysage">A4 paysage</option>
          <option value="a5-portrait">A5 portrait</option>
        </select>
      </label>
      <span class="opt opt-seg"><span>Colonnes</span>
        <span id="opt-cols" role="group" aria-label="Nombre de colonnes">
          <button type="button" data-valeur="1">1</button>
          <button type="button" data-valeur="2">2</button>
          <button type="button" data-valeur="3">3</button>
        </span>
      </span>
      <label class="opt"><input type="checkbox" id="opt-visa"> Visa</label>
      <label class="opt"><input type="checkbox" id="opt-cases"> Cases</label>
      <label class="opt"><input type="checkbox" id="opt-reserve"> Non affectés</label>
      <label class="opt"><input type="checkbox" id="opt-par-page"> 1 groupe/page</label>
    </div>

    <button type="button" id="print-now" class="print-go">Imprimer</button>
  </div>
```

- [ ] **Step 2 : Ajouter la colonne « Remis » aux deux tableaux**

Dans les **deux** `<thead>` et les **deux** `<tbody>`, insérer la cellule entre le rôle et le visa :

```html
            <thead><tr><th class="c-bp">N°</th><th class="c-role">Rôle</th><th class="c-remis">Remis</th><th class="c-sign">Visa</th></tr></thead>
```

```html
                <tr><td class="c-bp">{{ p.beltpack }}</td><td class="c-role">{{ p.role or '—' }}</td><td class="c-remis">☐</td><td class="c-sign"></td></tr>
```

- [ ] **Step 3 : Charger le script en module**

Remplacer la ligne 104 de `templates/print.html` :

```html
  <script type="module" src="{{ url_for('static', filename='js/print.js') }}"></script>
```

- [ ] **Step 4 : Ajouter le bandeau répété**

Juste avant `<footer class="sheet-foot">` :

```html
  {# Répété au pied de CHAQUE page à l'impression : une conduite qui se sépare doit
     rester identifiable feuille par feuille. #}
  <div class="sheet-band">
    {{ state.production_name or state.title or 'Affectation Intercom' }} ·
    {% if is_draft %}Brouillon{% else %}Publié{% endif %} · édité le {{ printed_at }}
  </div>
```

- [ ] **Step 5 : Réécrire `static/js/print.js`**

```js
/* Feuille d'affectation — câblage DOM des réglages.

   Toute la logique (allowlist, défauts, contraintes, persistance) vit dans
   printopts.js, qui est PUR et testé sous Node. Ce fichier-ci ne fait que
   brancher des contrôles dessus.

   Pas d'`onclick` inline ni d'attribut `style` : la CSP stricte l'interdit
   (leçon 2026-07-07) et un test serveur le verrouille. Les data-* passent par
   setAttribute, la règle @page par insertRule — jamais par un attribut de style.

   Pas d'impression automatique au chargement : ouvrir la feuille pour la RELIRE
   est le cas le plus fréquent, et une boîte d'impression surgissante serait une
   décision prise à la place de l'utilisateur. */
import { attributs, ecrire, effectif, lire, REGLAGES } from "./printopts.js";

const TAILLES = {
  "a3-portrait": "A3 portrait", "a3-paysage": "A3 landscape",
  "a4-portrait": "A4 portrait", "a4-paysage": "A4 landscape",
  "a5-portrait": "A5 portrait",
};

const CASES = [["visa", "opt-visa"], ["cases", "opt-cases"],
               ["reserve", "opt-reserve"], ["parPage", "opt-par-page"]];

let opts = lire(window.localStorage);

/** Une @page ne peut pas être conditionnée par un sélecteur : la règle du format
 *  retenu est INSÉRÉE, et écrase celle de base par ordre de cascade. */
function poserFormat(format) {
  const feuille = document.styleSheets[0];
  try {
    feuille.insertRule(`@page { size: ${TAILLES[format]}; }`, feuille.cssRules.length);
  } catch {
    /* Feuille pas encore chargée ou d'une autre origine : le défaut A3 du CSS tient. */
  }
}

function appliquer() {
  const vue = effectif(opts);
  const poses = attributs(vue);
  for (const def of Object.values(REGLAGES)) {
    const valeur = poses[def.attr];
    if (valeur === undefined) document.documentElement.removeAttribute(def.attr);
    else document.documentElement.setAttribute(def.attr, valeur);
  }
  poserFormat(vue.format);

  // Reflet des contrôles, y compris la contrainte : « 1 groupe/page » impose la
  // colonne unique, donc le segment Colonnes est DÉSACTIVÉ — un contrôle qui
  // resterait actif sans effet mentirait.
  document.getElementById("opt-format").value = opts.format;
  for (const btn of document.querySelectorAll("#opt-cols button")) {
    btn.setAttribute("aria-pressed", String(btn.dataset.valeur === vue.colonnes));
    btn.disabled = opts.parPage === "oui";
  }
  for (const [cle, id] of CASES) {
    document.getElementById(id).checked = opts[cle] === "oui";
  }
  ecrire(window.localStorage, opts);
}

function regler(cle, valeur) {
  opts = { ...opts, [cle]: valeur };
  appliquer();
}

document.getElementById("opt-format")
  .addEventListener("change", (e) => regler("format", e.target.value));
document.getElementById("opt-cols").addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-valeur]");
  if (btn) regler("colonnes", btn.dataset.valeur);
});
for (const [cle, id] of CASES) {
  document.getElementById(id)
    .addEventListener("change", (e) => regler(cle, e.target.checked ? "oui" : "non"));
}
document.getElementById("print-now").addEventListener("click", () => window.print());

// Filets de couleur : posés en CSSOM, jamais en attribut `style` (CSP).
document.querySelectorAll(".sheet-rule[data-color]").forEach((el) => {
  el.style.background = el.dataset.color;
});

appliquer();
```

- [ ] **Step 6 : Habiller la barre dans `print.css`**

À la suite des règles `.print-bar` existantes. Noter que `.print-swap` perd son `margin-left: auto`, désormais porté par `.print-opts`.

```css
.print-swap { margin-left: 0; }
.print-opts { display: flex; align-items: center; gap: 1rem; margin-left: auto; font-size: 9pt; }
.opt { display: flex; align-items: center; gap: .35rem; color: var(--ink-soft); }
.opt select { font: inherit; padding: .15rem .3rem; }
.opt-seg span[role="group"] { display: inline-flex; }
.opt-seg button {
  font: inherit;
  padding: .15rem .5rem;
  cursor: pointer;
  border: 1px solid var(--rule);
  background: var(--paper);
  color: var(--ink-soft);
}
.opt-seg button[aria-pressed="true"] { background: var(--ink); border-color: var(--ink); color: #fff; }
.opt-seg button:disabled { opacity: .45; cursor: not-allowed; }
```

- [ ] **Step 7 : Vérifier que la CSP n'est pas violée**

Run : `.venv/bin/pytest tests/test_print.py -q`
Attendu : PASSE, en particulier `test_la_feuille_n_a_ni_script_inline_ni_style_inline` — aucun `style="`, aucun `<style`, aucun `onclick` dans le HTML rendu.

- [ ] **Step 8 : Commit**

```bash
git add templates/print.html static/js/print.js static/css/print.css
git commit -m "feat(impression): barre de six réglages mémorisés

Format, colonnes, visa, cases, non affectés, un groupe par page — tout visible
d'un coup, replier ces options aurait reconduit le reproche de départ. Les choix
sont mémorisés : sans persistance, l'A3 serait à re-choisir à chaque impression.
« 1 groupe/page » désactive le segment Colonnes plutôt que de l'ignorer."
```

---

### Task 6 : Vérifier le rendu PAPIER

Tout ce qui précède se vérifie dans le DOM. Rien de cela ne prouve qu'une feuille A3 sort correctement — et un pied qui annonce « page 1 / 2 » doit être lu dans un PDF à deux pages, pas supposé (leçons 42 et 55).

**Files:**
- Create: `tests/e2e/test_impression_papier.py`

**Interfaces:**
- Consumes: la fixture `live_server` de `tests/e2e/conftest.py` et la fixture `page` de Playwright. Le helper d'entrée dans l'admin est **recopié localement** : `tests/e2e` n'est pas un package, un `from .helpers import` y échoue (leçon n°73).
- Produces: rien.

- [ ] **Step 1 : Écrire les tests qui échouent**

Créer `tests/e2e/test_impression_papier.py` :

```python
"""Le rendu PAPIER de la feuille d'impression, lu dans un vrai PDF.

Tous les autres tests portent sur le DOM. Aucun ne dit si une A3 sort correctement.
Les capacités exercées ici (taille de page honorée, `position: fixed` répété par page,
numéro de page en boîte de marge) ont été MESURÉES avant d'être promises — elles sont
spécifiques à Chromium, ce qui est acceptable : le boîtier en est un.
"""
import shutil
import subprocess

import pytest

pytestmark = pytest.mark.e2e

besoin_poppler = pytest.mark.skipif(
    shutil.which("pdftotext") is None or shutil.which("pdfinfo") is None,
    reason="poppler absent — seul moyen de LIRE le PDF plutôt que de le supposer",
)


def _plateau_publie(page, live_server):
    """Un plateau assez fourni pour déborder sur une deuxième page A3."""
    page.goto(live_server + "/admin/setup")
    page.fill("input[type=password]", "motdepasse8")
    page.click("button[type=submit]")
    page.wait_for_selector("#add-block-btn")
    for nom in ("Régie", "Son", "Lumière", "Plateau"):
        page.click("#add-block-btn")
        page.fill("#block-name", nom)
        page.click("#block-form button[type=submit]")
    for numero in range(1, 61):
        page.click("#add-beltpack-pool")
        page.fill("#person-beltpack", str(numero))
        page.fill("#person-role", f"Poste {numero}")
        page.click("#person-form button[type=submit]")
    page.click("#publish-btn")
    page.keyboard.press("Control+Enter")
    page.wait_for_selector("#sync-label:has-text('À jour')")


def _feuille(page, live_server):
    feuille = page.context.new_page()
    feuille.goto(live_server + "/admin/print")
    feuille.wait_for_selector(".sheet-table")
    return feuille


@besoin_poppler
def test_la_feuille_sort_en_a3_avec_bandeau_et_numero_sur_chaque_page(page, live_server, tmp_path):
    _plateau_publie(page, live_server)
    feuille = _feuille(page, live_server)

    pdf = tmp_path / "conduite.pdf"
    feuille.pdf(path=str(pdf), prefer_css_page_size=True)

    infos = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True).stdout
    assert "841.92 x 1191.12" in infos, f"A3 portrait attendu, obtenu :\n{infos}"

    texte = subprocess.run(["pdftotext", str(pdf), "-"], capture_output=True, text=True).stdout
    pages = texte.count("\f")
    assert pages >= 2, "le plateau doit déborder sur une 2e page pour que le test morde"
    assert texte.count("édité le") >= pages, "le bandeau doit se répéter sur CHAQUE page"
    assert f"page {pages} / {pages}" in texte, "numéro de page absent de la dernière page"
    feuille.close()


@besoin_poppler
def test_le_reglage_de_format_change_vraiment_le_papier(page, live_server, tmp_path):
    """Un réglage qui ne changerait rien au PDF serait un contrôle décoratif — c'est
    exactement le défaut des <kbd> non câblés du 2026-07-25 (leçon n°38)."""
    _plateau_publie(page, live_server)
    feuille = _feuille(page, live_server)

    feuille.select_option("#opt-format", "a4-paysage")
    pdf = tmp_path / "paysage.pdf"
    feuille.pdf(path=str(pdf), prefer_css_page_size=True)
    infos = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True).stdout
    assert "841.92 x 594.96" in infos, f"A4 paysage attendu, obtenu :\n{infos}"
    feuille.close()


def test_les_reglages_sont_memorises_d_une_ouverture_a_l_autre(page, live_server):
    _plateau_publie(page, live_server)
    feuille = _feuille(page, live_server)
    feuille.click("#opt-cols button[data-valeur='1']")
    feuille.wait_for_selector("html[data-cols='1']", state="attached")

    feuille.reload()
    # `state="attached"` obligatoire : <html> n'a pas de géométrie propre et le
    # `visible` implicite de Playwright expirerait (leçons n°33 et n°50).
    feuille.wait_for_selector("html[data-cols='1']", state="attached")
    assert feuille.get_attribute("html", "data-cols") == "1"
    feuille.close()


def test_un_groupe_par_page_desactive_le_choix_des_colonnes(page, live_server):
    """Un contrôle qui reste actif mais sans effet ment à l'utilisateur."""
    _plateau_publie(page, live_server)
    feuille = _feuille(page, live_server)
    feuille.check("#opt-par-page")
    feuille.wait_for_selector("#opt-cols button:disabled")
    assert feuille.get_attribute("html", "data-cols") == "1"
    feuille.close()


def test_actionner_chaque_reglage_ne_produit_aucune_erreur_console(page, live_server):
    """Une violation de CSP n'apparaît QUE dans la console : le test serveur vérifie
    l'absence de `style=` dans le HTML, il ne voit pas ce que le JS fait ensuite.

    Le témoin POSITIF (`journal`) est indispensable : sans lui, `erreurs == []`
    passerait au vert même si le collecteur ne s'était jamais armé — l'assertion
    creuse du 2026-07-23 (leçon n°33)."""
    _plateau_publie(page, live_server)
    feuille = page.context.new_page()
    erreurs, journal = [], []
    feuille.on("console", lambda m: (journal.append(m.type),
                                     erreurs.append(m.text) if m.type == "error" else None))
    feuille.on("pageerror", lambda e: erreurs.append(str(e)))
    feuille.goto(live_server + "/admin/print")
    feuille.wait_for_selector(".sheet-table")

    feuille.select_option("#opt-format", "a4-portrait")
    feuille.click("#opt-cols button[data-valeur='1']")
    for case in ("#opt-visa", "#opt-cases", "#opt-reserve", "#opt-par-page"):
        feuille.click(case)
    feuille.wait_for_selector("html[data-par-page='oui']", state="attached")

    feuille.evaluate("console.debug('sonde')")      # prouve que le collecteur est armé
    assert journal, "collecteur console jamais armé — l'assertion suivante ne prouverait rien"
    assert erreurs == []
    feuille.close()
```

- [ ] **Step 2 : Lancer et vérifier l'échec**

Run : `.venv/bin/pytest tests/e2e/test_impression_papier.py -m e2e -q`
Attendu : ÉCHEC. **Le marqueur `-m e2e` est obligatoire** — sans lui, « 4 deselected » et un code retour 0 ressembleraient à un succès (leçon n°73).

- [ ] **Step 3 : Corriger ce que les échecs révèlent**

Ces tests exercent l'intégration réelle des Tasks 4 et 5. Traiter chaque échec à sa racine dans `print.css` ou `print.js` — ne jamais assouplir une assertion pour la faire passer.

- [ ] **Step 4 : Lancer la suite complète**

Quatre commandes **séparées**, dont on LIT chaque résultat (ne jamais les enchaîner par `&&` derrière un pipe, leçon n°43) :

```bash
.venv/bin/pytest -q
.venv/bin/pytest -m e2e -q
npm test
.venv/bin/ruff check .
```

Attendu : tout vert, et le **nombre** de tests exécutés cohérent (≈ 500 unitaires, ≈ 40 e2e, ≈ 37 JS). Un « 0 passed » est un échec déguisé.

- [ ] **Step 5 : Contrôle visuel du rendu**

Ouvrir `/admin/print`, lancer un aperçu d'impression réel, et vérifier de l'œil ce qu'aucun test ne voit : équilibre des colonnes, en-tête qui ne touche plus le bord droit, colonne de visa où l'on peut effectivement signer. Un test source est nécessaire mais ne remplace pas le contrôle du rendu (leçon 2026-07-29 n°69).

- [ ] **Step 6 : Commit**

```bash
git add tests/e2e/test_impression_papier.py
git commit -m "test(impression): vérifier le PAPIER, pas seulement le DOM

Le PDF est lu : A3 honoré, bandeau présent sur chaque page, numéro de page en
dernière page, et le réglage de format change réellement les dimensions. Un
réglage qui ne changerait rien au PDF serait décoratif — c'est le défaut des
<kbd> non câblés de la leçon 38."
```

---

### Task 7 : Consigner le lot

**Files:**
- Modify: `tasks/todo.md` · `tasks/lessons.md` · `README.md`

- [ ] **Step 1 : Vérifier chaque affirmation du README avant de la laisser en place**

Run : `rtk proxy grep -n "print\|imprim\|Impression" README.md`
Contrôler par grep dans le code chaque affirmation vérifiable (route, réglages, défauts). Une passe de doc n'est pas une relecture de style : la documentation est le chemin qui dérive en silence (leçon n°32). Documenter le défaut A3 / 3 colonnes et les six réglages.

- [ ] **Step 2 : Ajouter la section du lot à `tasks/todo.md`**

Consigner ce qui a été livré, le coût assumé (le numéro de page est une spécificité Chromium, absent sur Firefox et Safari), et les défauts du plan trouvés à l'exécution.

- [ ] **Step 3 : Ajouter les leçons à `tasks/lessons.md`**

Au format `[date] | ce qui a mal tourné | règle pour l'éviter`. Deux candidates déjà acquises :
- l'en-tête « NOM » affichant le rôle est la **deuxième** occurrence du champ nom fantôme après le README du 2026-07-23 — la règle est de chercher TOUS les sites d'un champ au moment de sa suppression, pas au fil des découvertes ; c'est la leçon n°71 (« corriger une cause racine, c'est corriger sa CLASSE ») appliquée à une suppression de champ ;
- j'ai failli écarter le numéro de page en le croyant inconstructible sous Chromium : une capacité de plateforme se **sonde** avant d'être refusée, une croyance périmée coûte une fonction.

- [ ] **Step 4 : Commit**

```bash
git add tasks/todo.md tasks/lessons.md README.md
git commit -m "docs: consigner le lot « Impression » et ses deux leçons"
```
