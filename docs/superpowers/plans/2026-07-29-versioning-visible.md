# Versioning visible — plan d'implémentation

> **Pour les agents :** SOUS-COMPÉTENCE REQUISE — utiliser `superpowers:subagent-driven-development` (recommandé) ou `superpowers:executing-plans` pour exécuter ce plan tâche par tâche. Les étapes utilisent la syntaxe case à cocher (`- [ ]`).

**Objectif :** rendre lisible, sur trois écrans et une API, le code exact que fait tourner un boîtier — sans qu'aucun numéro ne soit jamais saisi à la main.

**Architecture :** `deploy/setup-pi.sh` interroge git au déploiement et grave une ligne de texte dans `comroster/VERSION`. Ce fichier a deux lecteurs — `comroster/services/version.py` côté Python, `deploy/kiosk-run.sh` côté shell — d'où le texte nu plutôt que du JSON, qui imposerait `jq`. Le service charge le fichier une fois au démarrage, comme `branding.py` et `lifetime.py`, et applique la même politique fail-safe.

**Pile technique :** Python 3 / Flask (sans nouvelle dépendance), Jinja2, JavaScript nu, bash et sh POSIX, pytest.

**Conception de référence :** [docs/superpowers/specs/2026-07-29-versioning-visible-design.md](../specs/2026-07-29-versioning-visible-design.md)

## Contraintes globales

Ces règles s'appliquent à **toutes** les tâches ci-dessous.

- **Aucune nouvelle dépendance.** Ni Python, ni JavaScript, ni paquet système. L'engagement « zéro dépendance JS au runtime » du README tient.
- **Aucun appel à l'exécutable `git` au runtime.** Ni `subprocess`, ni `os.system`. Le shell de déploiement seul appelle git. En production, `git` peut ne pas être installé.
- **`--dirty` est interdit** dans tout appel à `git describe` : l'option force un rafraîchissement de l'index, qu'un système de fichiers monté en lecture seule refuse.
- **Politique appliance fail-safe.** Toute lecture qui échoue retourne une valeur neutre et journalise un avertissement. Jamais d'exception qui empêcherait une page de s'afficher. Modèle : `comroster/services/lifetime.py:_load`.
- **Jamais un numéro inventé.** Si l'information n'est pas connue, l'afficher comme inconnue ou ne rien afficher — jamais une valeur par défaut plausible.
- **Français dans tout le code produit** : docstrings, commentaires, noms de tests, libellés d'interface. Les commentaires expliquent le *pourquoi*, pas le *quoi* — c'est la convention du dépôt.
- **Commits en français**, préfixés `feat:` / `fix:` / `docs:` / `test:`, avec `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>` en pied.
- **Format du fichier `comroster/VERSION`** : une ligne, trois champs séparés par une espace simple, terminée par un saut de ligne.
  ```
  v1.4.0+7 9f3c1a2 2026-07-29
  ```
  Champ 1 `label` (déjà normalisé par le shell), champ 2 `commit` (SHA court), champ 3 `date` (`YYYY-MM-DD`).

---

## Structure des fichiers

| Fichier | Responsabilité |
|---|---|
| `comroster/services/version.py` | **Créé.** Lit `comroster/VERSION`, dérive `public`, détecte la péremption. Aucune autre responsabilité. |
| `tests/test_version.py` | **Créé.** Couvre le service et son exposition. |
| `comroster/__init__.py` | Instancie le service, l'injecte aux gabarits, l'ajoute à `/healthz`, journalise le démarrage. |
| `comroster/services/health.py` | Ajoute la version au snapshot lu par l'onglet Santé. |
| `templates/display.html` | Version publique au pied de page. |
| `static/js/health.js` | Rend la carte d'identité du logiciel. |
| `static/js/journal.js` | Libellé de l'événement `startup`. |
| `deploy/setup-pi.sh` | Grave le fichier au déploiement. Seul endroit qui appelle git. |
| `deploy/kiosk-run.sh` | Lit le fichier, passe le label au splash en paramètre d'URL. |
| `deploy/boot-splash.html` | Affiche le label reçu. |
| `.gitignore` | Ignore `comroster/VERSION` (artefact généré). |
| `README.md`, `deploy/raspberry-pi.md` | Discipline de pose des tags. |

---

## Tâche 1 : le service de version — lecture et version publique

**Fichiers :**
- Créer : `comroster/services/version.py`
- Créer : `tests/test_version.py`

**Interfaces :**
- Consomme : rien.
- Produit : `class Version(package_dir=…, repo_dir=None)` avec les attributs `known: bool`, `label: str`, `commit: str`, `date: str`, `public: str`, et la méthode `snapshot() -> dict`. L'attribut `stale: bool` est ajouté par la tâche 2. La tâche 3 instancie `Version()` sans argument.

- [ ] **Étape 1 : écrire les tests qui échouent**

Créer `tests/test_version.py` :

```python
"""Version du logiciel : lecture du fichier gravé, et ce qu'on en montre au client."""
from comroster.services.version import Version


def _graver(tmp_path, ligne):
    (tmp_path / "VERSION").write_text(ligne, encoding="utf-8")
    return Version(str(tmp_path))


def test_lecture_nominale(tmp_path):
    v = _graver(tmp_path, "v1.4.0+7 9f3c1a2 2026-07-29\n")
    assert v.known is True
    assert v.label == "v1.4.0+7"
    assert v.commit == "9f3c1a2"
    assert v.date == "2026-07-29"


def test_fichier_absent_donne_une_version_inconnue(tmp_path):
    """Cas du poste de développement, et de toute installation qui n'est pas passée par
    deploy/setup-pi.sh. Ne doit rien casser : une page ne disparaît pas faute de numéro."""
    v = Version(str(tmp_path))
    assert v.known is False
    assert v.label == "" and v.commit == "" and v.date == ""
    assert v.public == ""


def test_fichier_vide_ou_tronque_donne_une_version_inconnue(tmp_path):
    """Mieux vaut « inconnue » qu'un numéro partiel : un demi-numéro se lit comme un
    numéro entier et induit en erreur au téléphone."""
    for ligne in ("", "\n", "v1.4.0+7\n", "v1.4.0+7 9f3c1a2\n"):
        assert _graver(tmp_path, ligne).known is False


def test_champs_surnumeraires_refuses(tmp_path):
    """Un quatrième champ signale un format qu'on ne comprend pas : on ne devine pas."""
    assert _graver(tmp_path, "v1.4.0 9f3c1a2 2026-07-29 extra\n").known is False


def test_version_publique_tronquee_a_majeur_mineur(tmp_path):
    """Ce que voit le CLIENT au pied de l'écran : moins précis, jamais faux."""
    assert _graver(tmp_path, "v1.4.0+7 9f3c1a2 2026-07-29\n").public == "v1.4"
    assert _graver(tmp_path, "v1.4.0 9f3c1a2 2026-07-29\n").public == "v1.4"
    assert _graver(tmp_path, "v2.0.0 9f3c1a2 2026-07-29\n").public == "v2.0"


def test_sans_tag_il_n_y_a_pas_de_version_publique(tmp_path):
    """`git describe --always` retombe sur l'identifiant du commit quand aucun tag
    n'existe. Afficher « 9f3c1a2 » à un client ne veut rien dire pour lui : le pied de
    l'écran doit alors rester exactement ce qu'il était."""
    v = _graver(tmp_path, "9f3c1a2 9f3c1a2 2026-07-29\n")
    assert v.known is True          # l'admin, elle, a bien une information exploitable
    assert v.label == "9f3c1a2"
    assert v.public == ""


def test_snapshot_porte_toutes_les_cles_attendues(tmp_path):
    """L'onglet Santé lit ce dictionnaire tel quel : une clé manquante y devient un
    « undefined » silencieux à l'écran."""
    snap = _graver(tmp_path, "v1.4.0+7 9f3c1a2 2026-07-29\n").snapshot()
    assert set(snap) == {"known", "label", "commit", "date", "public", "stale"}
```

