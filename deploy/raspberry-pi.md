# Déploiement « appliance » sur Raspberry Pi (autonome)

Objectif : une carte SD → au démarrage, le Pi affiche `/display` en plein écran, et
**ça ne s'arrête jamais** (relance auto serveur + kiosk). Chaque Pi est **autonome**
(serveur + affichage sur la même machine, indépendant des autres).

```
Raspberry Pi
├─ gunicorn (serveur : admin + antenne + données)   ← service système, boot
└─ Chromium kiosk → http://127.0.0.1:8080/display    ← service utilisateur, session graphique
```

> **Distribution clé-en-main ?** Pour livrer des boîtiers prêts à brancher (image SD
> pré-faite + carte de démarrage dans le carton), voir [build-image.md](build-image.md) et
> [quick-start-card.html](quick-start-card.html). Au branchement, l'écran affiche un guide
> avec QR code — le client n'a aucune commande à taper.

## Prérequis

- **Raspberry Pi OS Bookworm 64-bit _Desktop_** (le kiosk a besoin d'un environnement graphique).
- Réseau local (pour administrer depuis un téléphone/laptop). Pas besoin d'Internet en exploitation.
- Pi 3B+ minimum recommandé (le Pi 4 / 5 reste plus confortable pour Chromium).

## Installation en une commande

```bash
git clone <url-du-dépôt> ~/comroster
cd ~/comroster
sudo deploy/setup-pi.sh
sudo reboot
```

C'est tout. Au redémarrage, l'écran affiche ComRoster automatiquement.

### Ce que fait `setup-pi.sh`

1. Installe les paquets (`python3-venv`, `chromium-browser`, `unclutter`, `curl`).
2. Crée le venv et installe `requirements.txt`.
3. Génère une **clé de session** et écrit `/etc/comroster.env` (droits 600) avec :
   - `COMROSTER_BIND=0.0.0.0:8080` (admin accessible sur le LAN),
   - `COMROSTER_INSECURE_COOKIE=true` (LAN fermé sans TLS — voir note sécurité).
4. Installe et active le **service serveur** `comroster.service` (`Restart=on-failure`).
5. Installe le **service kiosk** utilisateur (`comroster-kiosk.service`) qui lance
   [kiosk-run.sh](kiosk-run.sh) : attente de `/healthz`, puis Chromium kiosk avec
   accélération GPU, anti-veille et curseur masqué.
6. Active l'**autologin bureau** et le *linger* utilisateur (le kiosk démarre au boot,
   sans clavier ni intervention).

Le script est **idempotent** : on peut le relancer après une mise à jour du code.

## Utilisation

