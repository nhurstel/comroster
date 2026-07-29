# Versioning visible — conception

**Date** : 2026-07-29
**État** : validé par Nathan, prêt pour le plan d'implémentation

## Le problème

Aucune version applicative n'existe aujourd'hui. Ni `__version__`, ni champ dans
`pyproject.toml` (qui ne contient que la configuration pytest et coverage), ni tag git —
`git tag` renvoie vide. Les seules occurrences du mot « version » dans le code désignent
autre chose : le format d'archive de sauvegarde (`backup.VERSION = 1`) et le cache-buster
`mtime` du pack de marque.

Conséquence concrète : devant un boîtier, au téléphone, **la question « quel code tourne
sur cette machine ? » n'a pas de réponse sans SSH**. C'est le besoin réel — pas un besoin
cosmétique.

Le boîtier est un clone git, mis à jour par `git pull && sudo deploy/setup-pi.sh`
(`deploy/raspberry-pi.md:126`). L'état réel d'une machine est donc un commit, pas un
numéro choisi à la main. Un numéro saisi manuellement mentirait dès le premier `git pull`
intermédiaire.

## Principe directeur

**Une seule source de vérité, générée, jamais recopiée.**

Tout ce qui suit en découle. Chaque fois qu'un choix se présentait entre « deux endroits à
tenir à jour » et « un seul », c'est le second qui a été retenu — un deuxième endroit est
un deuxième endroit qui peut mentir.

## Architecture

### Le fichier généré

`deploy/setup-pi.sh` — déjà le passage obligé de toute mise à jour — exécute `git describe`
et écrit **une ligne de texte** dans `comroster/VERSION` :

```
v1.4.0+7 9f3c1a2 2026-07-29
```

Trois champs séparés par une espace :

| Champ | Origine | Exemple |
|---|---|---|
| `label` | `git describe --tags --always`, normalisé | `v1.4.0+7` |
| `commit` | `git rev-parse --short HEAD` | `9f3c1a2` |
| `date` | `git log -1 --format=%cs` | `2026-07-29` |

**Pourquoi du texte nu et pas du JSON** : le fichier a deux lecteurs, Python et shell.
`read label commit date < comroster/VERSION` côté shell, `.split()` côté Python. Un JSON
obligerait `deploy/kiosk-run.sh` à dépendre de `jq`, qui n'est pas installé par
`setup-pi.sh`. Une ligne, zéro dépendance, zéro ambiguïté.

**Pourquoi le shell normalise et pas Python** : `git describe` produit `v1.4.0-7-g9f3c1a2`,
qu'on veut afficher `v1.4.0+7`. Cette normalisation doit exister **une seule fois**. Si
Python la refaisait de son côté, le splash et l'onglet Santé pourraient diverger — ce qui
contredirait le principe directeur. Le shell écrit le label définitif :

```sh
label=$(git describe --tags --always | sed -E 's/-([0-9]+)-g[0-9a-f]+$/+\1/')
```

**Écriture atomique** : écrire `comroster/VERSION.tmp` puis `mv`, conformément à la
pratique déjà en place dans `services/storage.py` (le `.gitignore` couvre déjà `*.tmp`).

**Si git échoue** (dépôt absent, exécutable git absent, installation par rsync ou tar) :
`setup-pi.sh` **n'écrit rien** et affiche un avertissement. Il ne doit jamais graver un
fichier faux. L'absence de fichier est un état parfaitement géré en aval (`known = False`).

