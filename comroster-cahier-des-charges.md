# ComRoster — Cahier des charges fonctionnel

Tableau d'affectation dynamique des beltpacks d'intercom (Riedel Bolero) pour spectacles
et concerts. Application web séparant une **interface d'administration**
(préparation/édition) d'un **affichage temps réel** (écran de régie).

> **Mise à jour du 2026-08-11.** Ce document datait du 19 juin 2026, premier jour du
> projet, et n'avait jamais été retouché : il décrivait un logiciel que ComRoster n'est
> plus. Le champ `nom` avait disparu du modèle, le minimum de mot de passe était faux,
> la bibliothèque de glisser-déposer annoncée n'a jamais été utilisée, et six routes y
> figuraient là où le produit en sert soixante-trois.
>
> Chaque affirmation vérifiable a été confrontée au code avant d'être laissée en place —
> longueurs, champs de formulaire, routes, valeurs par défaut, noms de fichiers. Les
> sections marquées **§ d'origine** conservent l'intention initiale, qui garde sa valeur
> même quand la réalisation l'a dépassée ; le reste décrit ce qui EXISTE.
>
> La cartographie des routes fait foi dans `app.url_map`, jamais ici : une liste tenue à
> la main dérive dès la route suivante.

---

## 1. Contexte & objectif — § d'origine, toujours exact

L'outil permet à un régisseur de définir qui porte quel beltpack d'intercom, de regrouper
les personnes par équipe/canal, puis de **publier** cet état vers un écran visible par
toute l'équipe technique. La publication est un acte explicite : l'admin travaille sur un
brouillon, puis pousse l'état validé vers l'affichage.

Principe directeur : **deux états distincts** — l'état de travail (admin) et l'état publié
(display). Rien n'apparaît à l'écran tant que l'utilisateur n'a pas publié.

**Ce que le projet est devenu.** L'objectif initial est atteint et dépassé : ComRoster
n'est plus seulement une application web, c'est un **boîtier** (appliance Raspberry Pi)
qu'on branche à un écran et qu'on administre depuis un navigateur du réseau. Cela déplace
plusieurs exigences — un plantage n'a pas de développeur pour le relever, la mise à jour
se fait sans clavier, et l'écran doit revenir seul après une coupure de courant.

---

## 2. Acteurs — § d'origine, toujours exact

| Acteur | Accès | Rôle |
|--------|-------|------|
| Administrateur | Authentifié (mot de passe) | Crée/modifie groupes et beltpacks, affecte, publie |
| Régie (écran) | Public, lecture seule | Consulte l'affectation publiée en temps réel |

---

## 3. Modèle de données

### 3.1 Beltpack (`people`)
- `id` — identifiant unique
- `role` — la fonction tenue (« Régie générale », « Poursuite cour »…)
- `beltpack` — le numéro du boîtier Bolero, **unique**
- `group_id` — affectation courante, `null` ⇒ réserve (non affecté)

> **Il n'y a pas de champ `nom`, et c'est une décision.** Le document d'origine en
> prévoyait un ; il a été retiré parce qu'en régie on ne cherche jamais une personne, on
> cherche une FONCTION : « qui est sur le 22 » se répond par « poursuite jardin ». Le rôle
> caractérise le numéro de beltpack, et le système mémorise cette correspondance
> (`beltpack_roles`) pour la proposer à la saisie suivante.

### 3.2 Groupe (`groups`)
- `id`, `name`, `color` (teinte prise dans une **palette bornée** de 24 valeurs), `order`
- `manual_order` — faux : les membres sont triés par numéro ; vrai : l'ordre du tableau
  fait foi, parce que quelqu'un les a rangés à la main

### 3.3 État global
Au-delà des groupes et des beltpacks, l'état porte tout ce qui décide du rendu à l'écran :

