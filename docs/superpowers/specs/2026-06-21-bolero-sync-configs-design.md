# Synchronisation antenne (miroir + plages), configs nommées, suppression multiple — Design

**Date :** 2026-06-21
**Statut :** validé (en attente de revue finale avant plan d'implémentation)
**Évolution de :** `2026-06-21-bolero-antenna-integration-design.md` (intégration de base déjà livrée)

## Objectif

Trois évolutions de la gestion des beltpacks, autour d'un principe simplifié : **un seul
tableau de travail**.

1. **Synchronisation miroir** depuis l'antenne (l'antenne fait foi) avec **récap avant
   application**, filtrée par **plages d'ID** (une instance ComRoster = une salle).
2. **Configs nommées** : sauvegarder/recharger des configurations complètes (preset « Base »,
   « Jour 2 »…). Charger une config **déconnecte** l'antenne.
3. **Suppression multiple** de fiches via un mode sélection.

Abandonné par rapport à une piste intermédiaire : la notion de « deux espaces manuel/antenne
avec bascule ». Remplacée par **un tableau unique** + **configs nommées**, plus simple et plus
puissant.

## Décisions actées

| Sujet | Décision |
|-------|----------|
| Tableau | **Un seul brouillon** (`data_draft.json`). Pas de swap, pas de mode persistant. |
| Connexion/déconnexion | N'échangent pas de tableau. La connexion **synchronise** le tableau ; la déconnexion **ne touche pas** le tableau (on garde la config, éditable). |
| Sync = miroir | Connexion **et** « Actualiser » → **récap** (à ajouter / rôles modifiés / inchangés / **à retirer**) → Appliquer. Miroir = beltpacks antenne **dans les plages**, retire le reste, **préserve noms et groupes** des conservés. |
| Plages | `antenna_ranges` = liste d'intervalles `[min,max]` dans `settings.json`. Vide = tous. Filtre **avant** miroir. |
| Configs nommées | Dossier `configs/` : sauver le brouillon courant sous un nom, lister, charger (remplace le brouillon), supprimer. **Charger ⇒ déconnecte l'antenne.** |
| Suppression multiple | Mode sélection (cases à cocher) + « Supprimer (N) ». Endpoint batch. |

## Architecture

```
comroster/
├── services/
│   ├── configs.py     # NOUVEAU : bibliothèque de configs nommées (CRUD dans configs/)
│   ├── model.py       # + mirror_beltpacks, filter_by_ranges, delete_people
│   └── antenna.py     # inchangé (fetch_beltpacks)
├── antenna.py         # blueprint : sync miroir + plages ; + endpoints configs ; + delete-batch
└── __init__.py        # + instancier Configs
```

### `services/configs.py`
Bibliothèque de configurations nommées, persistées dans `<DATA_DIR>/configs/<slug>.json`
(écriture atomique via `Storage`).
- `Configs(storage)`.
- `.list() -> list[dict]` → `[{"name": str, "updated_at": str}]`, trié par nom.
- `.save(name, state) -> None` → écrit `{ "name", "updated_at", "state" }` ; `name` non vide
  (sinon `ValueError`) ; fichier = slug du nom (collisions de slug → même nom écrasé).
- `.load(name) -> dict` → retourne le `state` ; `KeyError` si absent.
- `.delete(name) -> None` → supprime ; `KeyError` si absent.

### `services/model.py` (ajouts)
- `filter_by_ranges(items, ranges) -> list` : si `ranges` est vide ⇒ renvoie tous les items.
  Sinon ⇒ garde uniquement les items dont `int(number)` tombe dans un intervalle `[lo,hi]`
  (un `number` non entier est alors exclu).
- `mirror_beltpacks(state, items) -> dict` : applique le miroir.
  - Ajoute les numéros absents (au pool, nom vide), met à jour le rôle des existants
    (préserve nom **et** groupe), **retire** les fiches dont le numéro n'est pas dans `items`,
    met à jour `beltpack_roles` pour les présents.
  - Retourne `{"created":int, "updated":int, "removed":int}`.
- `delete_people(state, ids) -> int` : retire les personnes dont l'`id` est dans `ids`,
  retourne le nombre supprimé ; `touch(state)`.
- `diff_beltpacks(state, items)` (déjà présent) sert au récap ; en mode miroir, `missing`
  signifie « **à retirer** ».
- `merge_beltpacks` (additif, déjà présent) reste comme brique mais n'est plus utilisé par
  l'API de sync (remplacé par `mirror_beltpacks`).

## API HTTP (toutes `login_required`)