- [ ] **Étape 2 : lancer les tests pour vérifier qu'ils échouent**

Lancer : `python -m pytest tests/test_version.py -v`
Attendu : ÉCHEC avec `ModuleNotFoundError: No module named 'comroster.services.version'`

- [ ] **Étape 3 : écrire l'implémentation minimale**

Créer `comroster/services/version.py` :

```python
"""Version du logiciel : quel code, exactement, tourne sur ce boîtier.

Le numéro n'est jamais saisi — il est GRAVÉ au déploiement par deploy/setup-pi.sh, qui
interroge git. Un numéro saisi à la main mentirait dès le premier `git pull`
intermédiaire, et sur une appliance un numéro faux est pire que pas de numéro : il
donne une réponse fausse à la seule question qui compte au téléphone.

Fichier `comroster/VERSION`, une ligne, trois champs séparés par une espace :

    v1.4.0+7 9f3c1a2 2026-07-29
    │        │       └── date du commit (YYYY-MM-DD)
    │        └────────── commit court
    └─────────────────── label, DÉJÀ normalisé par le shell

Le label est normalisé une seule fois, côté shell. Si Python le renormalisait de son
côté, l'écran de démarrage (qui lit le même fichier, en shell) et l'onglet Santé
pourraient afficher deux chaînes différentes pour un même code — exactement le genre de
divergence que ce fichier unique existe pour empêcher.

Politique appliance fail-safe, comme services/lifetime.py : fichier absent, vide ou
mal formé ⇒ `known = False` et champs vides, avec un avertissement journalisé. Jamais
d'exception : aucune page ne doit disparaître faute d'un numéro de version.
"""
import logging
import os
import re

log = logging.getLogger(__name__)

#: Le paquet `comroster/` — c'est là que le déploiement grave VERSION. Ce module vit dans
#: `comroster/services/`, d'où les deux remontées.
PAQUET = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: Un label public commence par « v » suivi de majeur.mineur. Tout le reste (identifiant
#: de commit nu, préfixe inhabituel) n'a pas de version publique.
_MAJEUR_MINEUR = re.compile(r"^v(\d+)\.(\d+)")


def _version_publique(label):
    """Le label tronqué à majeur.mineur, pour le seul écran que le client regarde.

    « v1.4 » là où l'administration dit « v1.4.0+7 ». Être MOINS PRÉCIS n'est pas mentir ;
    afficher un numéro inventé le serait. Sans tag, on ne renvoie rien plutôt qu'un
    identifiant de commit, qui ne signifie rien pour un client.
    """
    trouve = _MAJEUR_MINEUR.match(label or "")
    return f"v{trouve.group(1)}.{trouve.group(2)}" if trouve else ""


class Version:
    def __init__(self, package_dir=PAQUET, repo_dir=None):
        self.path = os.path.join(package_dir, "VERSION")
        #: La racine du dépôt, où vit `.git`. Séparée du paquet pour que les tests
        #: puissent les dissocier.
        self.repo_dir = repo_dir if repo_dir is not None else os.path.dirname(package_dir)
        self.label, self.commit, self.date = self._charger()
        self.known = bool(self.label)
        self.public = _version_publique(self.label)
        self.stale = False

    def _charger(self):
        try:
            with open(self.path, encoding="utf-8") as fichier:
                champs = fichier.readline().split()
        except OSError as exc:
            # Le cas normal en développement : pas un incident, d'où `info`.
            log.info("Aucun fichier de version (%s) — version inconnue", exc)
            return "", "", ""
        if len(champs) != 3:
            log.warning(
                "Fichier de version mal formé (%d champ(s) au lieu de 3) — version inconnue",
                len(champs),
            )
            return "", "", ""
        return champs[0], champs[1], champs[2]

    def snapshot(self):
        """Ce que l'onglet Santé reçoit via /api/health."""
        return {
            "known": self.known,
            "label": self.label,
            "commit": self.commit,
            "date": self.date,
            "public": self.public,
            "stale": self.stale,
        }
```

- [ ] **Étape 4 : lancer les tests pour vérifier qu'ils passent**

Lancer : `python -m pytest tests/test_version.py -v`
Attendu : SUCCÈS, 7 tests passés.

- [ ] **Étape 5 : committer**

```bash
git add comroster/services/version.py tests/test_version.py
git commit -m "feat(version): service de lecture de la version gravée

Le numéro n'est jamais saisi : il est lu dans comroster/VERSION, gravé au
déploiement. Fichier absent ou mal formé donne « inconnue », jamais un
numéro partiel — un demi-numéro se lit comme un numéro entier.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Tâche 2 : la garde de fraîcheur

**Fichiers :**
- Modifier : `comroster/services/version.py`
- Modifier : `tests/test_version.py`

**Interfaces :**
- Consomme : `Version` de la tâche 1, en particulier `self.commit` et `self.repo_dir`.
- Produit : l'attribut `Version.stale: bool`, déjà présent dans `snapshot()`.

**Contexte.** Le fichier gravé a une faiblesse : un `git pull` sans relance de `setup-pi.sh` laisserait un numéro périmé affiché comme s'il était vrai. Cette tâche le détecte en comparant des **valeurs**, pas des dates. Ne jamais comparer le `mtime` de `.git/index` : `git status` réécrit l'index dès qu'un horodatage de fichier de travail a changé, sans qu'une ligne de code ait bougé — la garde crierait au loup et deviendrait ignorée.

- [ ] **Étape 1 : écrire les tests qui échouent**

Ajouter à la fin de `tests/test_version.py` :

```python
# ---------- Garde de fraîcheur ----------

SHA = "9f3c1a2b8e4d5f6a7c8b9d0e1f2a3b4c5d6e7f80"


def _depot(tmp_path, head, refs=None, packed=None):
    """Un faux dépôt : juste les fichiers que la garde sait lire, rien de plus.

    On ne lance jamais git — ni ici, ni en production. Sur un boîtier, l'exécutable peut
    très bien ne pas être installé.
    """
    paquet = tmp_path / "comroster"
    paquet.mkdir()
    (paquet / "VERSION").write_text("v1.4.0 9f3c1a2 2026-07-29\n", encoding="utf-8")
    git = tmp_path / ".git"
    git.mkdir()
    (git / "HEAD").write_text(head, encoding="utf-8")
    for nom, sha in (refs or {}).items():
        cible = git / nom
        cible.parent.mkdir(parents=True, exist_ok=True)
        cible.write_text(sha + "\n", encoding="utf-8")
    if packed is not None:
        (git / "packed-refs").write_text(packed, encoding="utf-8")
    return Version(str(paquet), repo_dir=str(tmp_path))