`version` · `updated_at` · `title` · `subtitle` · `production_name` · `theme`
(`night`/`day`) · `skin` (`basique`/`lineaire`/`grille`) · `text_scale` · `indicators`
(voyant réseau, batterie) · `perf` (mode performance) · `columns` (0 = automatique) ·
`groups` · `people` · `beltpack_roles`

> Toute addition à cette liste doit être reportée dans l'allowlist partagée `DRAFT_FIELDS`
> côté client, faute de quoi un export-réimport efface le champ en silence. Un test
> confronte cette liste au modèle serveur pour que l'oubli casse la suite plutôt que les
> données.

### 3.4 Persistance (fichiers plats, tous dans `DATA_DIR`)

| Fichier | Contenu |
|---------|---------|
| `data_draft.json` | état de travail (brouillon) |
| `data_published.json` | état publié, ce que `/display` diffuse |
| `admin_secret.json` | hash du mot de passe + du code de récupération |
| `settings.json` | réglages du boîtier (hors brouillon) |
| `antenna.json` | configuration de l'antenne Bolero |
| `network.json` | configuration réseau — **contient le PSK Wi-Fi en clair** |
| `viewer.json` | configuration de l'agent afficheur |
| `journal.jsonl` | journal des évènements |
| `lifetime.json` | compteurs de vie du boîtier |
| `history/` | snapshots horodatés des publications |
| `configs/` | configurations nommées, réutilisables d'un spectacle à l'autre |

> **Tous sont exclus du versionnement**, et ce n'est pas une liste tenue à la main : un
> test interroge les SERVICES (`storage.draft_path`, `journal.path`…) puis délègue le
> verdict à `git check-ignore`. `DATA_DIR` vaut le répertoire courant par défaut, donc ces
> fichiers atterrissent à la racine du dépôt quand on lance sans le définir.

---

## 4. Fonctions par module

### 4.1 Authentification & sécurité

| # | Fonction | État |
|---|----------|------|
| A1 | Configuration initiale — `/admin/setup` impose un mot de passe (**4 caractères minimum**) | fait |
| A2 | Code de récupération affiché **une seule fois** à la création | fait |
| A3 | Connexion `/admin/login` (hash Werkzeug, session chiffrée) | fait |
| A4 | Déconnexion | fait |
| A5 | Mot de passe oublié → réinitialisation par le code de récupération | fait |
| A6 | Reset total : suppression de `admin_secret.json` | fait |
| A7 | Toutes les routes admin exigent une session valide | fait |
| A8 | Changement de mot de passe depuis l'administration (`/admin/password`) | fait |

> **4 et non 8.** Le document d'origine annonçait 8 caractères. Le minimum a été abaissé à
> 4 le 2026-07-06 : le boîtier vit sur un réseau de production fermé, et un mot de passe
> long tapé sur un téléphone en pleine mise en place est un mot de passe noté sur un
> gaffer. La règle est imposée sur **tous** les chemins d'écriture — setup, récupération et
> changement — parce qu'elle n'existait d'abord que sur le premier.

### 4.2 Groupes

| # | Fonction | État |
|---|----------|------|
| G1–G3 | Créer, renommer, recolorer | fait |
| G4 | Supprimer — **les membres repassent en réserve**, jamais supprimés avec le groupe | fait |
| G5 | Ordonner les groupes | fait |
| G6 | Couleur prise dans une palette bornée de 24 teintes calibrées (contraste ≥ 4,5:1) | fait |

### 4.3 Beltpacks

| # | Fonction | État |
|---|----------|------|
| P1 | Ajouter — **numéro + rôle**, groupe optionnel (pas de nom, cf. 3.1) | fait |
| P2 | Modifier | fait |
| P4 | Supprimer — à l'unité ou par lot | fait |
| P5–P7 | Affecter, déplacer, retirer — **glisser-déposer HTML5 natif** | fait |
| P8 | **Unicité du numéro, blocage dur** — rejet, pas avertissement | fait |
| P9 | Vue Tableau, tri par colonne, sélection multiple (MAJ+clic, ⌘A) et réaffectation en lot | fait |
| P10 | Filtre sur numéro, rôle ou groupe | fait |
| P11 | Annuler / rétablir (⌘Z, ⌘⇧Z), **bornés au brouillon** | fait |

