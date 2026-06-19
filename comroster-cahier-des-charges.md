# ComRoster — Cahier des charges fonctionnel

Tableau d'affectation dynamique des beltpacks d'intercom pour spectacles et concerts.
Application web séparant une **interface d'administration** (préparation/édition) d'un
**affichage public temps réel** (écran TV en régie).

---

## 1. Contexte & objectif

L'outil permet à un régisseur de définir qui porte quel beltpack d'intercom, de
regrouper les personnes par équipe/canal, puis de **publier** cet état vers un écran
de diffusion visible par toute l'équipe technique. La publication est un acte explicite :
l'admin travaille sur un brouillon, puis pousse l'état validé vers le display.

Principe directeur : **deux états distincts** — l'état de travail (admin) et l'état publié
(display). Rien n'apparaît à l'écran tant que l'utilisateur n'a pas publié.

---

## 2. Acteurs

| Acteur | Accès | Rôle |
|--------|-------|------|
| Administrateur | Authentifié (mot de passe) | Crée/modifie groupes et personnes, affecte, publie |
| Spectateur (écran TV) | Public, lecture seule | Consulte l'affectation publiée en temps réel |

---

## 3. Modèle de données

### 3.1 Personne
- `id` (identifiant unique)
- `nom`
- `role` (fonction : HF, plateau, lumière, etc.)
- `beltpack` (numéro/identifiant du boîtier intercom — **unique** ; chaque beltpack Bolero Riedel porte un numéro propre)
- `groupe_id` (affectation courante, nullable → personne non affectée)

