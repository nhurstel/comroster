#!/bin/sh
# Lance Chromium en kiosk plein écran sur l'affichage ComRoster.
# Prévu pour être lancé par cage (Wayland mono-app) : `cage -- kiosk-run.sh`.
# Pointe sur 127.0.0.1 (contexte sécurisé → Screen Wake Lock possible).
set -eu

ROLE="${COMROSTER_ROLE:-autonomous}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ "$ROLE" = "viewer" ]; then
  # Afficheur : le kiosk ouvre l'agent local, qui teste le serveur distant et
  # bascule (display distant ou page de config). Attente de l'agent, pas du serveur.
  URL="${COMROSTER_KIOSK_URL:-http://127.0.0.1:8081/}"
  HEALTH="${COMROSTER_HEALTH_URL:-http://127.0.0.1:8081/api/server-status}"
  WAIT_SERVER=1
else
  # Splash « Booting ComRoster » affiché immédiatement (écran noir façon terminal) ;
  # il bascule tout seul vers le display dès que le serveur répond → pas d'écran de
  # bureau ni de page d'erreur pendant que gunicorn démarre.
  TARGET="${COMROSTER_KIOSK_URL:-http://127.0.0.1:8080/display}"
  HEALTH="${COMROSTER_HEALTH_URL:-http://127.0.0.1:8080/healthz}"
  URL="file://$SCRIPT_DIR/boot-splash.html?next=$TARGET&health=$HEALTH"
  WAIT_SERVER=0
fi
PROFILE="${HOME}/.comroster-kiosk"

# Binaire Chromium (Bookworm = chromium, anciens = chromium-browser)
CHROME="$(command -v chromium 2>/dev/null || command -v chromium-browser 2>/dev/null || true)"
[ -n "$CHROME" ] || { echo "Chromium introuvable (apt install chromium-browser)"; exit 1; }

# Attendre que le serveur réponde (le kiosk ne doit jamais afficher d'erreur au boot)
# En mode afficheur on attend l'agent local ; en autonome, c'est le splash qui
# patiente et bascule (Chromium démarre tout de suite pour l'écran noir immédiat).
if [ "$WAIT_SERVER" = "1" ]; then
  echo "Attente du serveur…"
  until curl -sf "$HEALTH" >/dev/null 2>&1; do sleep 1; done
fi

# cage fournit un affichage Wayland → Chromium en Ozone/Wayland natif.
# (Pas de xset/unclutter : c'étaient des outils X11, inutiles sous cage.)
exec "$CHROME" \
  --kiosk --incognito --start-fullscreen \
  --ozone-platform=wayland \
  --noerrordialogs --disable-infobars --disable-session-crashed-bubble \
  --no-first-run --fast --fast-start \
  --check-for-update-interval=31536000 \
  --disable-pinch --overscroll-history-navigation=0 \
  --autoplay-policy=no-user-gesture-required \
  --password-store=basic \
  --disable-features=Translate,TranslateUI \
  --user-data-dir="$PROFILE" \
  "$URL"