> Le rôle est **proposé** à la saisie d'un numéro déjà connu, et la proposition reste
> vivante tant que l'utilisateur n'a pas pris la main sur le champ.

### 4.4 Import / export & configurations

| # | Fonction | État |
|---|----------|------|
| I1–I2 | Exporter / importer l'état complet (`.rost`) | fait |
| I3 | **Configurations nommées** : enregistrer un plateau, le recharger, l'exporter, le supprimer | fait |
| I4 | **Sauvegarde du boîtier** : archive chiffrée de toute la configuration, inspection avant restauration | fait |

### 4.5 Publication

| # | Fonction | État |
|---|----------|------|
| B1 | Publier : copie du brouillon vers le publié | fait |
| B2 | Notification temps réel (SSE) | fait |
| B3 | Snapshot horodaté dans `history/` | fait |
| B4–B5 | Consulter et restaurer une publication passée, l'étiqueter | fait |
| B6 | Décompte de 5 s avant envoi, annulable ; ⌘↵ envoie immédiatement | fait |
| B7 | Témoin d'écart brouillon / publié (« N en attente » / « À jour ») | fait |

> **Concurrence : la décision d'origine a été corrigée.** Le document annonçait un
> last-write-wins sans verrou. C'était faux dès que deux requêtes se croisaient :
> l'atomicité d'ÉCRITURE ne dit rien de l'atomicité de TRANSACTION, et deux modifications
> simultanées se perdaient. Tout cycle lire-modifier-écrire est désormais sérialisé sur
> toute sa durée, au niveau du gestionnaire de requête.

### 4.6 Affichage (`/display`)

| # | Fonction | État |
|---|----------|------|
| D1 | Rendu lisible à distance, optimisé grand écran | fait |
| D2 | Mise à jour temps réel par SSE, sans rechargement | fait |
| D3 | Défilement automatique (délai initial, pauses, vitesse) | fait |
| D4 | Horloge | fait |
| D5 | Témoin « En direct » | fait |
| D6 | Compteurs groupes / beltpacks (apparence `basique` seule) | fait |
| D7 | Mode jour / nuit | fait |
| D8 | Reconnexion SSE et resynchronisation automatiques | fait |
| D9 | **Trois apparences** commutables à chaud : `basique`, `lineaire`, `grille` | fait |
| D10 | Ajustement automatique du texte, échelle réglable, nombre de colonnes | fait |
| D11 | Transition d'arrivée à la publication — supprimée en mode performance, jamais jouée sur un simple `snapshot` | fait |
| D12 | Anti-veille (Screen Wake Lock) | fait |
| D13 | Guide d'accueil + QR sur boîtier neuf | fait |
| D14 | Encre (noire/blanche) choisie au rendu selon la luminance du groupe | fait |

### 4.7 Modules ajoutés depuis le document d'origine

| # | Module | Ce qu'il fait |
|---|--------|---------------|
| E1 | **Aperçu** | Témoin permanent de l'état publié dans l'admin, et grand aperçu — deux iframes sur la vraie page display, rendues à 1920×1080, sans aucun flux SSE |
| E2 | **Impression** | Feuille de service A3/A4, pagination, couleurs de groupe, mode monochrome |
| E3 | **Journal** | Évènements du boîtier et volet technique, consultables sans SSH |
| E4 | **Contrôle avant show** | Répond en clair à « puis-je lancer le show ? », preuves triées par gravité |
| E5 | **Antenne Bolero** | Découverte réseau, connexion, import des beltpacks depuis l'antenne |
| E6 | **Réseau** | IP fixe ou DHCP, scan Wi-Fi, application à chaud |
| E7 | **Marque blanche** | Logo et nom du client posés sur le boîtier |
| E8 | **Kiosk** | Raspberry Pi OS Lite + `cage` : l'écran revient seul après coupure |
| E9 | **Version visible** | La version tourne sur le splash de démarrage et dans l'administration |

