# ComRoster

Tableau d'affectation dynamique des beltpacks d'intercom (Riedel Bolero) pour spectacles
et concerts. Une **interface d'administration** prépare l'affectation (brouillon) ; un
**affichage TV temps réel** diffuse l'état **publié** vers la régie via Server-Sent Events.

Principe directeur : deux états distincts. L'admin travaille sur un brouillon ; rien
n'apparaît à l'écran tant qu'il n'a pas cliqué « Publier ».

Le **rôle** (« Régie », « Lumière »…) caractérise le **numéro de beltpack** : le système
mémorise la correspondance n° → rôle et la propose à la saisie.

## Pile technique

Python 3.12 · Flask · Flask-WTF (CSRF) · Flask-Limiter (anti-bruteforce) · Werkzeug
(hashing) · SSE (`EventSource`) · SortableJS (drag-and-drop) · pytest. Persistance par
fichiers JSON plats avec écriture atomique. Aucun SGBD.

## Installation

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Variables d'environnement

| Variable | Rôle | Défaut |
|----------|------|--------|
| `FLASK_SECRET_KEY` | Clé de session — **obligatoire en prod** (refus de démarrer sinon) | — |
| `DATA_DIR` | Répertoire des fichiers d'état | répertoire courant |
| `PORT` | Port d'écoute (dev) | `8080` |
| `FLASK_DEBUG` | Mode debug (`true`/`false`) — désactive `Secure` sur le cookie | `false` |

Générer une clé : `python -c "import secrets; print(secrets.token_hex(32))"`.

## Lancement

**Développement :**
```bash
FLASK_SECRET_KEY=dev DATA_DIR=./instance FLASK_DEBUG=true .venv/bin/python app.py
```

**Production (un seul worker — le broker SSE est en mémoire) :**
```bash
FLASK_SECRET_KEY=<clé> DATA_DIR=/opt/comroster/instance \
  .venv/bin/gunicorn -c gunicorn.conf.py app:app
```
Derrière Nginx : voir [deploy/nginx.conf](deploy/nginx.conf) — `proxy_buffering off` sur
`/events` est **indispensable** au SSE. Service systemd : [deploy/comroster.service](deploy/comroster.service).

## Premier démarrage

1. Ouvrir `/admin/setup` → définir le mot de passe admin (8 caractères min.).
2. **Noter le code de récupération** affiché une seule fois (sert à réinitialiser le mot de passe).
3. `/admin` : créer les groupes (canaux), ajouter les personnes (nom + n° beltpack + rôle),
   glisser-déposer dans les groupes, puis **Publier**.
4. Ouvrir `/display` sur l'écran de régie — mise à jour en direct à chaque publication.

## Parcours & routes

- `/admin/setup`, `/admin/login`, `/admin/recover` — comptes (public).
- `/admin` + `/api/*` — administration (session requise, CSRF sur les requêtes mutatives).
- `/display` + `/events` — affichage TV public, **lecture seule** (état publié uniquement).

## Réinitialisation totale (A6)

Mot de passe **et** code de récupération perdus : supprimer le fichier secret, l'app
repassera en configuration initiale au prochain accès.
```bash
rm /opt/comroster/instance/admin_secret.json
```

## Fichiers d'état (non versionnés)

`data_draft.json` (brouillon), `data_published.json` (publié), `admin_secret.json`
(hash, permissions 600), `history/` (snapshots horodatés des publications). Tous listés
dans `.gitignore`.

## Tests

```bash
.venv/bin/pytest -q
```
