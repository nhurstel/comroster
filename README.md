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
(hashing) · SSE (`EventSource`) · drag-and-drop HTML5 natif (zéro dépendance JS) ·
trois apparences d'écran commutables × deux modes de luminosité · pytest. Persistance
par fichiers JSON plats avec écriture atomique. Aucun SGBD.

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
| `COMROSTER_ANTENNA_TIMEOUT` | Délai (s) des requêtes vers l'antenne Bolero | `5` |
| `COMROSTER_BIND` | Adresse:port d'écoute gunicorn (mettre `0.0.0.0:8080` en Pi autonome) | `127.0.0.1:8080` |
| `COMROSTER_INSECURE_COOKIE` | Désactive le flag `Secure` du cookie (LAN fermé sans TLS) — **sans** activer le debug | `false` |

Générer une clé : `python -c "import secrets; print(secrets.token_hex(32))"`.

## Lancement

**Développement** (le plus simple) :
```bash
./run-dev.sh
```
Le script active `FLASK_DEBUG=true` : la factory fournit alors une clé de session de dev
et désactive le flag `Secure` du cookie (nécessaire en HTTP local). Équivalent manuel :
```bash
FLASK_DEBUG=true DATA_DIR=./instance python app.py
```
> Sans `FLASK_DEBUG` ni `FLASK_SECRET_KEY`, l'app **refuse de démarrer** (garde prod voulue).

**Production (un seul worker — le broker SSE est en mémoire) :**
```bash
FLASK_SECRET_KEY=<clé> DATA_DIR=/opt/comroster/instance \
  .venv/bin/gunicorn -c gunicorn.conf.py app:app
```
Derrière Nginx : voir [deploy/nginx.conf](deploy/nginx.conf) — `proxy_buffering off` sur
`/events` est **indispensable** au SSE. Service systemd : [deploy/comroster.service](deploy/comroster.service).

> **HTTPS requis en prod.** Le cookie de session est marqué `Secure` : sans TLS, la connexion
> admin échoue silencieusement. La config Nginx fournie redirige 80 → 443 et termine le TLS.
> Sur un LAN de régie fermé sans certificat, lancer gunicorn avec `FLASK_DEBUG=true` désactive
> le flag `Secure` (à réserver à ce cas).

Le mot de passe de l'antenne Bolero est **chiffré au repos** (Fernet, clé dérivée de
`FLASK_SECRET_KEY`) dans `antenna.json` — dépendance `cryptography`. Changer la clé de session
rend les identifiants antenne illisibles (ils sont alors ignorés, sans erreur).

### Raspberry Pi (mode appliance)

Cible de déploiement principale. Installation **en une commande** d'un Pi autonome
(serveur + affichage kiosk, démarrage auto au boot, relance auto) :

```bash
git clone <url> ~/comroster && cd ~/comroster
sudo deploy/setup-pi.sh && sudo reboot
```

Guide complet (prérequis, admin sur le LAN, mise à jour, robustesse) :
**[deploy/raspberry-pi.md](deploy/raspberry-pi.md)**.

Le `/display` est optimisé pour ce matériel : polices **auto-hébergées** (aucun appel CDN,
hors-ligne), auto-scroll en `transform` **composé GPU** (pas de repaint CPU continu),
**anti-veille** (Screen Wake Lock + blanking OS). Détails kiosk : [deploy/kiosk.md](deploy/kiosk.md).

Flags utiles en appliance : `COMROSTER_BIND` (défaut `127.0.0.1:8080`) et
`COMROSTER_INSECURE_COOKIE` (désactive le cookie `Secure` pour un LAN fermé sans TLS).

## Premier démarrage

1. Ouvrir `/admin/setup` → définir le mot de passe admin (4 caractères min.).
2. **Noter le code de récupération** affiché une seule fois (sert à réinitialiser le mot de passe).
3. `/admin` : créer les groupes (canaux), ajouter les beltpacks (n° + rôle),
   glisser-déposer dans les groupes, puis **Envoyer à l'affichage**.
4. Ouvrir `/display` sur l'écran de régie — mise à jour en direct à chaque publication.