### 3.2 Groupe
- `id`
- `nom`
- `couleur` (code couleur personnalisable, ex. hex)
- `ordre` (position d'affichage, optionnel)

### 3.3 État global
- Liste des groupes
- Liste des personnes
- Pool « disponibles » = personnes sans `groupe_id`

### 3.4 Persistance (fichiers plats)
- `data_draft.json` : **état de travail** (brouillon), écrit à chaque modification dans l'admin
- `data_published.json` : **état publié**, snapshot validé que `/display` lit et diffuse
- `admin_secret.json` : hash du mot de passe + hash du code de récupération (privé, jamais versionné)
- `data.sample.json` : exemple de configuration (optionnel)
- `history/` : snapshots horodatés des publications successives (cf. B3)

> Décision actée : **deux fichiers d'état**. L'admin n'écrit jamais directement dans
> l'état publié. « Publier » copie le brouillon vers le fichier publié, archive le
> snapshot précédent dans `history/`, puis notifie les displays (SSE). Cela garantit
> qu'une édition en cours ne fuite jamais à l'écran avant publication.

---

## 4. Fonctions par module

### 4.1 Module Authentification & sécurité

| # | Fonction | Description |
|---|----------|-------------|
| A1 | Configuration initiale | Au premier lancement, `/admin/setup` impose la création d'un mot de passe admin (min. 8 caractères) |
| A2 | Génération du code de récupération | Un code unique est affiché **une seule fois** à la création ; il sert à réinitialiser le mot de passe |
| A3 | Connexion | `/admin/login` : vérification du mot de passe (hash Werkzeug), ouverture de session chiffrée |
| A4 | Déconnexion | Bouton dédié dans la toolbar, destruction de la session |
| A5 | Mot de passe oublié | Réinitialisation via le code de récupération → nouveau mot de passe + nouveau code généré |
| A6 | Reset total | Suppression manuelle de `admin_secret.json` → retour à la configuration initiale |
| A7 | Protection des routes | Toutes les routes admin exigent une session valide |

### 4.2 Module Gestion des groupes

| # | Fonction | Description |
|---|----------|-------------|
| G1 | Créer un groupe | Saisie d'un nom |
| G2 | Personnaliser la couleur | Sélecteur de couleur par groupe |
| G3 | Modifier un groupe | Renommer / changer la couleur |
| G4 | Supprimer un groupe | Les personnes affectées **repassent dans le pool disponible** (elles ne sont jamais supprimées avec le groupe) |
| G5 | Ordonner les groupes | Position d'affichage (optionnel) |

### 4.3 Module Gestion des personnes

| # | Fonction | Description |
|---|----------|-------------|
| P1 | Ajouter une personne | Saisie nom + rôle + numéro de beltpack, groupe optionnel |
| P2 | Modifier une personne | Édition des champs |
| P3 | Modifier le beltpack | Action rapide via menu contextuel (clic droit) |
| P4 | Supprimer une personne | Retrait définitif |
| P5 | Affecter à un groupe | **Drag-and-drop** depuis le pool « disponibles » vers un groupe |
| P6 | Déplacer entre groupes | Drag-and-drop d'un groupe vers un autre |
| P7 | Retirer d'un groupe | Menu contextuel → retour au pool disponible |
| P8 | Contrôle d'unicité du beltpack | **Blocage dur** : si un numéro de beltpack est déjà attribué, son affectation à une autre personne est **impossible** (rejet de la saisie, pas de simple avertissement) |

### 4.4 Module Import / Export

| # | Fonction | Description |
|---|----------|-------------|
| I1 | Exporter la configuration | Téléchargement JSON de l'état complet (groupes + personnes) |
| I2 | Importer une configuration | Restauration depuis un fichier JSON |

### 4.5 Module Publication

| # | Fonction | Description |
|---|----------|-------------|
| B1 | Publier vers l'affichage | Copie l'état de travail vers l'état publié |
| B2 | Notification temps réel | Déclenche la mise à jour instantanée de tous les displays connectés (SSE) |
| B3 | Archivage de l'historique | À chaque publication, snapshot horodaté dans `history/` |
| B4 | Consulter l'historique | Lister les publications passées (date/heure) — *nice-to-have* |
| B5 | Restaurer une publication | Recharger un snapshot historique comme nouvel état de travail — *nice-to-have* |

> Concurrence multi-admin : **dernière modification gagne** (last-write-wins). Pas de
> verrou ; le dernier `publish` écrase l'état publié, le dernier enregistrement de
> brouillon écrase le brouillon.

### 4.6 Module Affichage public (Display)

| # | Fonction | Description |
|---|----------|-------------|
| D1 | Affichage TV | Rendu lisible à distance, optimisé grands écrans, design glassmorphism |
| D2 | Mise à jour temps réel | Réception des changements via Server-Sent Events, sans rechargement |
| D3 | Auto-scroll | Défilement automatique du contenu, avec délai initial, pauses en haut/bas, vitesse paramétrables |
| D4 | Horloge | Heure courante affichée en continu |
| D5 | Indicateur de connexion | Témoin « En direct » (vert si flux SSE actif) |
| D6 | Statistiques live | Compteurs : nombre de groupes / nombre de personnes affichés |
| D7 | Mode jour/nuit | Adaptation de la luminosité/contraste |
| D8 | Reconnexion SSE automatique | Après une coupure réseau, le display rétablit seul le flux et resynchronise l'état publié |

---

## 5. Paramètres configurables

```
AUTO_SCROLL_INITIAL_DELAY   délai avant démarrage du scroll (ms)
AUTO_SCROLL_EDGE_PAUSE      pause en haut/bas de page (ms)
AUTO_SCROLL_SPEED           vitesse de défilement (px/s)

--primary / --secondary / --accent   couleurs de thème (CSS :root)

FLASK_SECRET_KEY    clé de session (obligatoire en prod)
PORT                port d'écoute (défaut 8080)
FLASK_DEBUG         mode debug (False en prod)
```

---

## 6. Exigences non-fonctionnelles

- **Temps réel** : propagation des changements via SSE, latence quasi nulle après publication.
- **Sécurité** : mots de passe hashés (Werkzeug), sessions chiffrées, `admin_secret.json` hors versioning.
- **Performance** : animations GPU-accelerated, CSS optimisé, dégradation possible (désactiver `backdrop-filter`).
- **Responsive** : desktop, tablette, mobile pour l'admin ; grand écran pour le display.
- **Accessibilité** : visée WCAG.
- **Portabilité** : Python 3.7+, Flask, dépendances minimales.
- **Déploiement** : service systemd + reverse proxy Nginx avec `proxy_buffering off` (indispensable au SSE).

---

## 7. Cartographie des routes (déduite)

| Route | Méthode | Accès | Rôle |
|-------|---------|-------|------|
| `/admin/setup` | GET/POST | Public (1er lancement) | Création du compte admin |
| `/admin/login` | GET/POST | Public | Connexion / mot de passe oublié |
| `/admin` | GET | Authentifié | Interface d'administration |
| `/admin/...` (publish, CRUD) | POST | Authentifié | Actions sur groupes/personnes, publication |
| `/display` | GET | Public | Affichage TV |
| flux SSE (ex. `/stream`, `/events`) | GET | Public | Canal temps réel pour le display |

---

## 8. Parcours utilisateur de référence

1. **Setup** → création mot de passe + sauvegarde du code de récupération.
2. **Préparation** → création des groupes (avec couleurs), ajout des personnes.
3. **Affectation** → drag-and-drop des personnes dans les groupes.
4. **Publication** → bouton « Publier vers l'affichage ».
5. **Diffusion** → le `/display` se met à jour instantanément sur l'écran de régie.
6. **Ajustement en cours de show** → modif dans l'admin + nouvelle publication.

---

## 9. Décisions de conception actées

| Sujet | Décision |
|-------|----------|
| Brouillon vs publié | **Deux fichiers** (`data_draft.json` + `data_published.json`). L'admin n'écrit jamais directement dans le publié ; « Publier » copie l'un vers l'autre. |
| Suppression d'un groupe | Ses membres **retournent dans le pool disponible** ; ils ne sont jamais supprimés. |
| Concurrence multi-admin | **Dernière modification gagne** (last-write-wins), pas de verrou. |
| Unicité des beltpacks | **Numéro unique, blocage dur.** Si un beltpack porte déjà un numéro, il est impossible de l'attribuer à une autre personne ; la saisie est rejetée (validation à l'ajout comme à la modification). |
| Historique des publications | **Souhaité (nice-to-have)** : snapshots horodatés dans `history/`, consultation et restauration possibles. |
| Reconnexion SSE | **Oui** : reprise automatique du flux et resynchronisation côté display après coupure. |