def test_code_a_jour_n_est_pas_signale(tmp_path):
    v = _depot(tmp_path, "ref: refs/heads/main\n", refs={"refs/heads/main": SHA})
    assert v.stale is False


def test_code_modifie_depuis_le_deploiement_est_signale(tmp_path):
    """Le cas qu'on veut attraper : `git pull` sans relancer deploy/setup-pi.sh."""
    autre = "0000000aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    v = _depot(tmp_path, "ref: refs/heads/main\n", refs={"refs/heads/main": autre})
    assert v.stale is True


def test_tete_detachee_resolue(tmp_path):
    """`.git/HEAD` porte alors le SHA directement, sans passer par une référence."""
    assert _depot(tmp_path, SHA + "\n").stale is False


def test_reference_compactee_resolue(tmp_path):
    """`git gc` déplace les références dans packed-refs et supprime le fichier
    refs/heads/main. Sans ce repli, la garde s'éteindrait en silence sur tout dépôt
    un peu ancien — une garde éteinte sans le dire est pire qu'une garde absente."""
    v = _depot(tmp_path, "ref: refs/heads/main\n",
               packed=f"# pack-refs with: peeled fully-peeled sorted \n{SHA} refs/heads/main\n")
    assert v.stale is False


def test_sans_depot_git_aucun_soupcon(tmp_path):
    """Cas d'un boîtier installé par copie d'image : on ne peut pas savoir, donc on
    n'invente pas un doute."""
    paquet = tmp_path / "comroster"
    paquet.mkdir()
    (paquet / "VERSION").write_text("v1.4.0 9f3c1a2 2026-07-29\n", encoding="utf-8")
    assert Version(str(paquet), repo_dir=str(tmp_path)).stale is False


def test_git_en_fichier_worktree_aucun_soupcon(tmp_path):
    """Dans un worktree git, `.git` est un FICHIER qui pointe ailleurs. Configuration
    inexistante sur un boîtier, courante sur un poste de développement : elle ne doit
    pas produire d'erreur."""
    paquet = tmp_path / "comroster"
    paquet.mkdir()
    (paquet / "VERSION").write_text("v1.4.0 9f3c1a2 2026-07-29\n", encoding="utf-8")
    (tmp_path / ".git").write_text("gitdir: /ailleurs/.git/worktrees/x\n", encoding="utf-8")
    assert Version(str(paquet), repo_dir=str(tmp_path)).stale is False


def test_version_inconnue_n_est_jamais_perimee(tmp_path):
    """Sans commit gravé, il n'y a rien à comparer : « inconnue » se suffit, l'affubler
    d'un « incertaine » n'ajouterait que du bruit."""
    paquet = tmp_path / "comroster"
    paquet.mkdir()
    git = tmp_path / ".git"
    git.mkdir()
    (git / "HEAD").write_text(SHA + "\n", encoding="utf-8")
    v = Version(str(paquet), repo_dir=str(tmp_path))
    assert v.known is False and v.stale is False
```

- [ ] **Étape 2 : lancer les tests pour vérifier qu'ils échouent**

Lancer : `python -m pytest tests/test_version.py -k "perimee or tete or reference or depot or worktree or modifie or jour" -v`
Attendu : ÉCHEC — `test_code_modifie_depuis_le_deploiement_est_signale` échoue avec `assert False is True` (`stale` vaut toujours `False`, valeur posée en dur par la tâche 1).

- [ ] **Étape 3 : écrire l'implémentation**

Dans `comroster/services/version.py`, remplacer la ligne `self.stale = False` par :

```python
        self.stale = self._est_perimee()
```

Puis ajouter ces méthodes à la classe `Version`, avant `snapshot()` :

```python
    # ---------- garde de fraîcheur ----------
    def _est_perimee(self):
        """Le code déployé correspond-il encore à ce que dit le dépôt ?

        Comparaison de VALEURS, pas de dates. Comparer le `mtime` de `.git/index` serait
        plus court et FAUX : `git status` réécrit l'index dès qu'un horodatage de fichier
        de travail a changé, sans qu'une ligne de code ait bougé. La garde crierait au
        loup, et une garde qui crie au loup finit ignorée.

        Aucune commande git n'est lancée : que de la lecture de fichiers. Sur un boîtier,
        l'exécutable git peut ne pas être installé du tout.

        Tout ce qu'on ne sait pas lire ⇒ False. On n'invente pas un doute.
        """
        if not self.commit:
            return False
        tete = self._sha_de_la_tete()
        return bool(tete) and not tete.startswith(self.commit)

    def _sha_de_la_tete(self):
        git = os.path.join(self.repo_dir, ".git")
        # Un `.git` FICHIER (worktree git) pointe ailleurs : on renonce sans erreur.
        if not os.path.isdir(git):
            return ""
        tete = _premiere_ligne(os.path.join(git, "HEAD"))
        if not tete.startswith("ref:"):
            return tete                     # tête détachée : le SHA est écrit directement
        reference = tete[len("ref:"):].strip()
        return (_premiere_ligne(os.path.join(git, reference))
                or _reference_compactee(git, reference))


def _premiere_ligne(path):
    try:
        with open(path, encoding="utf-8") as fichier:
            return fichier.readline().strip()
    except OSError:
        return ""


def _reference_compactee(git_dir, reference):
    """`git gc` déplace les références dans `.git/packed-refs` et supprime les fichiers
    individuels. Sans ce repli, la garde s'éteindrait silencieusement sur tout dépôt
    ayant subi un ramasse-miettes."""
    try:
        with open(os.path.join(git_dir, "packed-refs"), encoding="utf-8") as fichier:
            for ligne in fichier:
                morceaux = ligne.split()
                if len(morceaux) == 2 and morceaux[1] == reference:
                    return morceaux[0]
    except OSError:
        pass
    return ""
```

- [ ] **Étape 4 : lancer les tests pour vérifier qu'ils passent**

Lancer : `python -m pytest tests/test_version.py -v`
Attendu : SUCCÈS, 14 tests passés.

- [ ] **Étape 5 : committer**

```bash
git add comroster/services/version.py tests/test_version.py
git commit -m "feat(version): détecter un code modifié depuis le déploiement

Compare le commit gravé au SHA lu dans .git, par lecture de fichier — jamais
par mtime : git status réécrit l'index sans qu'une ligne de code ait bougé,
et une garde qui crie au loup finit ignorée.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Tâche 3 : câblage Flask — extension, `/healthz`, snapshot santé, gabarits

**Fichiers :**
- Modifier : `comroster/__init__.py`
- Modifier : `comroster/services/health.py:160` (bloc final du dictionnaire `snapshot`)
- Modifier : `tests/test_version.py`

**Interfaces :**
- Consomme : `Version` des tâches 1 et 2.
- Produit : `app.extensions["version"]` ; la variable de gabarit `appversion` ; la clé `version` dans `/healthz` et dans `health.snapshot(app)`.