## Apparences de l'écran

`/display` se décline en trois **apparences** (réglage « Apparence » dans l'admin), chacune
disponible en mode sombre et clair. Le choix est stocké dans l'état publié : il change à chaud,
sans recharger l'écran de régie.

| Valeur | Nom | Parti pris |
|--------|-----|-----------|
| `basique` | Basique | **Défaut.** Cartes en verre dépoli, accent turquoise, capitales. |
| `lineaire` | Linéaire | Tableau réglé, à-plat. La couleur du groupe se limite au bandeau de tête. Rôles nettement plus gros (pas de cadre à financer). |
| `grille` | Grille | Mosaïque pleine : le groupe **est** une surface colorée. Le plus lisible de loin. |

Techniquement : un attribut `data-skin` sur `<body>` ; `basique` vit dans
[display.css](static/css/display.css), les autres dans [skins.css](static/css/skins.css). Les
feuilles sont toutes chargées en permanence, puisque l'apparence peut changer en direct par SSE.

> **`grille` pose du texte sur la couleur du groupe.** L'encre (noire ou blanche) est choisie au
> rendu d'après la luminance relative sRGB. Pour garantir la lisibilité, le choix de couleur d'un
> groupe se fait dans une **palette bornée** de 24 teintes calibrées (contraste ≥ 4.5:1 avec l'encre
> dans les deux modes de luminosité) — pas un sélecteur libre, qui laissait choisir des teintes
> médiocres. La règle d'encre est partagée par l'écran et l'admin ([ink.js](static/js/ink.js)).

**Aperçu** — un **témoin permanent** en surimpression, coin bas-droit, montre l'état **publié** et
se rafraîchit à chaque publication. À cette taille le texte est illisible par construction : on y
lit la structure (colonnes, couleurs de groupes, densité), pas le contenu. Cliquer dessus ouvre le
grand aperçu ; un clic à côté le referme. Le bandeau replie le témoin, et ce choix est mémorisé.

Les deux sont des iframes sur `/admin/preview`, c'est-à-dire la vraie page display à l'échelle —
aucun rendu parallèle, donc aucune dérive possible. Ni l'une ni l'autre n'ouvre de flux SSE
(voir ci-dessous).

> **L'aperçu est rendu en 1920×1080**, la résolution du kiosk Pi. En colonnes « Automatique », leur
> nombre dépend de la largeur en pixels (`minmax(340px, 1fr)`) : un aperçu ne peut donc être fidèle
> qu'à **une** résolution. Si votre écran de régie n'est pas en 1080p, fixez le nombre de colonnes
> — le rendu devient alors indépendant de la largeur, et l'aperçu exact partout.

## Parcours & routes

- `/admin/setup`, `/admin/login`, `/admin/recover` — comptes (public).
- `/admin` + `/api/*` — administration (session requise, CSRF sur les requêtes mutatives).
- `/admin/preview` — aperçu de l'état **publié**, session requise. Rend `display.html` avec
  `data-preview="on"` : le JS y coupe le SSE, les sondages, l'anti-veille et le défilement.
  `?scroll=1` rétablit le défilement (grand aperçu seulement — le témoin permanent reste immobile).
  Chaque flux `/events` occupe un thread et un créneau de `COMROSTER_SSE_MAX` (12 par défaut) —
  un aperçu laissé ouvert affamerait les vrais afficheurs.
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

Dépendances de dev (hors `requirements.txt`) : voir [requirements-dev.txt](requirements-dev.txt).
```bash
.venv/bin/pip install -r requirements-dev.txt
```

**Tests unitaires / intégration** (rapides, sans navigateur) :
```bash
.venv/bin/pytest -q
```

**Tests bout-en-bout** (navigateur Playwright headless, marqueur `e2e`, exclus par défaut) :
```bash
.venv/bin/playwright install chromium      # une fois : télécharge le navigateur
.venv/bin/pytest tests/e2e -m e2e
```
Ils démarrent un vrai serveur et valident le parcours complet (configuration → groupe →
beltpack → publication → affichage TV) dans un vrai navigateur.