| Méthode & route | Effet | Codes |
|-----------------|-------|-------|
| `PUT /api/settings` `{bolero_enabled?, antenna_ranges?}` | Met à jour les réglages ; `antenna_ranges` validé (liste de `[int,int]`, `lo<=hi`) | 200 / 400 (plages invalides) |
| `POST /api/antenna/import/preview` | `fetch_beltpacks` → `filter_by_ranges` → `diff_beltpacks` (récap miroir) | 200 / 409 (flag) / 502 |
| `POST /api/antenna/import/apply` | `fetch` → `filter` → `mirror_beltpacks` → save draft | 200 `{created,updated,removed}` / 409 / 502 |
| `GET /api/configs` | Liste des configs | 200 |
| `POST /api/configs` `{name}` | Sauve le brouillon courant sous `name` | 200 / 400 (nom vide) |
| `POST /api/configs/<name>/load` | Charge la config → remplace le brouillon **+ déconnecte l'antenne** | 200 / 404 |
| `DELETE /api/configs/<name>` | Supprime la config | 200 / 404 |
| `POST /api/people/delete-batch` `{ids:[…]}` | Suppression multiple dans le brouillon | 200 `{deleted:int}` |

Inchangés : `GET/PUT /api/settings` (étendu), `connect`, `disconnect`, `status`. La garde
flag (409 si `bolero_enabled` faux) s'applique aux routes `/api/antenna/*` ; les configs et
`delete-batch` ne sont **pas** gardées par le flag (elles concernent le tableau, pas l'antenne).

## Flux de données

1. **Connexion** : `connect {ip,password}` → établit le lien. L'UI enchaîne aussitôt sur
   `import/preview` → affiche le **récap** → l'utilisateur **Applique** (`import/apply`,
   miroir). Même récap pour « Actualiser depuis l'antenne » ultérieurement.
2. **Déconnexion** : `disconnect` → le tableau reste tel quel (config conservée, éditable).
3. **Sauver une config** : `POST /api/configs {name}` avec le brouillon courant.
4. **Charger une config** : `POST /api/configs/<name>/load` → `save_draft(config)` +
   `client.disconnect()` → retour standalone propre, tableau = la config.
5. **Suppression multiple** : sélection d'ids → `delete-batch` → save draft → re-render.

## UI admin

- **Indicateur d'état antenne** (dans le dialog Réglages) : connecté (nom + firmware) / hors
  ligne, et rappel des plages actives.
- **Dialog Réglages** : interrupteur (existant) + **éditeur de plages** (`antenna_ranges` :
  ajout/suppression d'intervalles `de … à …`) + connexion + bouton **« Actualiser depuis
  l'antenne »** (quand connecté).
- **Récap de sync** (dialog existant) : ajoute la ligne « **N à retirer** » (les `missing`).
- **Dialog « Configurations »** (nouveau bouton dans la barre, groupe *Données*) : liste des
  configs (Charger / Supprimer) + champ « Sauvegarder la config courante sous… ».
- **Mode sélection** : bouton « Sélectionner » dans le panneau « Disponibles » (et groupes) →
  cases à cocher sur les fiches → barre « Supprimer (N) » / « Annuler ».
- **Confirmation** au chargement d'une config et à la suppression multiple.

## Sécurité

- Tous les endpoints `login_required` + CSRF. `configs/` dans `DATA_DIR`, **gitignored**.
- Charger une config remplace le brouillon (acte explicite, confirmé) ; la publication vers
  le display reste séparée.
- Validation des plages (entiers, `lo<=hi`) côté serveur → 400 sinon.

## Tests (pytest)

- `filter_by_ranges` : intervalles multiples, vide = tout, numéros non entiers exclus si
  ranges non vide.
- `mirror_beltpacks` : création, maj rôle, **retrait des absents**, **préservation nom+groupe**
  des conservés, compteur `{created,updated,removed}`.
- `delete_people` : suppression par ids, compteur, ids inexistants ignorés.
- `Configs` : save/list/load/delete, slug, `KeyError` sur absent, nom vide → `ValueError`.
- API : `import/apply` retire bien les absents ; `antenna_ranges` filtre l'import ; plages
  invalides → 400 ; `configs/<name>/load` déconnecte l'antenne ; `delete-batch` ; garde flag.
- Bout-en-bout (faux serveur antenne) : plages → seuls les BP voulus importés ; ré-sync retire
  un BP disparu.

## Fichiers touchés

- Créés : `comroster/services/configs.py`, `tests/test_configs.py`,
  `tests/test_mirror_beltpacks.py` (+ ajouts dans `tests/test_antenna_api.py`).
- Modifiés : `comroster/services/model.py` (mirror/filter/delete_people),
  `comroster/antenna.py` (sync miroir, plages, endpoints configs, delete-batch),
  `comroster/__init__.py` (instancier `Configs`), `templates/admin.html` (éditeur de plages,
  dialog Configurations, mode sélection, ligne « à retirer »), `static/js/admin.js`,
  `static/css/admin.css`, `.gitignore` (`configs/`).