---

## 10. Réalisation

Cette partie définit la **manière de construire** ComRoster : pile technique justifiée,
architecture logicielle, contrats/protocoles, sécurité, roadmap par phases et méthode de
travail. Les choix visent la robustesse en condition de spectacle (le pire moment pour un bug).

### 10.1 Pile technique retenue

| Couche | Choix | Pourquoi |
|--------|-------|----------|
| Backend | **Flask** (Python 3.7+) | Léger, suffisant pour l'échelle (une régie, quelques admins, quelques écrans), conforme au README |
| Temps réel | **Server-Sent Events** (pas WebSocket) | Le flux est **unidirectionnel** serveur → display ; SSE est plus simple, reconnecte nativement (`EventSource`) et passe les reverse-proxies HTTP sans bricolage |
| Persistance | **Fichiers JSON + écriture atomique** | Conforme au README ; pas de SGBD à déployer en venue. La robustesse vient de l'atomicité (cf. 10.3), pas d'un moteur |
| Frontend admin | **HTML server-rendered + JS vanilla + SortableJS** | Drag-and-drop entre listes fiable sans framework lourd ; SortableJS gère le glisser-déposer inter-conteneurs proprement (~10 ko) |
| Frontend display | **JS vanilla + `EventSource`** | Aucune dépendance, reconnexion automatique intégrée |
| Hashing | **Werkzeug** (`generate_password_hash` / `check_password_hash`) | Déjà fourni avec Flask, algorithmes à jour (pbkdf2/scrypt) |
| Sécurité formulaires | **CSRF token** (Flask-WTF ou double-submit manuel) | Auth par cookie de session ⇒ protection CSRF **obligatoire** sur toute route mutative |
| Anti-bruteforce | **Flask-Limiter** (ou compteur maison) | Un seul mot de passe protège tout : limiter les tentatives de login |
| Prod | **Gunicorn (1 worker, gthread) + Nginx + systemd** | Le pub/sub SSE est en mémoire ⇒ **un seul process** (cf. 10.6) |