- **Affichage** : automatique sur l'écran du Pi.
- **Administration** : depuis un appareil du même réseau → `http://<ip-du-pi>:8080/admin`
  (le script affiche l'IP à la fin). Premier accès : `/admin/setup` pour créer le mot de passe.

L'IP du Pi : `hostname -I`. Pour une IP stable, réserver un bail DHCP ou fixer l'adresse.

## Mise à jour

```bash
cd ~/comroster && git pull
sudo deploy/setup-pi.sh          # réinstalle deps + services (config conservée)
sudo systemctl restart comroster
sudo reboot                      # ou: systemctl --user restart comroster-kiosk
```

## Robustesse (« ça s'arrête plus »)

- `Restart=on-failure` sur le serveur **et** le kiosk → relance auto après un crash.
- Le kiosk **attend** `/healthz` avant d'afficher : pas d'écran d'erreur si le serveur
  démarre un peu après.
- **Coupures de courant** : pour éviter toute corruption de la carte SD, envisager le mode
  **overlayfs en lecture seule** (`raspi-config` → Performance → Overlay File System).
  Dans ce cas, garder `DATA_DIR` sur une partition inscriptible si l'admin doit persister
  entre redémarrages, ou accepter un état volatil.

## Configuration réseau — Filaire ou Wi-Fi

Le boîtier rejoint le réseau intercom **au choix, de façon pérenne** (admin → bouton
**Réseau** → « Liaison ») :

### Filaire (RJ45) — défaut
Pensé pour une **infra à base de switchs (sans routeur, donc sans DHCP)**. Par défaut, le
boîtier utilise une adresse **link-local** auto-assignée et reste joignable via
`comroster.local` (mDNS) — l'écran de bienvenue affiche aussi l'adresse exacte.
Modes disponibles : link-local / DHCP / IP fixe (passerelle et DNS facultatifs).
En mode filaire, la **radio Wi-Fi est coupée** au boot (pas d'émission parasite en régie).

### Wi-Fi (point d'accès du réseau intercom)
Le boîtier s'associe à un AP relié au réseau intercom : **SSID + mot de passe WPA2**,
adresse en **DHCP ou IP fixe** (IP fixe recommandée si le réseau n'a pas de DHCP — l'AP
n'est alors qu'un pont). En mode Wi-Fi, **la prise RJ45 reste un port de service
permanent** (link-local) : un câble direct entre un ordinateur et le boîtier permet
toujours d'ouvrir l'admin (`comroster.local`), pour la première configuration comme
pour le dépannage si le Wi-Fi est injoignable (mauvais mot de passe, AP éteint…).

**Première configuration d'un boîtier destiné au Wi-Fi :** brancher un câble RJ45 direct
PC↔boîtier → `http://comroster.local:8080/admin` → Réseau → Liaison « Wi-Fi », SSID,
mot de passe, mode IP → Enregistrer → redémarrer. Le câble peut ensuite être retiré.

**Comment ça marche (sûr par conception) :** l'admin n'écrit que le souhait dans
`instance/network.json` (le mot de passe Wi-Fi n'en ressort jamais par l'API). C'est le
service système **`comroster-network.service`** qui l'applique via `nmcli` **au
démarrage** ([apply-network.sh](apply-network.sh)) — jamais en cours de requête, donc
**pas de risque de se verrouiller** en pleine reconfiguration. Une config invalide est
rejetée avant tout appel `nmcli` : l'état réseau précédent est conservé.

> ⚠️ **À valider sur un vrai Pi.** L'application `nmcli` n'est pas testable hors matériel.
> Le formulaire, la validation et la persistance sont couverts par les tests ; l'étape
> d'application réseau doit être vérifiée sur le Pi cible (Bookworm / NetworkManager).

## Note sécurité — `COMROSTER_INSECURE_COOKIE`

Le cookie de session est marqué `Secure` par défaut (impose HTTPS). En appliance autonome
sur **LAN fermé sans TLS**, on le désactive pour que l'admin se connecte en `http://`. À
réserver à un réseau de confiance isolé. Pour un réseau exposé : déployer derrière Nginx en
HTTPS (voir [nginx.conf](nginx.conf)) et retirer `COMROSTER_INSECURE_COOKIE`.

## Dépannage

| Symptôme | Piste |
|----------|-------|
| Écran noir au boot | `systemctl --user status comroster-kiosk` ; vérifier l'autologin bureau (`raspi-config` → System → Boot/Auto Login → Desktop Autologin). |
| « Chromium introuvable » | `sudo apt install chromium-browser`. |
| Admin inaccessible sur le LAN | Vérifier `COMROSTER_BIND=0.0.0.0:8080` dans `/etc/comroster.env` puis `sudo systemctl restart comroster`. |
| Page d'erreur au lieu du display | Le serveur n'est pas prêt : `systemctl status comroster` et logs `journalctl -u comroster`. |
| L'écran s'éteint quand même | Vérifier l'anti-veille (Wake Lock sur 127.0.0.1) ; sous X11 le kiosk coupe le DPMS, sous Wayland voir [kiosk.md](kiosk.md). |

Détails kiosk avancés (flags Chromium, Wayland/X11, blanking) : [kiosk.md](kiosk.md).