**`.gitignore`** : ajouter `comroster/VERSION` — c'est un artefact généré, pas du code
source. Note : le test `test_gitignore_couvre_tous_les_fichiers_detat` ne couvre pas ce
fichier (il n'est pas dans `DATA_DIR`), la ligne doit donc être ajoutée à la main.

### Le module runtime

`comroster/services/version.py`, sur le modèle exact de `services/branding.py` et
`services/lifetime.py` : **chargement unique au démarrage**, immuable ensuite. La version
du code ne change pas pendant qu'un show tourne, et un déploiement implique de toute façon
un redémarrage du service.

```python
class Version:
    known:  bool   # un fichier lisible a été trouvé
    label:  str    # "v1.4.0+7" | "9f3c1a2" | ""
    commit: str    # "9f3c1a2" | ""
    date:   str    # "2026-07-29" | ""
    public: str    # "v1.4" | ""   — voir ci-dessous
    stale:  bool   # le code déployé ne correspond plus au dépôt
```

**`public`** est le label tronqué à `majeur.mineur`, destiné au seul pied de `/display`.
Règle : si le label commence par `v` suivi d'un chiffre, tronquer à deux composants
(`v1.4.0+7` → `v1.4`, `v1.4.0` → `v1.4`) ; sinon chaîne vide. Un boîtier sans tag n'a
donc **pas** de version publique et n'affiche rien devant un client — être moins précis
est acceptable, affirmer quelque chose de faux ne l'est pas.

**Politique appliance fail-safe**, identique à `lifetime.py` : fichier absent, vide,
tronqué ou illisible ⇒ `known = False` et champs vides, avec un avertissement journalisé.
Jamais une exception qui empêcherait une page de s'afficher.

Injection dans les templates via `@app.context_processor`, à côté de `brand`.

### La garde de fraîcheur

Le fichier gravé a une faiblesse assumée : un `git pull` sans relance de `setup-pi.sh`
laisserait un numéro périmé affiché comme s'il était vrai. En pratique le risque est
limité — avec l'overlay read-only actif (`deploy/readonly-fs.sh`), `git pull` sur le
boîtier n'est pas possible sans désactiver l'overlay au préalable. Il reste neutralisable
à coût quasi nul.

**Mécanisme** — comparaison de **valeurs**, pas de dates, et sans sous-processus :

1. Lire `.git/HEAD`.
2. S'il contient `ref: refs/heads/<branche>`, lire `.git/refs/heads/<branche>` ; si ce
   fichier n'existe pas (références compactées par `git gc`), chercher la ligne
   correspondante dans `.git/packed-refs`.
3. S'il contient directement un SHA (HEAD détaché), l'utiliser tel quel.
4. `stale = not sha_complet.startswith(commit_gravé)`.

Tout échec de lecture à n'importe quelle étape ⇒ `stale = False`. On ne peut pas savoir,
donc on n'invente pas.

`.git` est cherché à la racine du dépôt, c'est-à-dire le parent de `comroster/`. S'il
s'agit d'un **fichier** et non d'un dossier (cas d'un worktree git), la garde est
désactivée sans erreur — cette configuration n'existe pas sur un boîtier.

**Écarté : la comparaison de `mtime`** entre `comroster/VERSION` et `.git/index`. C'est
une heuristique fausse : `git status` réécrit l'index dès qu'un `mtime` de fichier de
travail a changé, sans qu'une ligne de code ait bougé. Elle produirait des « incertaine »
à tort, ce qui détruirait la confiance dans l'indicateur. La lecture de référence coûte
une dizaine de lignes de plus et n'a aucun faux positif.

`stale` n'est visible **que dans l'onglet Santé**. Jamais sur `/display`, jamais sur le
splash.

## Les surfaces

| Surface | Affiche | Justification du niveau de détail |
|---|---|---|
| **Onglet Santé (admin)** | `ComRoster v1.4.0+7 · 9f3c1a2 · 2026-07-29`<br>+ `— incertaine, le code a changé depuis le déploiement` si `stale` | La surface de support : tout y est. Placée à côté du carnet de bord `lifetime`, déjà remonté par `services/health.py:160`. |
| **Pied de `/display`** | `Propulsé par ComRoster v1.4` (marque client active)<br>`COMROSTER par Nathan Hurstel · v1.4` (sans marque) | Écran vu par le client. `public` seul : pas de hash, pas de `+7`. Si `public` est vide, le pied reste **exactement** ce qu'il est aujourd'hui. |
| **Boot-splash** | `v1.4.0+7`, discret sous le mot-marque | `kiosk-run.sh` lit `comroster/VERSION` et ajoute `&v=<label>` à l'URL, exactement comme il passe déjà `next` et `health` (`kiosk-run.sh:12`). Le splash reste un fichier statique ouvert en `file://`, sans requête possible. |
| **`/healthz`** | `{"status": "ok", "version": "v1.4.0+7"}` | Gratuit, et c'est le point qu'on interroge à distance. |
| **Journal** | Entrée « démarrage en v1.4.0+7 » | `services/journal.py` tient déjà les redémarrages. Corollaire : le journal devient l'**historique des mises à jour du boîtier**. |