> Pourquoi pas FastAPI/WebSocket/Postgres ? Parce que le besoin réel — pousser un état
> validé vers des écrans en lecture seule — est exactement le terrain de jeu de SSE+Flask.
> Ajouter de l'asynchrone, du bidirectionnel ou un SGBD serait de la complexité sans contrepartie.

### 10.2 Architecture logicielle

Découpage en **application factory + blueprints + services**, pour la testabilité et la séparation des responsabilités.

```
comroster/
├── app.py                    # point d'entrée (bootstrap create_app)
├── comroster/
│   ├── __init__.py           # create_app() : factory, config, enregistrement des blueprints
│   ├── config.py             # lecture des variables d'environnement
│   ├── auth.py               # blueprint : /admin/setup, /admin/login, /admin/logout, /admin/recover
│   ├── api.py                # blueprint : CRUD groupes/personnes, /api/publish, import/export
│   ├── display.py            # blueprint : /display (page), /events (flux SSE)
│   ├── security.py           # CSRF, rate-limit, garde de session (@login_required)
│   └── services/
│       ├── storage.py        # lecture / écriture atomique des fichiers d'état + verrou
│       ├── model.py          # schéma, normalisation, validation (unicité beltpack)
│       ├── pubsub.py         # broker SSE en mémoire (liste de files par client)
│       └── history.py        # snapshots horodatés, listing, restauration
├── templates/                # setup.html, login.html, admin.html, display.html
├── static/
│   ├── css/main.css
│   └── js/{admin.js, display.js}
├── tests/                    # pytest
├── data_draft.json           # (gitignored)
├── data_published.json       # (gitignored)
├── admin_secret.json         # (gitignored)
├── history/                  # (gitignored)
├── requirements.txt
└── .gitignore
```

**Flux de données :** l'UI admin lit/écrit le **brouillon** via `/api/*` → `model` valide →
`storage` écrit atomiquement `data_draft.json`. Au clic « Publier », `api` appelle la
séquence de publication (10.3) → `pubsub` diffuse → chaque `/events` pousse le nouvel état →
les displays se rafraîchissent.

### 10.3 Protocoles & contrats

#### Schéma des fichiers d'état (`data_draft.json` / `data_published.json`)

