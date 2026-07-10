# Déploiement 2 Pi : serveur + afficheur — design validé (2026-07-10)

## Besoin
Permettre, à l'installation, de choisir le rôle d'un boîtier :
- **Autonome** (défaut, comportement actuel) : serveur + affichage sur le même Pi.
- **Serveur** : données + admin, sans affichage.
- **Afficheur** : écran seul (Chromium), branché sur un Pi serveur distant.

Contrainte forte : le code serveur (Flask) ne change PAS. C'est du packaging /
déploiement. Le mode Autonome reste le défaut → aucune régression pour l'existant.

## Décisions actées (Nathan)
1. **3 profils** choisis par un menu interactif dans `setup-pi.sh`.
2. L'afficheur vise le serveur par **IP saisie à l'installation** (pas de mDNS).
3. **Reconfiguration après install** possible pour les deux Pi :
   - Serveur : onglet **Réseau** de l'admin (déjà existant).
   - Afficheur : **page de config locale** servie par un petit agent (option validée).
4. Sur l'afficheur, la page de config s'affiche : si le serveur est injoignable,
   **et** via une **bannière de 5 s au boot** (option A) pour reconfigurer même
   quand tout fonctionne.

## Architecture des 3 profils

| Composant | Autonome | Serveur | Afficheur |
|-----------|----------|---------|-----------|
| `comroster.service` (Flask) | ✅ | ✅ | ❌ |
| `comroster-network.service` (réseau au boot) | ✅ | ✅ | ✅ |
| Kiosk Chromium | ✅ (→ 127.0.0.1) | ❌ | ✅ (→ serveur distant) |
| `comroster-viewer.service` (agent config) | ❌ | ❌ | ✅ |
| Bureau / Chromium requis | oui | non (Lite OK) | oui |
| Dépendances Python | complètes | complètes | complètes (Flask présent, jamais lancé) |

`setup-pi.sh` lit le profil et n'installe/active que les services voulus. Idempotent.

## Composant : agent de configuration afficheur

Petit serveur Python autonome (`comroster/viewer_agent.py`), bibliothèque standard
(`http.server`) + `segno` pour le QR + réutilisation des modules `services`
(`viewer`, `netconfig`). Il ne démarre jamais Flask/gunicorn. Service **utilisateur**
(pas root), écoute sur `0.0.0.0:8081`. ~150 lignes. Ne duplique pas le serveur
ComRoster : il ne sait faire que la config afficheur. (Note : le paquet `comroster`
importe Flask au chargement, donc l'afficheur installe les dépendances complètes ;
Flask est présent mais jamais lancé — cf. plan, Global Constraints.)

**Routes :**
- `GET /` — page de boot : bannière 5 s (« ⚙ Configurer » + QR + compte à rebours),
  logique de bascule (voir plus bas).
- `GET /api/server-status` — l'agent teste **en Python** (`urllib` vers
  `http://<ip-serveur>:8080/healthz`) et renvoie `{"reachable": bool, "display_url": "…"}`.
  Évite tout problème CORS : le navigateur interroge l'agent local (même origine).
- `GET /config` — formulaire : IP serveur visée + IP réseau propre de l'afficheur.
- `POST /config` — écrit `viewer.json` + `network.json`, répond « redémarrage requis ».
- `GET /qr.svg` — QR vers `/config` (pilotage au téléphone, comme l'accueil serveur).

**Sécurité :** l'agent est **sans authentification** (l'afficheur n'a pas de mot de
passe admin). Réservé à un réseau de régie isolé de confiance — même posture assumée
que `COMROSTER_INSECURE_COOKIE`. Documenté explicitement. Durcissement (auth) hors périmètre.

## Flux de démarrage du kiosk

`kiosk-run.sh` (profil afficheur) lance Chromium sur **la page locale de l'agent**
(`http://127.0.0.1:8081/`), pas directement sur le serveur distant. Toute la logique
vit dans la page locale (JS) + l'agent :

```
Page de boot (agent local)
  ├─ interroge GET /api/server-status (l'agent teste le serveur distant)
  ├─ affiche 5 s : « ⚙ Configurer » + QR + compte à rebours
  │     └─ action utilisateur (clic/scan) → /config
  ├─ à la fin des 5 s :
  │     ├─ serveur joignable   → navigation vers http://<ip-serveur>:8080/display
  │     └─ serveur injoignable → /config (formulaire)
```

La navigation finale vers le display distant est un `window.location` (top-level) :
pas d'iframe, donc pas de conflit avec la CSP `frame-ancestors 'self'` du serveur.

Après bascule sur le display distant, si le serveur tombe, le display gère déjà sa
reconnexion SSE. Pour revenir à la config : rebooter l'afficheur (bannière au boot)
ou couper le serveur. Cohérent avec l'option A validée.

## Données de configuration

| Fichier | Contenu | Écrit par | Appliqué par |
|---------|---------|-----------|--------------|
| `instance/viewer.json` | `{"server_ip": "...", "server_port": 8080}` | agent (user) | `kiosk-run.sh` au (re)démarrage du kiosk |
| `instance/network.json` | IP réseau du Pi (schéma NetConfig existant) | agent (user) | `apply-network.sh` (root) au boot |

Aucun accès root pour l'agent : il n'écrit que des fichiers utilisateur, appliqués
par les services système au reboot — même principe de sécurité que l'admin serveur.

## Modifications concrètes

- `deploy/setup-pi.sh` : menu de rôle ; installation conditionnelle des services
  selon le profil ; question « IP du serveur » en profil afficheur ; `segno` en
  profil afficheur.
- `deploy/kiosk-run.sh` : profil afficheur → Chromium sur l'agent local ; lecture de
  `viewer.json` pour connaître le serveur distant.
- `comroster/viewer_agent.py` (nouveau) : l'agent et ses routes.
- `deploy/comroster-viewer.service` (nouveau) : service utilisateur de l'agent.
- `deploy/raspberry-pi.md` + `deploy/aide-memoire-terrain.md` : sections 2 Pi.

## Tests
- **viewer_agent** : construction de l'URL display depuis `viewer.json` ; `/api/server-status`
  (serveur mock joignable / injoignable) ; `POST /config` écrit bien viewer.json +
  network.json et valide les IP (réutilise `netconfig.validate`) ; page de boot rendue.
- **Sans matériel** : toute la logique de l'agent est testable (serveur HTTP mocké).
- **À valider sur Pi réel** (non simulable) : menu d'install des 3 profils, bascule
  kiosk, application nmcli, bannière 5 s à l'écran.

## Hors périmètre (YAGNI)
- Pilotage des afficheurs depuis l'admin serveur.
- Authentification de l'agent afficheur.
- Découverte automatique (mDNS) du serveur.
- Bascule automatique display → config en cours de show (seulement au boot).
