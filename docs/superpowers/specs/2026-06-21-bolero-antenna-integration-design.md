# Intégration antenne Bolero — Design

**Date :** 2026-06-21
**Statut :** validé (en attente de revue finale avant plan d'implémentation)

## Objectif

Permettre à ComRoster, **en option**, de se connecter à une antenne Riedel Bolero du
réseau intercom (IP + mot de passe) et d'**importer les beltpacks réels** dans le tableau
d'affectation. La fonctionnalité est **activable/désactivable** : désactivée (défaut),
ComRoster est strictement identique à aujourd'hui — aucune UI antenne, aucun appel réseau.

Périmètre de cette itération : **connexion + import des beltpacks**. Hors périmètre (plus
tard, l'architecture le permet) : pousser des configs vers l'antenne, monitoring temps
réel via WebSocket, pilotage des partylines/profils.

## Contexte API Bolero (référence : `RIEDEL SOFTS/BOLERO_API_BIBLE.md`)

- REST : `http://<ip>/rest/…` (port 80, pas de HTTPS natif).
- **Auth = HTTP Basic Auth**, utilisateur fixe `admin` + mot de passe →
  `Authorization: Basic base64("admin:" + password)`. Sans mot de passe, header omis.
- Test de connexion : `GET /rest/nodeStatus` (renvoie les nodes en ligne).
- Infos : `GET /rest/firmware`.
- Beltpacks : `GET /rest/bp` → `{ "bp": [ { registered, id, connectedNodeId?,
  lastConnectTime?, bpConfig: { bpNumber, bpName, … } } ] }`.

Mapping Bolero → ComRoster : `bpConfig.bpNumber` → `beltpack` (numéro, en chaîne) ;
`bpConfig.bpName` → `role` (le nom programmé ressemble à un rôle : « Régie Son »…) ;
le **nom de personne** ComRoster reste vide (à renseigner par le régisseur).

## Décisions actées

| Sujet | Décision |
|-------|----------|
| Activation | Feature flag `bolero_enabled` (défaut **false**), togglable depuis l'admin, persisté |
| Identifiants | IP + mot de passe **chiffrés sur disque** (Fernet, clé dérivée de `FLASK_SECRET_KEY`) ; reconnexion auto au démarrage si le flag est actif |
| Forme d'import | Une **fiche par beltpack** dans le pool « disponibles » (n° = bpNumber, rôle = bpName, nom vide) |
| Ré-import | **Synchroniser (antenne fait foi)** : crée les nouveaux, met à jour le rôle des existants, **préserve** noms et fiches manuelles, ne supprime jamais |
| Confirmation | **Récap avant application** : preview (nouveaux / rôles modifiés / inchangés / absents) puis « Appliquer » |
| Auth Bolero | Basic Auth, user `admin` (fixe), mot de passe saisi |

## Architecture

Nouveau service + un blueprint dédié, sans toucher au cœur existant.

```
comroster/
├── services/
│   ├── antenna.py     # NOUVEAU : client Bolero + état connexion + creds chiffrés
│   └── settings.py    # NOUVEAU : réglages app persistés (bolero_enabled)
├── antenna.py         # NOUVEAU : blueprint /api/settings + /api/antenna/*
└── __init__.py        # MODIF : enregistrer le blueprint, instancier les services,
                       #         reconnexion auto au boot si flag actif
```

### `services/settings.py`
Réglages applicatifs persistés dans `<DATA_DIR>/settings.json` (écriture atomique via
`Storage`).
- `Settings(storage)` ; `.get(key, default)` ; `.set(key, value)` ; `.all() -> dict`.
- Clé utilisée : `bolero_enabled: bool` (défaut `false`).

### `services/antenna.py`
Client Bolero **synchrone** (urllib + Basic Auth) avec état de connexion en mémoire de
process et persistance chiffrée des identifiants.

- `AntennaClient(data_dir, secret_key)`.
- Chiffrement : `Fernet(base64.urlsafe_b64encode(sha256(secret_key)))`. Si déchiffrement
  impossible (clé changée), les creds persistés sont ignorés (re-saisie requise).
- Persistance : `<DATA_DIR>/antenna.json` = `{ ip, password_enc, info, updated_at }`.
  Permissions `600`. `password_enc` = token Fernet (jamais en clair sur disque).
- Méthodes :
  - `connect(ip, password) -> dict` : test `GET /rest/nodeStatus` (Basic Auth, timeout 4 s) ;
    succès → `GET /rest/firmware`, stocke creds chiffrés + `info` (nodes, firmware),
    `connected=True`, retourne `info`. Échec → lève `AntennaError` (message « vérifiez IP
    et mot de passe »), n'écrit rien.
  - `disconnect()` : efface mémoire **et** `antenna.json`.
  - `status() -> dict` : `{ connected, ip, info }` (jamais le mot de passe).
  - `fetch_beltpacks() -> list[dict]` : `GET /rest/bp` ; renvoie pour chaque BP
    `registered` : `{ number: str, name: str, online: bool }`
    (`online` = `connectedNodeId` présent et ≠ 0).
  - `load_persisted()` : au boot, recharge ip+password déchiffrés en mémoire (sans tester).
  - `_request(method, path, body=None)` : urllib + Basic Auth + timeout, erreurs → `AntennaError`.
- `AntennaError(Exception)` : erreurs réseau/HTTP côté antenne.

### `model.merge_beltpacks(state, items) -> dict`
Fusion « antenne fait foi », pure (mute `state`), dans `services/model.py`.
```
created = updated = 0
for it in items:                       # it = {number, name, online}
    num = normalize_beltpack(it["number"])
    if not num: continue
    person = personne dont normalize_beltpack(beltpack) == num
    if person is None:
        state["people"].append({id:new_id(), name:"", role:it["name"] or "",
                                beltpack:num, group_id:None}); created += 1
    elif it["name"] and person["role"] != it["name"]:
        person["role"] = it["name"]; updated += 1
    if it["name"]:
        state.setdefault("beltpack_roles", {})[num] = it["name"]
touch(state)
return {"created": created, "updated": updated}
```
Ne supprime jamais. Les numéros Bolero étant uniques, aucun doublon de beltpack n'est créé.

### `model.diff_beltpacks(state, items) -> dict`
Calcule le récap **sans muter** :
- `new`    : `[{number, name}]` numéros absents de ComRoster.
- `changed`: `[{number, old_role, new_role}]` présents dont le rôle diffère du bpName (non vide).
- `unchanged` : entier (présents et rôle identique).
- `missing` : `[{number, role}]` fiches ComRoster (avec beltpack) sans équivalent antenne
  (info seulement, conservées).

## API HTTP (toutes protégées `login_required`)

| Méthode & route | Effet | Codes |
|-----------------|-------|-------|
| `GET /api/settings` | `{ bolero_enabled }` | 200 |
| `PUT /api/settings` `{bolero_enabled}` | Active/désactive ; désactivation → `disconnect()` | 200 |
| `POST /api/antenna/connect` `{ip,password}` | Connexion + persistance chiffrée | 200 / 400 (IP vide) / 502 (échec antenne) |
| `POST /api/antenna/disconnect` | Déconnexion + purge creds | 200 |
| `GET /api/antenna/status` | `{connected, ip, info}` | 200 |
| `POST /api/antenna/import/preview` | Lit `/rest/bp` → `diff_beltpacks` (récap) | 200 / 502 |
| `POST /api/antenna/import/apply` | Lit `/rest/bp` → `merge_beltpacks` → save draft | 200 `{created,updated}` / 502 |

**Garde feature flag :** si `bolero_enabled` est faux, tous les `/api/antenna/*` renvoient
**409** `{ "error": "bolero_disabled" }`. Le mot de passe n'apparaît dans aucune réponse.

## Flux de données

1. **Activation** : admin ouvre « Réglages » → bascule l'interrupteur → `PUT /api/settings`
   → le bloc Antenne apparaît.
2. **Connexion** : saisie IP + mot de passe → `POST /api/antenna/connect` → test Basic Auth →
   creds chiffrés sur disque, infos affichées.
3. **Import** : « Importer les beltpacks » → `POST /api/antenna/import/preview` → dialog récap
   (nouveaux / modifiés / inchangés / absents) → « Appliquer » → `POST /api/antenna/import/apply`
   → fusion dans le **brouillon** → re-render admin. La publication vers le display reste
   l'acte explicite habituel.
4. **Reconnexion auto** : au démarrage, si `bolero_enabled`, `load_persisted()` recharge les
   creds ; le statut réel est confirmé au premier `GET /api/antenna/status` (test léger).

## UI admin

- **Toolbar repensée** pour rester lisible : regroupement logique avec séparateurs —
  *Édition* (`+ Groupe`, `+ Personne`) · *Tableau* (`Infos`, `Écran : nuit`, `Historique`) ·
  *Données* (`Exporter`, `Importer`) · `⚙ Réglages` · `Publier` · `Déconnexion`.
  Style sobre identique à l'existant (boutons plats, hauteur uniforme).
- **Dialog « Réglages »** : interrupteur *Intégration réseau Bolero*. Si activé, un bloc
  *Antenne* :
  - déconnecté → champs IP + mot de passe + `Connecter` ;
  - connecté → `Antenne <nom> · firmware <v> · <n> beltpacks`, boutons `Importer les
    beltpacks` et `Déconnecter`.
- **Dialog « Récap d'import »** : `+ N nouveaux`, `~ M rôles mis à jour` (avant→après),
  `K inchangés`, `- W absents (conservés)`, puis `Appliquer` / `Annuler`.

Quand le flag est faux : ni le bloc Antenne, ni les dialogs antenne ne sont accessibles
(le bouton Réglages reste, pour pouvoir activer).

## Sécurité

- Endpoints réservés à l'admin (`login_required`) + CSRF (requêtes mutatives).
- Mot de passe antenne **chiffré** sur disque (Fernet/`FLASK_SECRET_KEY`), `antenna.json`
  hors versioning (`.gitignore`), permissions `600` ; **jamais** renvoyé au client.
- Flag off ⇒ aucun appel réseau sortant, endpoints antenne en 409.

## Dépendances

Ajout de `cryptography` à `requirements.txt`.

## Tests (pytest)

Faux antenne par monkeypatch de `AntennaClient._request` (ou fixture HTTP locale) :
- `connect` succès (stocke, chiffre) / échec (n'écrit rien, lève `AntennaError`).
- Chiffrement aller-retour : `password_enc` illisible en clair, déchiffré correctement ;
  clé changée → creds ignorés.
- `merge_beltpacks` : création (pool, nom vide), maj du rôle, **préservation du nom et du
  groupe**, pas de doublon, mise à jour `beltpack_roles`.
- `diff_beltpacks` : new / changed / unchanged / missing corrects.
- Garde flag : `/api/antenna/*` → 409 si `bolero_enabled` faux.
- Import bout-en-bout : preview puis apply modifient le brouillon ; status ne fuit pas le mdp.

`RIEDEL SOFTS/Riedel Bolero/Webapp/bolero_mock_server.py` reste disponible pour un essai
manuel réaliste contre une fausse antenne.

## Fichiers touchés

- Créés : `comroster/services/settings.py`, `comroster/services/antenna.py`,
  `comroster/antenna.py`, `templates` (dialogs réglages/récap intégrés à `admin.html`),
  JS (`static/js/admin.js` étendu), tests `tests/test_settings.py`,
  `tests/test_antenna.py`, `tests/test_merge_beltpacks.py`.
- Modifiés : `comroster/__init__.py` (services + blueprint + reconnexion auto),
  `comroster/services/model.py` (`merge_beltpacks`, `diff_beltpacks`),
  `templates/admin.html` (toolbar + dialogs), `static/css/admin.css` (toolbar/dialogs),
  `requirements.txt`, `.gitignore` (`antenna.json`, `settings.json`).