```json
{
  "version": 1,
  "updated_at": "2026-06-19T14:32:00Z",
  "groups": [
    { "id": "f3a1…", "name": "Plateau", "color": "#00A8E8", "order": 0 }
  ],
  "people": [
    { "id": "b27c…", "name": "Jean", "role": "HF", "beltpack": "12", "group_id": "f3a1…" }
  ]
}
```
- `id` : **UUID4** (évite les collisions à l'import / la fusion).
- `group_id` : `null` ⇒ personne dans le pool « disponibles ».
- `version` : prévu pour de futures migrations de schéma.

#### Écriture atomique (cœur de la robustesse)

Avec des fichiers plats + last-write-wins, le risque n'est pas le conflit logique mais
le **fichier corrompu** (écriture interrompue, écritures concurrentes). Règle imposée dans `storage.py` :

1. Sérialiser en mémoire.
2. Écrire dans un fichier temporaire **dans le même répertoire**.
3. `flush()` + `os.fsync()`.
4. `os.replace(tmp, cible)` — **renommage atomique** (jamais de fichier à moitié écrit).
5. Le tout sous un `threading.Lock` global pour sérialiser les écritures du process.

#### API HTTP (REST-ish)

| Méthode & route | Accès | Effet | Codes |
|-----------------|-------|-------|-------|
| `POST /admin/setup` | Public (1er run) | Crée le compte + code de récup | 201 / 409 si déjà configuré |
| `POST /admin/login` | Public | Ouvre la session | 200 / 401 / 429 (rate-limit) |
| `POST /admin/logout` | Auth | Détruit la session | 204 |
| `POST /admin/recover` | Public | Reset via code de récup | 200 / 401 |
| `GET /api/state` | Auth | Renvoie le **brouillon** | 200 |
| `POST /api/groups` · `PATCH /api/groups/{id}` · `DELETE /api/groups/{id}` | Auth | CRUD groupe (suppression ⇒ membres au pool) | 200 / 404 |
| `POST /api/people` · `PATCH /api/people/{id}` · `DELETE /api/people/{id}` | Auth | CRUD personne / affectation | 200 / 404 / **409 beltpack déjà pris** |
| `POST /api/publish` | Auth | Séquence de publication (ci-dessous) | 200 / 409 si brouillon invalide |
| `GET /api/history` · `POST /api/history/{ts}/restore` | Auth | Lister / restaurer un snapshot | 200 / 404 |
| `GET /api/export` · `POST /api/import` | Auth | Sauvegarde / restauration JSON | 200 / 400 si JSON invalide |
| `GET /display` | Public | Page d'affichage | 200 |
| `GET /events` | Public | Flux SSE | 200 (text/event-stream) |

> **Unicité beltpack** : vérifiée **côté serveur** dans `model.py` à chaque `POST`/`PATCH`
> personne. Si le numéro est déjà attribué à un autre `id`, réponse **409 Conflict**, aucune
> écriture. Le contrôle client n'est qu'un confort ; le serveur fait foi (cohérent avec last-write-wins).

#### Séquence de publication (`POST /api/publish`)

1. Charger le brouillon, **valider** (unicité beltpack, intégrité des `group_id`).
2. Si invalide → 409, on s'arrête.
3. Écrire atomiquement `data_published.json` (10.3).
4. Archiver une copie dans `history/<timestamp>.json`.
5. Diffuser l'événement à tous les clients SSE.

#### Protocole SSE (`GET /events`)

- En-têtes : `Content-Type: text/event-stream`, `Cache-Control: no-cache`, `X-Accel-Buffering: no` (désactive le buffering Nginx).
- À la connexion : le serveur envoie `retry: 3000` puis un événement `snapshot` contenant **l'état publié complet** → resynchronisation immédiate, y compris après une coupure.
- À chaque publication : événement `published` avec l'état complet.
- **Heartbeat** : une ligne commentaire `: keepalive` toutes les ~15 s pour empêcher proxy/navigateur de couper une connexion oisive.
- Côté display : `EventSource` reconnecte tout seul ; comme chaque (re)connexion renvoie un `snapshot`, **aucun rejeu d'événements (Last-Event-ID) n'est nécessaire** — la reconnexion (D8) est résolue par construction.

```
retry: 3000

event: snapshot
data: {"version":1,"groups":[…],"people":[…]}

: keepalive

event: published
data: {"version":1,"groups":[…],"people":[…]}
```

### 10.4 Sécurité (mise en œuvre)

- `FLASK_SECRET_KEY` **obligatoire** en prod (refuser de démarrer sinon) ; valeur longue et aléatoire.
- Cookie de session : `HttpOnly`, `SameSite=Lax`, `Secure` (derrière HTTPS).
- **CSRF** : jeton sur toutes les requêtes mutatives (POST/PATCH/DELETE).
- **Rate-limit** du login (ex. 5 tentatives / 5 min / IP) → 429.
- Mot de passe **et** code de récupération hashés (Werkzeug) ; `admin_secret.json` hors versioning + permissions `600`.
- `/api/*` et `/admin/*` (hors setup/login/recover) protégés par garde de session.
- `/display` et `/events` publics **en lecture seule** : ils n'exposent que l'état publié (jamais le brouillon, jamais de secret).

### 10.5 Roadmap par phases

Chaque phase est livrable et testable indépendamment ; on ne passe à la suivante qu'une fois la précédente « Done » (10.6).

| Phase | Objet | Livrable | « Done » quand |
|-------|-------|----------|----------------|
| **P0 — Socle** | Repo, venv, `requirements.txt`, `.gitignore`, `create_app()`, `config.py` | App qui démarre, route santé | `flask run` répond, config lue depuis l'env |
| **P1 — Données & validation** | `model.py`, `storage.py` (écriture atomique + lock), schéma, unicité beltpack | Couche persistance testée | Tests verts : atomicité, rejet beltpack doublon, suppression groupe → pool |
| **P2 — Auth & sécurité** | `auth.py`, `security.py` : setup/login/logout/recover, CSRF, rate-limit | Accès admin protégé | Setup une fois, login/logout OK, brute-force limité, secret hashé |
| **P3 — API CRUD** | `api.py` : groupes, personnes, affectations | API complète sur le brouillon | Tous les endpoints répondent aux bons codes (200/404/409) |
| **P4 — Publication & temps réel** | Séquence publish, `history.py`, `pubsub.py`, `/events` | Brouillon → publié → SSE | Une publication atteint un client SSE de test ; snapshot historisé |
| **P5 — UI Admin** | `admin.html` + `admin.js` : DnD (SortableJS), couleurs, menu contextuel, import/export, bouton Publier | Régie utilisable | Parcours §8 réalisable à la souris |
| **P6 — UI Display** | `display.html` + `display.js` : `EventSource`, auto-scroll, horloge, stats, jour/nuit, reconnexion | Écran TV opérationnel | Publication visible en direct ; coupure réseau → resync auto (D8) |
| **P7 — Historique (nice-to-have)** | UI de consultation/restauration (B4/B5) | Time-travel des publications | Lister et restaurer un snapshot fonctionne |
| **P8 — Durcissement & déploiement** | Tests d'intégration, unit systemd, conf Nginx (`proxy_buffering off`), gunicorn 1 worker gthread | Mise en prod reproductible | Service démarre au boot, SSE passe le proxy, tests CI verts |

### 10.6 Démarche & méthode

- **TDD ciblé sur le critique** : `storage` (atomicité), `model` (unicité beltpack, suppression groupe), séquence de `publish`. Ce sont les points où un bug se paie en plein direct → on écrit le test avant le code.
- **Tranches verticales** : faire marcher le chemin de bout en bout *(ajouter une personne → publier → la voir à l'écran)* dès P4/P5, **avant** de polir l'UI. On valide l'architecture tôt.
- **Un seul worker pour le SSE** : le broker pub/sub est en mémoire. En prod, `gunicorn --workers 1 --threads 8 --worker-class gthread`. Un publish traité par un worker n'atteindrait jamais un display branché sur un autre worker. *Voie de montée en charge si un jour nécessaire : remplacer le broker mémoire par un pub/sub Redis* — mais hors besoin actuel.
- **Tester les modes de panne, pas seulement le chemin heureux** : couper le réseau et vérifier la resynchro du display (D8) ; ouvrir deux onglets admin et vérifier le comportement last-write-wins ; tenter un beltpack en double et vérifier le 409.
- **Definition of Done par fonctionnalité** : code + test automatisé (pour le backend critique) + vérification manuelle à l'écran. Une fonction n'est finie que si elle est visible et correcte sur le display.
- **Commits atomiques** (un changement cohérent par commit), branches par phase, `.gitignore` strict sur les fichiers d'état et le secret dès P0.
- **Nice-to-have isolés** (P7) : derrière le cœur, jetables si le temps manque, sans bloquer une mise en service.

### 10.7 Checklist d'acceptation finale

- [ ] A1–A7 : setup unique, login/logout, récupération, reset, routes gardées
- [ ] G1–G5 : CRUD groupes ; **suppression → membres au pool**
- [ ] P1–P8 : CRUD personnes, DnD, menu contextuel ; **beltpack unique, blocage dur (409)**
- [ ] I1–I2 : export / import JSON
- [ ] B1–B5 : publication atomique, SSE, historisation, consultation/restauration
- [ ] D1–D8 : affichage TV, temps réel, auto-scroll, horloge, indicateur live, stats, jour/nuit, **reconnexion auto**
- [ ] Sécurité : secret obligatoire, cookies durcis, CSRF, rate-limit, hashing, secret hors git
- [ ] Prod : systemd + Nginx (`proxy_buffering off`, `X-Accel-Buffering: no`) + gunicorn 1 worker gthread