**Écartés volontairement** : la feuille imprimable (`templates/print.html` — document
remis au client, aucun besoin) et la page de connexion.

## Discipline de release

Le dépôt n'a aucun tag. **Premier geste : poser `v1.0.0` sur l'état actuel** — le produit
est livré, brandé, et compte 81 démarrages au carnet de bord.

SemVer relu pour une appliance :

- **MAJEUR** — la mise à jour exige une action humaine. Concrètement : quand
  `backup.VERSION` change, une archive ancienne ne se restaure plus.
- **MINEUR** — une fonction visible en plus.
- **CORRECTIF** — une correction, rien de neuf.

**Pas de `CHANGELOG.md`.** Le message du tag annoté *est* le changelog
(`git tag -a v1.4.0 -m "…"`), et `tasks/todo.md` documente déjà les lots par le menu. Un
fichier de plus serait un deuxième endroit à tenir à jour.

À documenter dans `README.md` et `deploy/raspberry-pi.md` : poser le tag **avant** de
déployer, sans quoi les boîtiers afficheront `+N` au lieu du numéro propre.

## Décisions et compromis assumés

**La version est exposée sur `/healthz`, qui n'est pas authentifié.** C'est une fuite
d'information mineure (surface d'attaque connue). Retenu quand même : le boîtier vit sur
un LAN de régie fermé, et pouvoir faire un `curl` depuis un poste sans ouvrir de session
est précisément ce qui rend l'indicateur utile en dépannage.

**Le display est moins précis que l'admin, délibérément.** `v1.4` devant un client là où
l'admin dit `v1.4.0+7`. Être moins précis n'est pas mentir ; afficher un numéro inventé le
serait.

**Le fichier gravé a été préféré à la résolution à chaud** (`git describe` appelé au
démarrage du service). La résolution à chaud ne peut structurellement pas être périmée,
mais introduit une dépendance à l'exécutable `git` et au dossier `.git` en production. Le
choix du fichier gravé, plus la garde de fraîcheur ci-dessus, couvre le même besoin sans
sous-processus au démarrage.

**`--dirty` n'est pas utilisé.** L'option force un rafraîchissement de l'index git, qu'un
système de fichiers monté en lecture seule refuse.

## Vérification

**Tests unitaires** (`tests/test_version.py`) :

- parsing nominal ; fichier absent ; fichier vide ; ligne tronquée à un ou deux champs ;
- label sans tag (`9f3c1a2`) ⇒ `public == ""` ;
- troncature `public` : `v1.4.0+7` → `v1.4`, `v1.4.0` → `v1.4` ;
- `stale` : SHA identique ⇒ `False` ; SHA différent ⇒ `True` ; `.git` absent ⇒ `False` ;
  référence compactée dans `packed-refs` ⇒ résolue ; HEAD détaché ⇒ résolu ;
- `/healthz` contient le champ `version` ;
- pied de `/display` inchangé quand `public` est vide.

**Vérification de rendu réelle, obligatoire** sur les trois surfaces visibles — onglet
Santé, pied du display, splash — et pas seulement des tests verts. La leçon consignée au
commit `975c29b` (« trois façons pour un outil de fabrication de mentir sur son succès »)
s'applique directement ici : un générateur qui écrit un fichier et déclare « fait » sans
que rien ne s'affiche à l'écran est exactement le piège décrit.

## Périmètre des fichiers

| Fichier | Nature |
|---|---|
| `comroster/services/version.py` | nouveau — lecture, `public`, garde de fraîcheur |
| `comroster/__init__.py` | extension, `context_processor`, champ dans `/healthz` |
| `comroster/services/health.py` | version dans le snapshot |
| `comroster/services/journal.py` | événement de démarrage |
| `templates/display.html` | pied de page |
| `templates/health.html`, `static/js/health.js` | affichage dans l'onglet Santé |
| `static/js/journal.js` | libellé de l'événement de démarrage |
| `deploy/setup-pi.sh` | génération du fichier |
| `deploy/kiosk-run.sh` | lecture et passage en paramètre d'URL |
| `deploy/boot-splash.html` | affichage du paramètre `v` |
| `.gitignore` | `comroster/VERSION` |
| `tests/test_version.py` | nouveau |
| `README.md`, `deploy/raspberry-pi.md` | discipline de tags |
