# Affichage en kiosk sur Raspberry Pi

Le Pi affiche `/display` en plein écran dans Chromium, en permanence, sans veille.
Deux niveaux complémentaires empêchent l'écran de s'éteindre :

1. **Screen Wake Lock** (déjà intégré au `display.js`) — actif si la page est servie en
   contexte sécurisé (HTTPS ou `http://127.0.0.1`). C'est pour ça qu'on pointe le kiosk sur
   **127.0.0.1** plutôt que l'IP LAN.
2. **Désactivation du blanking côté OS** (ci-dessous) — le filet de sécurité fiable.

## 1. Désactiver la veille / le blanking

### Raspberry Pi OS **Bookworm** (Wayland / labwc, par défaut)
Éditer `~/.config/labwc/autostart` (le créer si absent) :
```sh
# Pas d'extinction ni d'économiseur d'écran
swayidle -w timeout 0 '' &
```
Plus simple et robuste : désactiver l'économiseur via `~/.config/wayfire.ini` ou simplement
s'appuyer sur le Wake Lock + le flag Chromium ci-dessous. Vérifier qu'aucun `swayidle`/
`xdg-screensaver` ne tourne avec un timeout.

### Raspberry Pi OS **Bullseye** ou antérieur (X11)
Ajouter à `~/.config/lxsession/LXDE-pi/autostart` :
```
@xset s off
@xset s noblank
@xset -dpms
```

## 2. Lancer Chromium en kiosk (optimisé Pi)

Script `~/comroster-kiosk.sh` :
```sh
#!/bin/sh
# Attendre que le serveur réponde
until curl -sf http://127.0.0.1:8080/healthz >/dev/null; do sleep 1; done

exec chromium-browser \
  --kiosk --incognito --noerrordialogs --disable-infobars --no-first-run \
  --check-for-update-interval=31536000 \
  --disable-pinch --overscroll-history-navigation=0 \
  --autoplay-policy=no-user-gesture-required \
  --enable-gpu-rasterization --ignore-gpu-blocklist --use-gl=egl \
  http://127.0.0.1:8080/display
```
> Sur Pi, `--use-gl=egl --enable-gpu-rasterization --ignore-gpu-blocklist` activent
> l'accélération GPU : combiné à l'auto-scroll en `transform`, le rendu reste fluide et froid.
> Adapter l'URL si servi en HTTPS via Nginx (`https://comroster.local/display`).

## 3. Démarrage automatique

Service utilisateur systemd `~/.config/systemd/user/comroster-kiosk.service` :
```ini
[Unit]
Description=ComRoster — affichage kiosk
After=graphical-session.target
PartOf=graphical-session.target

[Service]
ExecStart=%h/comroster-kiosk.sh
Restart=on-failure
RestartSec=3

[Install]
WantedBy=graphical-session.target
```
Activer : `chmod +x ~/comroster-kiosk.sh && systemctl --user enable --now comroster-kiosk`.

## Rappel

Le **serveur** ComRoster (gunicorn) tourne via [comroster.service](comroster.service) (service
système). Le **kiosk** ci-dessus est un service *utilisateur* lié à la session graphique. Les
deux sont indépendants : le serveur peut tourner sur un autre hôte que l'écran.