---

## 5. Paramètres configurables

Variables d'environnement réellement lues par `config.py` :

```
FLASK_SECRET_KEY            clé de session — OBLIGATOIRE en production
DATA_DIR                    répertoire des fichiers d'état (défaut : répertoire courant)
PORT                        port d'écoute (défaut 8080)
FLASK_DEBUG                 mode debug (désactive aussi le cookie Secure)
COMROSTER_BRAND_DIR         pack de marque blanche
COMROSTER_INSECURE_COOKIE   autorise le cookie hors HTTPS (jamais en production)
COMROSTER_BEHIND_PROXY      active ProxyFix — indispensable au rate-limit derrière nginx
COMROSTER_SSE_MAX           plafond de flux SSE simultanés (défaut 12)
```

> **`COMROSTER_BEHIND_PROXY` n'est pas un détail.** Sans lui, derrière un reverse proxy,
> toutes les requêtes semblent venir de `127.0.0.1` : le rate-limit du login devient un
> compteur partagé, et un attaquant verrouille la connexion de tout le monde. Il reste
> **opt-in** parce qu'actif par défaut il serait usurpable en accès direct.
>
> Le plafond SSE doit rester **strictement inférieur** au nombre de threads du serveur :
> chaque flux occupe un thread en continu, et sans plafond huit écrans suffisent à figer
> le boîtier entier, `/healthz` compris.

Les réglages de défilement et les couleurs de thème ne sont plus des variables
d'environnement : le défilement se règle dans l'interface, les couleurs sont des jetons
CSS.

---

## 6. Exigences non-fonctionnelles

- **Temps réel** : propagation par SSE, latence quasi nulle après publication.
- **Sécurité** : hash Werkzeug, sessions chiffrées, CSRF sur toute route mutative,
  rate-limit du login, secrets hors versionnement.