**Pourquoi `appversion` et non `version` :** le modèle de données porte déjà un champ `version` (`services/model.py:76`, le numéro de révision d'une publication). Deux `version` différents dans le même espace de noms de gabarit est une confusion garantie à la relecture.

- [ ] **Étape 1 : écrire les tests qui échouent**

Ajouter à la fin de `tests/test_version.py` :

```python
# ---------- Câblage de l'application ----------

def test_healthz_porte_la_version(client):
    """C'est le point qu'on interroge à distance, sans ouvrir de session : « quel code
    tourne sur cette machine ? » doit avoir une réponse en un curl."""
    corps = client.get("/healthz").get_json()
    assert corps["status"] == "ok"
    assert "version" in corps          # None hors déploiement : la clé, elle, est due


def test_la_sante_expose_la_version(app):
    from comroster.services import health
    snap = health.snapshot(app)
    assert "version" in snap
    assert set(snap["version"]) == {"known", "label", "commit", "date", "public", "stale"}


def test_la_version_est_injectee_dans_les_gabarits(app):
    """Le pied de /display la lit sous le nom `appversion`. « version » tout court est
    déjà pris par le numéro de révision d'une publication (services/model.py)."""
    from flask import render_template_string
    with app.test_request_context("/"):
        rendu = render_template_string("{{ appversion.known }}|{{ appversion.public }}")
    assert rendu.startswith(("True|", "False|"))
```

- [ ] **Étape 2 : lancer les tests pour vérifier qu'ils échouent**

Lancer : `python -m pytest tests/test_version.py -k "healthz or sante or gabarits" -v`
Attendu : ÉCHEC — `KeyError: 'version'` sur `test_healthz_porte_la_version`.

- [ ] **Étape 3 : écrire l'implémentation**

Dans `comroster/__init__.py`, ajouter l'import à côté des autres services (après `from .services.storage import Storage`) :

```python
from .services.version import Version
```

Remplacer la route `/healthz` :

```python
    @app.get("/healthz")
    def healthz():
        # La version voyage avec le battement de cœur : c'est le seul point qu'on peut
        # interroger sans ouvrir de session, et « quel code tourne ici ? » est la
        # première question du dépannage. Fuite d'information assumée — LAN de régie.
        return jsonify({"status": "ok", "version": app.extensions["version"].label or None})
```

Instancier le service juste après la ligne `app.extensions["branding"] = …` :

```python
    app.extensions["version"] = Version()
```

Étendre le processeur de contexte existant :

```python
    @app.context_processor
    def _injecter_contexte_global():
        # `appversion` et non `version` : le modèle a déjà un champ `version` (le numéro
        # de révision d'une publication) et la confusion serait garantie à la relecture.
        return {
            "brand": app.extensions["branding"],
            "appversion": app.extensions["version"],
        }
```

*(La fonction s'appelait `_injecter_marque` : elle injecte désormais deux choses, d'où le nouveau nom.)*

Dans `comroster/services/health.py`, ajouter au dictionnaire retourné par `snapshot`, juste après la clé `"lifetime"` :

```python
        # Carte d'identité du logiciel. « Quel code tourne sur cette machine ? » n'avait
        # jusqu'ici de réponse qu'en SSH.
        "version": app.extensions["version"].snapshot(),
```

- [ ] **Étape 4 : lancer les tests pour vérifier qu'ils passent**

Lancer : `python -m pytest tests/test_version.py tests/test_health.py tests/test_app.py -v`
Attendu : SUCCÈS, aucun échec.

- [ ] **Étape 5 : lancer toute la suite**

Lancer : `python -m pytest -q`
Attendu : SUCCÈS. Le renommage de `_injecter_marque` et l'ajout d'une clé à `/healthz` peuvent avoir des lecteurs ailleurs — c'est ici qu'on le découvre, pas sur un boîtier.

- [ ] **Étape 6 : committer**

```bash
git add comroster/__init__.py comroster/services/health.py tests/test_version.py
git commit -m "feat(version): exposer la version à /healthz, à la santé et aux gabarits

Injectée sous le nom appversion : « version » est déjà pris par le numéro de
révision d'une publication.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Tâche 4 : graver le fichier au déploiement

**Fichiers :**
- Modifier : `deploy/setup-pi.sh` (insérer après le bloc d'installation des dépendances Python, avant la configuration des services systemd)
- Modifier : `.gitignore`
- Modifier : `tests/test_version.py`

**Interfaces :**
- Consomme : le format défini dans les contraintes globales.
- Produit : le fichier `comroster/VERSION` sur un boîtier déployé.

**Deux pièges à ne pas manquer.** `setup-pi.sh` tourne sous `set -euo pipefail` : toute commande qui échoue arrête le script, il faut donc encadrer les appels git. Et il tourne en **root** alors que le dépôt appartient à `$TARGET_USER` : depuis git 2.35.2, git refuse d'opérer sur un dépôt appartenant à un autre utilisateur (« dubious ownership »). D'où `sudo -u "$TARGET_USER"`, comme le script le fait déjà pour `pip` et `venv`.

- [ ] **Étape 1 : écrire les tests qui échouent**

Ajouter à la fin de `tests/test_version.py` :

D'abord, compléter l'**en-tête** de `tests/test_version.py` — les imports vivent en tête de fichier, sinon `ruff` lève `E402` (le dépôt est linté, cf. `deploy/lint-local.sh`) :

```python
"""Version du logiciel : lecture du fichier gravé, et ce qu'on en montre au client."""
import os
import re
import subprocess

import pytest

from comroster.services.version import Version

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
```

Puis ajouter à la fin du fichier :

```python
# ---------- Gravure au déploiement ----------

def _setup_pi():
    with open(os.path.join(RACINE, "deploy", "setup-pi.sh"), encoding="utf-8") as fichier:
        return fichier.read()


def test_le_deploiement_grave_la_version():
    """Sans cette écriture, tout le reste de la chaîne affiche « inconnue » : c'est le
    seul endroit où le numéro est produit."""
    source = _setup_pi()
    assert "comroster/VERSION" in source
    assert "describe --tags --always" in source


def test_le_deploiement_n_utilise_pas_dirty():
    """`--dirty` force un rafraîchissement de l'index, qu'une racine montée en lecture
    seule (deploy/readonly-fs.sh) refuse."""
    assert "--dirty" not in _setup_pi()


def test_le_deploiement_interroge_git_sous_l_utilisateur_cible():
    """Le script tourne en root, le dépôt appartient à l'utilisateur : sans `sudo -u`,
    git refuse le dépôt (« dubious ownership ») et la version resterait inconnue sur
    tous les boîtiers, en silence."""
    assert re.search(r'sudo -u "\$TARGET_USER" git', _setup_pi())


@pytest.mark.skipif(not os.path.isdir(os.path.join(RACINE, ".git")), reason="hors dépôt git")
def test_le_fichier_de_version_est_ignore_par_git():
    """C'est un artefact GÉNÉRÉ. Committé, il se figerait à la valeur du poste qui l'a
    produit et mentirait sur tous les autres.

    `skipif` et non un `return` muet : c'est la convention de tests/test_gitignore.py, et
    un test qui se termine sans assertion se compte comme réussi — il mentirait sur sa
    propre couverture."""
    code = subprocess.run(["git", "check-ignore", "-q", "comroster/VERSION"],
                          cwd=RACINE, check=False).returncode
    assert code == 0, "comroster/VERSION n'est pas couvert par .gitignore"
```

- [ ] **Étape 2 : lancer les tests pour vérifier qu'ils échouent**

Lancer : `python -m pytest tests/test_version.py -k "deploiement or ignore" -v`
Attendu : ÉCHEC des quatre tests.

- [ ] **Étape 3 : écrire l'implémentation**

Dans `.gitignore`, ajouter après le bloc `# Sauvegardes et temporaires…` :

```
# Version gravée au déploiement par deploy/setup-pi.sh. Artefact GÉNÉRÉ : committé, il
# se figerait à la valeur du poste qui l'a produit et mentirait sur tous les autres.
comroster/VERSION
```

Dans `deploy/setup-pi.sh`, insérer ce bloc après l'installation des dépendances Python (après la ligne `install -d -o "$TARGET_USER" ... "$DATA_DIR"`) :

```bash
# --- Version du logiciel --------------------------------------------------
# Gravée ICI, une fois, à partir de git — jamais saisie à la main : un numéro saisi
# mentirait dès le premier `git pull` intermédiaire.
#
# Le fichier a DEUX lecteurs — comroster/services/version.py et deploy/kiosk-run.sh —
# d'où une ligne de texte nu plutôt que du JSON, qui imposerait `jq` au shell.
# Le label est normalisé UNE SEULE FOIS, ici : si Python le renormalisait de son côté,
# l'écran de démarrage et l'onglet Santé pourraient afficher deux chaînes pour un même
# code.
#
# `sudo -u` est indispensable : ce script tourne en root, le dépôt appartient à
# l'utilisateur, et git refuse depuis 2.35.2 un dépôt appartenant à un autre
# (« dubious ownership »). Sans cela la version resterait inconnue partout, en silence.
echo "▶ Version du logiciel…"
VERSION_FILE="$APP_DIR/comroster/VERSION"
git_cible() { sudo -u "$TARGET_USER" git -C "$APP_DIR" "$@" 2>/dev/null; }

ver_label=""; ver_commit=""; ver_date=""
if git_cible rev-parse --git-dir >/dev/null; then
  # `--always` retombe sur l'identifiant du commit quand aucun tag n'existe.
  # `--dirty` est volontairement absent : il rafraîchit l'index, ce qu'une racine
  # montée en lecture seule refuse.
  ver_label=$(git_cible describe --tags --always | sed -E 's/-([0-9]+)-g[0-9a-f]+$/+\1/') || true
  ver_commit=$(git_cible rev-parse --short HEAD) || true
  ver_date=$(git_cible log -1 --format=%cs) || true
fi

if [ -n "$ver_label" ] && [ -n "$ver_commit" ] && [ -n "$ver_date" ]; then
  # Écriture atomique : un fichier à moitié écrit serait lu comme « mal formé ».
  printf '%s %s %s\n' "$ver_label" "$ver_commit" "$ver_date" > "$VERSION_FILE.tmp"
  mv "$VERSION_FILE.tmp" "$VERSION_FILE"
  chown "$TARGET_USER:$TARGET_USER" "$VERSION_FILE"
  echo "  $ver_label · $ver_commit · $ver_date"
else
  # On ne grave RIEN plutôt qu'un numéro faux : l'absence de fichier est un état
  # parfaitement géré en aval (« version inconnue »).
  rm -f "$VERSION_FILE.tmp"
  echo "  ⚠ git n'a pas répondu — version laissée inconnue (rien n'a été gravé)"
fi
```

- [ ] **Étape 4 : lancer les tests pour vérifier qu'ils passent**

Lancer : `python -m pytest tests/test_version.py tests/test_deploy_scripts.py tests/test_gitignore.py -v`
Attendu : SUCCÈS. `test_deploy_scripts.py` valide la syntaxe du script par `bash -n` — c'est le filet qui attrape une accolade manquante avant le terrain.

- [ ] **Étape 5 : vérifier la gravure pour de vrai**

Le test lit le script ; il ne prouve pas qu'il produit la bonne ligne. Exécuter le cœur du bloc à la main, depuis la racine du dépôt :

```bash
git describe --tags --always | sed -E 's/-([0-9]+)-g[0-9a-f]+$/+\1/'
git rev-parse --short HEAD
git log -1 --format=%cs
```

Attendu : trois valeurs non vides. Avant la pose du premier tag (tâche 9), la première commande renvoie l'identifiant du commit — c'est le comportement voulu, couvert par `test_sans_tag_il_n_y_a_pas_de_version_publique`.

- [ ] **Étape 6 : committer**

```bash
git add deploy/setup-pi.sh .gitignore tests/test_version.py
git commit -m "feat(version): graver la version au déploiement

Une ligne de texte nu, lisible par Python et par sh sans dépendance. Rien
n'est gravé si git ne répond pas : l'absence de fichier est un état géré,
un numéro faux ne l'est pas.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Tâche 5 : la version publique au pied de l'écran de régie

**Fichiers :**
- Modifier : `templates/display.html:44-47`
- Modifier : `tests/test_version.py`

**Interfaces :**
- Consomme : la variable de gabarit `appversion` (tâche 3), attribut `public`.
- Produit : rien pour les tâches suivantes.

**C'est le seul écran que le client regarde.** Version courte uniquement — jamais d'identifiant de commit, jamais de `+7`. Et si `public` est vide (aucun tag posé), le pied reste **exactement** ce qu'il est aujourd'hui : ne rien afficher vaut mieux qu'afficher ce qui ne veut rien dire pour un client.

- [ ] **Étape 1 : écrire les tests qui échouent**

Ajouter à la fin de `tests/test_version.py` :

```python
# ---------- Pied de l'écran de régie ----------

def test_le_pied_du_display_porte_la_version_publique(app, monkeypatch):
    monkeypatch.setattr(app.extensions["version"], "public", "v1.4")
    html = app.test_client().get("/display").get_data(as_text=True)
    assert "v1.4" in html
    assert "9f3c1a2" not in html         # jamais de commit devant un client


def test_sans_version_publique_le_pied_est_inchange(app, monkeypatch):
    """Aucun tag posé : le pied doit retrouver mot pour mot ce qu'il était avant ce lot.
    Un séparateur orphelin (« Nathan Hurstel · ») trahirait une valeur manquante."""
    monkeypatch.setattr(app.extensions["version"], "public", "")
    html = app.test_client().get("/display").get_data(as_text=True)
    assert "COMROSTER par Nathan Hurstel" in html
    assert "Nathan Hurstel ·" not in html
```

- [ ] **Étape 2 : lancer les tests pour vérifier qu'ils échouent**

Lancer : `python -m pytest tests/test_version.py -k "pied" -v`
Attendu : ÉCHEC de `test_le_pied_du_display_porte_la_version_publique` — `"v1.4" not in html`.

- [ ] **Étape 3 : écrire l'implémentation**

Dans `templates/display.html`, remplacer la ligne 45 :

```html
    <span class="created-by">{% if brand.active %}Propulsé par ComRoster{% if appversion.public %} {{ appversion.public }}{% endif %}{% else %}COMROSTER par Nathan Hurstel{% if appversion.public %} · {{ appversion.public }}{% endif %}{% endif %}</span>
```

Le séparateur diffère volontairement : un simple espace derrière « ComRoster » (le numéro qualifie le produit), un point médian derrière le nom de l'auteur (deux informations distinctes). Les deux conditions sont internes aux branches pour qu'aucun séparateur ne survive à une version absente.

- [ ] **Étape 4 : lancer les tests pour vérifier qu'ils passent**

Lancer : `python -m pytest tests/test_version.py tests/test_ui.py tests/test_branding.py -v`
Attendu : SUCCÈS. `test_branding.py` couvre les deux états du pied (marque cliente active ou non) : il confirme qu'aucun des deux n'a été cassé.

- [ ] **Étape 5 : vérifier le rendu réel**

Lancer `./run-dev.sh`, ouvrir `http://127.0.0.1:8080/display`, **regarder le pied de page**.
Attendu : sans tag posé, le pied est identique à avant. Pour voir le cas nominal, graver un fichier de test puis relancer le serveur :

```bash
printf 'v1.4.0+7 9f3c1a2 2026-07-29\n' > comroster/VERSION
```

Attendu à l'écran : `COMROSTER par Nathan Hurstel · v1.4`. Supprimer ensuite le fichier (`rm comroster/VERSION`) pour ne pas fausser les tâches suivantes.

- [ ] **Étape 6 : committer**

```bash
git add templates/display.html tests/test_version.py
git commit -m "feat(version): version publique au pied de l'écran de régie

v1.4 et non v1.4.0+7 : moins précis n'est pas mentir. Sans tag, le pied
reste mot pour mot ce qu'il était — pas de séparateur orphelin.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Tâche 6 : la version sur l'écran de démarrage

**Fichiers :**
- Modifier : `deploy/kiosk-run.sh`
- Modifier : `deploy/boot-splash.html`
- Modifier : `tests/test_version.py`

**Interfaces :**
- Consomme : le fichier `comroster/VERSION` (tâche 4).
- Produit : rien pour les tâches suivantes.

**Le piège du `+`.** Dans une chaîne de requête, `+` est décodé comme une **espace** par `URLSearchParams`. Passer `v=v1.4.0+7` tel quel afficherait `v1.4.0 7`. Le shell doit encoder `+` en `%2B` — avec `sed`, pas avec une substitution bash : `kiosk-run.sh` est du sh POSIX.

**Ne pas toucher au shebang ni au `set -eu`** en tête de `kiosk-run.sh`. Sous `set -u`, une variable non initialisée arrête le script : `ver` doit être initialisée à vide avant tout.

- [ ] **Étape 1 : écrire les tests qui échouent**

Ajouter à la fin de `tests/test_version.py` :

```python
# ---------- Écran de démarrage ----------

def _fichier_deploy(nom):
    with open(os.path.join(RACINE, "deploy", nom), encoding="utf-8") as fichier:
        return fichier.read()


def test_le_kiosk_transmet_la_version_au_splash():
    """Le splash s'ouvre en file:// AVANT que le serveur réponde : il ne peut rien
    demander à personne. La version doit lui arriver par l'URL, comme `next` et
    `health`."""
    source = _fichier_deploy("kiosk-run.sh")
    assert "comroster/VERSION" in source
    assert "&v=$" in source


def test_le_kiosk_encode_le_plus_dans_l_url():
    """Dans une chaîne de requête, « + » se décode en ESPACE : sans encodage,
    « v1.4.0+7 » s'afficherait « v1.4.0 7 » à l'écran de démarrage."""
    assert "%2B" in _fichier_deploy("kiosk-run.sh")


def test_le_splash_affiche_la_version_sans_injection():
    """Le paramètre d'URL est une entrée non fiable : textContent, jamais innerHTML."""
    source = _fichier_deploy("boot-splash.html")
    assert 'params.get("v")' in source
    assert 'getElementById("version").textContent' in source
```

- [ ] **Étape 2 : lancer les tests pour vérifier qu'ils échouent**

Lancer : `python -m pytest tests/test_version.py -k "kiosk or splash" -v`
Attendu : ÉCHEC des trois tests.

- [ ] **Étape 3 : écrire l'implémentation — le lanceur**

Dans `deploy/kiosk-run.sh`, insérer juste avant le bloc `if [ "$ROLE" = "viewer" ]` :

```sh
# Version gravée au déploiement. Le splash s'ouvre en file:// AVANT que le serveur
# réponde : il ne peut rien demander à personne, la version doit lui arriver par l'URL —
# comme `next` et `health`.
#
# `+` DOIT être encodé : dans une chaîne de requête il se décode en espace, et
# « v1.4.0+7 » s'afficherait « v1.4.0 7 ». sed et non substitution bash : on est en sh.
ver=""
VERSION_FILE="$SCRIPT_DIR/../comroster/VERSION"
if [ -r "$VERSION_FILE" ]; then
  read -r ver _ < "$VERSION_FILE" || ver=""
  ver=$(printf '%s' "$ver" | sed 's/+/%2B/g')
fi
```

Puis, dans la branche `else` (rôle autonome), remplacer la construction de `URL` :

```sh
  URL="file://$SCRIPT_DIR/boot-splash.html?next=$TARGET&health=$HEALTH&v=$ver"
```

- [ ] **Étape 4 : écrire l'implémentation — le splash**

Dans `deploy/boot-splash.html`, remplacer la ligne `<div id="marque">ComRoster</div>` par :

```html
  <div id="identite">
    <div id="marque">ComRoster</div>
    <div id="version"></div>
  </div>
```

Ajouter dans le `<style>`, après le bloc `#marque` :

```css
    /* Marque et version forment UN bloc : sans ce conteneur, le `gap` du body les
       séparerait autant que les autres éléments et la version flotterait. */
    #identite {
      display: flex; flex-direction: column;
      align-items: center; gap: 0.9vmin;
    }

    #version {
      font-size: 1.05vmin; font-weight: 400;
      letter-spacing: 0.12em;
      color: var(--muted);
      font-variant-numeric: tabular-nums;
    }
```

Ajouter dans le `<script>`, juste après la ligne `const health = params.get("health") || …` :

```js
    // textContent et non innerHTML : un paramètre d'URL est une entrée non fiable.
    const version = params.get("v") || "";
    if (version) document.getElementById("version").textContent = version;
```

- [ ] **Étape 5 : lancer les tests pour vérifier qu'ils passent**

Lancer : `python -m pytest tests/test_version.py tests/test_deploy_scripts.py -v`
Attendu : SUCCÈS. `bash -n` sur `kiosk-run.sh` confirme que le script reste syntaxiquement valide.

- [ ] **Étape 6 : vérifier le rendu réel du splash**

Ouvrir directement le fichier dans un navigateur, avec le paramètre encodé :

```bash
open "file://$PWD/deploy/boot-splash.html?v=v1.4.0%2B7&health=http://127.0.0.1:9/x"
```

Attendu : « ComRoster » avec `v1.4.0+7` (avec un **plus**, pas une espace) juste en dessous, en gris discret. Le voyant reste en veille puis passe au rouge — normal, l'URL de santé pointe volontairement dans le vide.

Vérifier aussi le cas sans version :

```bash
open "file://$PWD/deploy/boot-splash.html?health=http://127.0.0.1:9/x"
```

Attendu : aucune ligne vide sous « ComRoster », l'espacement est identique à avant ce lot.

- [ ] **Étape 7 : committer**

```bash
git add deploy/kiosk-run.sh deploy/boot-splash.html tests/test_version.py
git commit -m "feat(version): version sur l'écran de démarrage

Passée par l'URL comme next et health : le splash s'ouvre en file:// avant
que le serveur réponde. Le « + » est encodé en %2B, sans quoi la chaîne de
requête le décoderait en espace.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Tâche 7 : journaliser la version à chaque démarrage

**Fichiers :**
- Modifier : `comroster/__init__.py`
- Modifier : `static/js/journal.js:7-20` (dictionnaire `EVENT_LABELS`)
- Modifier : `tests/test_version.py`

**Interfaces :**
- Consomme : `app.extensions["version"]` et `app.extensions["journal"]` (tâche 3).
- Produit : l'événement `startup` dans le journal.

**Le vrai gain de cette tâche :** le journal devient l'historique des mises à jour du boîtier. « Depuis quand tourne-t-il sur cette version, et qu'y avait-il avant ? » n'a aucune autre source.

- [ ] **Étape 1 : écrire les tests qui échouent**

Ajouter à la fin de `tests/test_version.py` :

```python
# ---------- Journal ----------

def test_le_demarrage_est_journalise_avec_la_version(app):
    """Le journal devient l'historique des mises à jour du boîtier : « depuis quand
    tourne-t-il sur cette version ? » n'a aucune autre source."""
    evenements = app.extensions["journal"].entries()
    demarrages = [e for e in evenements if e["event"] == "startup"]
    assert len(demarrages) == 1
    assert demarrages[0]["detail"]          # jamais vide : « version inconnue » à défaut


def test_le_libelle_du_demarrage_existe_cote_navigateur():
    """Sans entrée dans EVENT_LABELS, la page Journal afficherait la clé technique
    « startup » à l'utilisateur."""
    with open(os.path.join(RACINE, "static", "js", "journal.js"), encoding="utf-8") as f:
        assert "startup:" in f.read()
```

- [ ] **Étape 2 : lancer les tests pour vérifier qu'ils échouent**

Lancer : `python -m pytest tests/test_version.py -k "demarrage or libelle" -v`
Attendu : ÉCHEC — `assert 0 == 1` sur le premier test.

- [ ] **Étape 3 : écrire l'implémentation**

Dans `comroster/__init__.py`, juste après `app.extensions["lifetime"].register_start()` :

```python
    # Le journal tient déjà les redémarrages ; y inscrire la version en fait
    # l'historique des MISES À JOUR du boîtier — « depuis quand tourne-t-il là-dessus,
    # et qu'y avait-il avant ? » n'a aucune autre source.
    app.extensions["journal"].record(
        "startup", app.extensions["version"].label or "version inconnue"
    )
```

Dans `static/js/journal.js`, ajouter au dictionnaire `EVENT_LABELS`, en première position (l'ordre du dictionnaire suit le cycle de vie) :

```js
    startup: "Démarrage de l'application",
```

- [ ] **Étape 4 : lancer les tests pour vérifier qu'ils passent**

Lancer : `python -m pytest tests/test_version.py tests/test_journal.py -v`
Attendu : SUCCÈS. Les tests de journal existants lisent `entries[0]`, le plus récent : un `startup` écrit au démarrage est le plus ancien et ne les déplace pas.

- [ ] **Étape 5 : lancer toute la suite**

Lancer : `python -m pytest -q`
Attendu : SUCCÈS. Un événement écrit à **chaque** création d'application touche toutes les fixtures : c'est ici qu'un effet de bord se voit.

- [ ] **Étape 6 : vérifier le rendu réel**

Lancer `./run-dev.sh`, ouvrir `http://127.0.0.1:8080/admin/journal`.
Attendu : une ligne « Démarrage de l'application » — libellé en français, pas la clé `startup` — avec la version en détail (ou « version inconnue » tant qu'aucun fichier n'est gravé).

- [ ] **Étape 7 : committer**

```bash
git add comroster/__init__.py static/js/journal.js tests/test_version.py
git commit -m "feat(version): journaliser la version à chaque démarrage

Le journal devient l'historique des mises à jour du boîtier.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Tâche 8 : la carte d'identité dans l'onglet Santé

**Fichiers :**
- Modifier : `static/js/health.js:139-144` (insérer avant le bloc « temps de fonctionnement »)
- Modifier : `tests/test_version.py`

**Interfaces :**
- Consomme : la clé `version` de `/api/health` (tâche 3).
- Produit : rien pour les tâches suivantes.

**C'est la surface de support : tout y est.** Label complet, commit, date, et la mention d'incertitude si le code du dépôt a bougé depuis le déploiement. C'est le seul endroit où `stale` est visible.

- [ ] **Étape 1 : écrire le test qui échoue**

Ajouter à la fin de `tests/test_version.py` :

```python
# ---------- Onglet Santé ----------

def test_la_sante_rend_la_carte_d_identite():
    """`health.js` est une IIFE non exportable : on le lit comme du texte, à la manière
    de tests/test_js_constants.py. C'est peu, mais ça attrape la clé mal orthographiée
    qui produirait un « undefined » à l'écran."""
    with open(os.path.join(RACINE, "static", "js", "health.js"), encoding="utf-8") as f:
        source = f.read()
    assert "d.version" in source
    assert "version du logiciel" in source
    assert "ver.stale" in source
```

- [ ] **Étape 2 : lancer le test pour vérifier qu'il échoue**

Lancer : `python -m pytest tests/test_version.py -k "carte" -v`
Attendu : ÉCHEC — `assert 'd.version' in source`.

- [ ] **Étape 3 : écrire l'implémentation**

Dans `static/js/health.js`, insérer juste **avant** le commentaire `/* Temps : trois horizons distincts…` (ligne 139) :

```js
    /* Carte d'identité du logiciel. Elle précède les durées : « quel code tourne ici ? »
       vient avant « depuis combien de temps ». C'est le SEUL endroit qui montre le
       commit et l'éventuelle péremption — le pied de l'écran de régie, lui, est vu par
       le client. */
    const ver = d.version || {};
    facts.push({ heading: "version du logiciel" });
    if (ver.known) {
      facts.push({
        label: "version",
        value: ver.label,
        tone: ver.stale ? "warn" : "",
        hint: ver.stale
          ? `${ver.commit} · ${ver.date} — incertaine : le dépôt a changé depuis le déploiement`
          : `${ver.commit} · ${ver.date}`,
      });
    } else {
      facts.push({
        label: "version", value: "inconnue",
        hint: "aucun fichier de version — ce boîtier n'a pas été déployé par deploy/setup-pi.sh",
      });
    }

```

- [ ] **Étape 4 : lancer les tests pour vérifier qu'ils passent**

Lancer : `python -m pytest tests/test_version.py -v`
Attendu : SUCCÈS, l'ensemble du fichier passe.

- [ ] **Étape 5 : vérifier le rendu réel — les trois états**

Lancer `./run-dev.sh` et ouvrir `http://127.0.0.1:8080/admin/health` après chaque manipulation (le service relit le fichier au démarrage : **redémarrer entre chaque**).

1. **Version inconnue** — `rm -f comroster/VERSION`
   Attendu : intertitre « version du logiciel », ligne « version — inconnue », légende expliquant l'absence de déploiement.
2. **Version à jour** — graver le vrai commit :
   ```bash
   printf 'v1.4.0+7 %s %s\n' "$(git rev-parse --short HEAD)" "$(git log -1 --format=%cs)" > comroster/VERSION
   ```
   Attendu : « version — v1.4.0+7 », légende `<commit> · <date>`, **sans** mention d'incertitude.
3. **Version périmée** — graver un commit qui n'est pas la tête :
   ```bash
   printf 'v1.3.0 0000000 2026-01-01\n' > comroster/VERSION
   ```
   Attendu : « version — v1.3.0 » en teinte d'avertissement, légende terminée par « incertaine : le dépôt a changé depuis le déploiement ».

Puis nettoyer : `rm -f comroster/VERSION`.

C'est la vérification qui compte. Les tests ci-dessus lisent du texte source : ils ne prouvent pas qu'un pixel s'affiche.

- [ ] **Étape 6 : committer**

```bash
git add static/js/health.js tests/test_version.py
git commit -m "feat(version): carte d'identité du logiciel dans l'onglet Santé

Label, commit, date, et la mention d'incertitude quand le dépôt a bougé
depuis le déploiement. Seul endroit où stale est visible.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Tâche 9 : premier tag et documentation de la discipline

**Fichiers :**
- Modifier : `README.md` (section voisine de la ligne 85, qui renvoie au guide de déploiement)
- Modifier : `deploy/raspberry-pi.md:126` (section « Mise à jour »)
- Modifier : `tasks/lessons.md`
- Poser le tag `v1.0.0`

**Interfaces :**
- Consomme : tout ce qui précède.
- Produit : le premier tag, sans lequel toute la chaîne affiche un identifiant de commit au lieu d'un numéro.

- [ ] **Étape 1 : documenter la discipline**

Ajouter dans `deploy/raspberry-pi.md`, dans la section « Mise à jour », juste après le bloc `git pull` :

```markdown
> **Poser le tag AVANT de déployer.** La version affichée est dérivée de `git describe` :
> déployer un commit non taggé fait apparaître `v1.4.0+7` au lieu de `v1.4.0`, sur les
> trois écrans. Le numéro reste exact — il dit simplement « sept commits après le tag ».
>
> ```bash
> git tag -a v1.4.0 -m "Ce que cette version apporte"
> git push origin v1.4.0
> ```
>
> Le message du tag annoté tient lieu de journal des versions : il n'y a pas de
> `CHANGELOG.md`, et il ne doit pas y en avoir — ce serait un deuxième endroit à tenir à
> jour, donc un deuxième endroit qui peut mentir.
>
> Relancer `sudo deploy/setup-pi.sh` après **chaque** `git pull` : c'est lui qui grave
> `comroster/VERSION`. Sans cela l'onglet Santé signale « incertaine ».
```

Ajouter dans `README.md`, près de la section qui renvoie au guide de déploiement :

```markdown
### Versions

Le numéro affiché (onglet Santé, pied de l'écran de régie, écran de démarrage) n'est
jamais saisi : `deploy/setup-pi.sh` le dérive de `git describe` et le grave dans
`comroster/VERSION`, fichier généré et non suivi par git.

- **MAJEUR** — la mise à jour exige une action humaine ; concrètement, quand
  `backup.VERSION` change et qu'une archive ancienne ne se restaure plus.
- **MINEUR** — une fonction visible en plus.
- **CORRECTIF** — une correction, rien de neuf.

L'onglet Santé affiche le détail complet (`v1.4.0+7 · 9f3c1a2 · 2026-07-29`) ; l'écran de
régie, vu par le client, n'affiche que `v1.4`.
```

- [ ] **Étape 2 : lancer toute la suite une dernière fois**

Lancer : `python -m pytest -q && npx vitest run`
Attendu : SUCCÈS des deux côtés.

- [ ] **Étape 3 : committer la documentation**

```bash
git add README.md deploy/raspberry-pi.md
git commit -m "docs: discipline de version — poser le tag avant de déployer

Le message du tag annoté tient lieu de journal des versions : pas de
CHANGELOG.md, qui serait un deuxième endroit à tenir à jour.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

- [ ] **Étape 4 : poser le premier tag**

Le dépôt n'a aucun tag. Sans lui, `git describe --always` retombe sur l'identifiant du commit et aucun écran n'affiche de version publique.

```bash
git tag -a v1.0.0 -m "Première version numérotée.

Le produit est livré et en service : affectations, publication en direct sur
l'écran de régie, feuille imprimable, marque cliente, antenne Bolero, santé et
journal du boîtier. Ce tag fige le point de départ du versionnage."
git tag -n99 v1.0.0
```

Attendu : le tag et son message s'affichent.

- [ ] **Étape 5 : vérifier la chaîne complète, de bout en bout**

```bash
git describe --tags --always | sed -E 's/-([0-9]+)-g[0-9a-f]+$/+\1/'
```

Attendu : `v1.0.0` si le tag est sur la tête, sinon `v1.0.0+N`.

Graver puis relancer le serveur :

```bash
printf '%s %s %s\n' \
  "$(git describe --tags --always | sed -E 's/-([0-9]+)-g[0-9a-f]+$/+\1/')" \
  "$(git rev-parse --short HEAD)" "$(git log -1 --format=%cs)" > comroster/VERSION
./run-dev.sh
```

Vérifier les quatre surfaces :

1. `curl -s http://127.0.0.1:8080/healthz` → contient `"version":"v1.0.0…"`
2. `http://127.0.0.1:8080/admin/health` → « version du logiciel », label complet, **sans** mention d'incertitude
3. `http://127.0.0.1:8080/display` → pied de page terminé par `v1.0`
4. `open "file://$PWD/deploy/boot-splash.html?v=v1.0.0&health=http://127.0.0.1:8080/healthz"` → `v1.0.0` sous le mot-marque

- [ ] **Étape 6 : consigner la leçon**

Ajouter une entrée à `tasks/lessons.md`, au format du fichier (`[date] | ce qui a mal tourné | règle pour l'éviter`), sur le piège central de ce lot : **`+` dans une chaîne de requête se décode en espace** — un affichage faux que ni les tests unitaires ni la relecture n'attrapent, seulement l'œil sur l'écran.

```bash
git add tasks/lessons.md
git commit -m "docs: leçon — le « + » d'une URL se décode en espace

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Auto-revue du plan

**Couverture de la conception** — chaque section de la spec a sa tâche :

| Exigence de la spec | Tâche |
|---|---|
| Fichier généré, format, écriture atomique, échec silencieux | 4 |
| Module runtime, `public`, fail-safe | 1 |
| Garde de fraîcheur par lecture de référence | 2 |
| Surface « onglet Santé » | 8 |
| Surface « pied de `/display` » | 5 |
| Surface « boot-splash » | 6 |
| Surface « `/healthz` » | 3 |
| Surface « Journal » | 7 |
| Discipline de tags, pose de `v1.0.0`, pas de `CHANGELOG.md` | 9 |
| `.gitignore` | 4 |
| Tests unitaires énumérés dans la spec | 1, 2, 3 |
| Vérification de rendu réelle sur les trois surfaces visibles | 5, 6, 8 |

**Cohérence des noms** — `Version`, `known`, `label`, `commit`, `date`, `public`, `stale`, `snapshot()` sont identiques de la tâche 1 à la tâche 8. La variable de gabarit est `appversion` partout (tâches 3 et 5). La clé d'API est `version` partout (tâches 3 et 8). Le fichier est `comroster/VERSION` partout (tâches 1, 4, 6).

**Aucun espace réservé** — chaque étape porte le code réel à écrire, la commande exacte à lancer et le résultat attendu.

**Deux pièges documentés dans le plan plutôt que laissés à découvrir sur le terrain** : la propriété du dépôt qui fait échouer git sous `sudo` (tâche 4), et le `+` décodé en espace dans une chaîne de requête (tâche 6). Les deux échouent en silence — ce sont exactement ceux qui survivent à une suite de tests verte.