- **Robustesse appliance — fail-safe, pas fail-loud** : sur une donnée EXTERNE corrompue
  (fichier d'état illisible, réponse réseau aberrante), on récupère et on journalise ; on
  ne plante jamais. Cette tolérance ne s'applique **jamais** aux bugs de code : aucun
  catch-all autour d'un rendu ou d'une logique interne.
- **Démarrage** : `create_app()` ne doit contenir que des opérations dont l'échec est
  tolérable. Un octet corrompu ne doit pas empêcher le boîtier de démarrer.
- **Performance** : mode performance qui coupe animations et transitions.
- **Accessibilité** : contraste AA vérifié par mesure, palette bornée pour le garantir.
- **Portabilité** : Python 3.12, Flask, dépendances minimales, aucun SGBD.
- **Déploiement** : systemd + gunicorn (1 worker, gthread) ; `proxy_buffering off` si
  reverse proxy.

---

## 7. Cartographie des routes

Le produit sert **63 routes**. Les énumérer ici garantirait seulement qu'elles soient
fausses un jour : **la source de vérité est `app.url_map`**. Par famille :

| Famille | Objet |
|---------|-------|
| `/admin/*` | setup, login, logout, recover, password, administration, aperçu, impression, journal, contrôle |
| `/api/groups`, `/api/people`, `/api/draft`, `/api/state` | le brouillon |
| `/api/publish`, `/api/history/*` | publication et historique |
| `/api/configs/*` | configurations nommées |
| `/api/backup/*` | sauvegarde chiffrée du boîtier |
| `/api/antenna/*` | découverte, connexion et import Bolero |
| `/api/network/*` | IP, Wi-Fi, application |
| `/api/settings`, `/api/reboot` | réglages et redémarrage |
| `/api/journal`, `/api/logs`, `/api/health`, `/api/live`, `/api/status` | état du boîtier |
| `/display`, `/events`, `/display/qr.svg` | l'écran de régie (public, lecture seule) |
| `/branding/*` | logo de marque blanche |
| `/healthz` | sonde de santé, sans session |

Pour obtenir la liste exacte :

```bash
.venv/bin/python -c "from comroster import create_app; \
  app=create_app({'DATA_DIR':'/tmp/x','SECRET_KEY':'x'}); \
  print('\n'.join(sorted(str(r) for r in app.url_map.iter_rules())))"
```

---

## 8. Parcours utilisateur de référence — § d'origine, toujours exact

1. **Setup** → mot de passe + code de récupération noté.
2. **Préparation** → groupes (avec couleurs), ajout des beltpacks.
3. **Affectation** → glisser-déposer, ou vue Tableau pour les lots.
4. **Publication** → « Envoyer à l'affichage ».
5. **Diffusion** → l'écran de régie se met à jour instantanément.
6. **Ajustement en cours de show** → modification puis nouvelle publication.

---

## 9. Décisions de conception actées

| Sujet | Décision |
|-------|----------|
| Brouillon vs publié | **Deux fichiers.** L'admin n'écrit jamais dans le publié ; « Publier » copie l'un vers l'autre, archive, puis notifie. |
| Champ `nom` | **Supprimé.** En régie on cherche une fonction, pas une personne (cf. 3.1). |
| Suppression d'un groupe | Ses membres **retournent en réserve**, jamais supprimés. |
| Concurrence | **Sérialisation du cycle lire-modifier-écrire.** Corrige le last-write-wins d'origine, qui perdait des modifications simultanées. |
| Unicité des beltpacks | **Numéro unique, blocage dur**, validé côté serveur. Le contrôle client n'est qu'un confort. |
| Couleur de groupe | **Palette bornée** de 24 teintes, pas de sélecteur libre : c'est ce qui permet de poser du texte sur la couleur en garantissant le contraste. |
| Politique de panne | **Fail-safe sur les données externes, jamais sur le code** (cf. §6). |
| Portée de l'annulation | Le brouillon **seul** — la configuration du boîtier a ses propres endpoints. Frontière structurelle, pas liste d'exclusions. |
| Historique des publications | **Livré** (le document d'origine le classait « nice-to-have »). |
| Reconnexion SSE | Chaque (re)connexion renvoie un `snapshot` complet : la resynchronisation est résolue par construction, sans rejeu d'évènements. |

---

## 10. Réalisation

### 10.1 Pile technique

| Couche | Choix |
|--------|-------|
| Backend | **Flask**, Python 3.12 |
| Temps réel | **Server-Sent Events** — flux unidirectionnel, reconnexion native, passe les proxies |
| Persistance | **Fichiers JSON + écriture atomique**, aucun SGBD |
| Frontend admin | HTML rendu serveur + **JS vanilla**, glisser-déposer **HTML5 natif** |
| Frontend display | JS vanilla + `EventSource` |
| Hashing | Werkzeug |
| CSRF | Flask-WTF |
| Anti-bruteforce | Flask-Limiter |
| Production | Gunicorn (1 worker, gthread) + systemd |

> **SortableJS n'a jamais été utilisé**, contrairement à ce qu'annonçait le document
> d'origine : le glisser-déposer HTML5 natif suffit, et le projet revendique zéro
> dépendance JavaScript.
>
> **Un seul worker**, parce que le broker pub/sub est en mémoire : une publication traitée
> par un worker n'atteindrait jamais un écran branché sur un autre.

### 10.2 Architecture

Application factory + blueprints + services. **Quatre blueprints** (`auth`, `api`,
`display`, `antenna`) et **vingt-trois services** sous `comroster/services/` :

`storage` · `model` · `publisher` · `pubsub` · `history` · `configs` · `backup` ·
`secret` · `settings` · `journal` · `logbuffer` · `health` · `lifetime` · `version` ·
`antenna` · `discovery` · `live_poller` · `netconfig` · `netstatus` · `wifi` · `viewer` ·
`viewer_auth` · `branding`

Côté vue, six gabarits : `admin.html` (qui réunit les panneaux), `display.html`,
`print.html`, `setup.html`, `login.html`, et `auth_base.html` dont les deux derniers
héritent. Six feuilles : `main.css`, `display.css`, `skins.css`, `admin.css`, `auth.css`,
`print.css`.

Outillage : `tests/` (unitaires) et `tests/e2e/` (Playwright, un fichier par sujet),
`tools/captures.py` (captures du README), `deploy/` (installation Pi, kiosk, marque).

### 10.3 Protocoles & contrats

**Écriture atomique** — sérialiser en mémoire, écrire dans un temporaire du même
répertoire, `flush()` + `os.fsync()`, `os.replace()`, le tout sous verrou. Jamais de
fichier à moitié écrit.

**Séquence de publication** — charger le brouillon, valider (unicité, intégrité des
`group_id`), écrire atomiquement le publié, archiver dans `history/`, diffuser.

**SSE** — en-têtes `text/event-stream`, `no-cache`, `X-Accel-Buffering: no`. À la
connexion, `retry: 3000` puis un `snapshot` complet ; à chaque publication, un `published`.
Heartbeat régulier pour qu'aucun proxy ne coupe une connexion oisive. Les abonnés sont
**typés** : le total borne le pool de threads, mais seuls les écrans comptent comme
« afficheurs » — sans quoi ouvrir l'administration ferait croire qu'un écran est branché.

### 10.4 Sécurité

`FLASK_SECRET_KEY` obligatoire en production · cookie `HttpOnly`, `SameSite=Lax`,
`Secure` · CSRF sur toute requête mutative · rate-limit du login · mot de passe **et** code
de récupération hashés, fichier hors versionnement · `/display` et `/events` publics en
lecture seule, n'exposant que l'état publié.

### 10.5 Roadmap — toutes les phases sont livrées

P0 socle · P1 données & validation · P2 auth & sécurité · P3 API CRUD · P4 publication &
temps réel · P5 UI admin · P6 UI display · P7 historique · P8 durcissement & déploiement.

Le document d'origine classait la phase 7 en « nice-to-have, jetable si le temps manque » :
elle est faite, et l'historique s'étiquette. Se sont ajoutés depuis : apparences,
impression, sauvegarde chiffrée, configurations nommées, journal, contrôle avant show,
antenne Bolero, réseau, marque blanche, kiosk et version visible.

### 10.6 Démarche

- **TDD sur le critique** : atomicité du stockage, unicité du beltpack, séquence de
  publication — les points où un bug se paie en plein direct.
- **Tester les modes de panne**, pas seulement le chemin heureux.
- **Une garde se confronte à sa mutation** : un test qui ne tombe pas quand on casse ce
  qu'il surveille est un test creux, et une mutation doit fausser **une seule** propriété.
- **Mesurer plutôt que juger à l'œil**, et vérifier que la métrique mesure ce que
  l'utilisateur PERÇOIT — pour du texte, la ligne de base, jamais le centre des boîtes.
- **Les leçons sont écrites** dans `tasks/lessons.md` après chaque correction, et relues au
  démarrage. C'est le seul mécanisme qui empêche de repayer la même erreur.

### 10.7 Acceptation

Toutes les fonctions listées en §4 sont livrées et couvertes. État au 2026-08-11 :
**553 tests unitaires · 67 bout-en-bout · 43 JavaScript · lint propre**, CI verte.

Deux points restent du ressort de l'œil et non des tests : la composition de la feuille
imprimée et celle des écrans de connexion. Ils ont été jugés et validés le 2026-08-09.
