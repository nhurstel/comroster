#!/bin/sh
# Lance Chromium en kiosk plein écran sur l'affichage ComRoster.
# Pointe sur 127.0.0.1 (contexte sécurisé → Screen Wake Lock actif).
# Optimisé Raspberry Pi : accélération GPU activée.
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

# X11 : couper l'économiseur d'écran / DPMS (sans effet ni erreur sous Wayland)
if [ -n "${DISPLAY:-}" ] && command -v xset >/dev/null 2>&1; then
  xset s off 2>/dev/null || true
  xset s noblank 2>/dev/null || true
  xset -dpms 2>/dev/null || true
fi

# Masquer le curseur si unclutter est présent
command -v unclutter >/dev/null 2>&1 && unclutter -idle 0 >/dev/null 2>&1 &

# Rendu : Wayland natif si la session l'est (Bookworm/labwc), sinon réglages X11.
# --use-gl=egl (ancien) demande « gl=none » et casse le GPU sur Chromium récent → retiré.
if [ "${XDG_SESSION_TYPE:-}" = "wayland" ] || [ -n "${WAYLAND_DISPLAY:-}" ]; then
  RENDER_FLAGS="--ozone-platform=wayland"
else
  RENDER_FLAGS="--enable-gpu-rasterization --ignore-gpu-blocklist"
fi

exec "$CHROME" \
  --kiosk --incognito --start-fullscreen \
  --noerrordialogs --disable-infobars --disable-session-crashed-bubble \
  --no-first-run --fast --fast-start \
  --check-for-update-interval=31536000 \
  --disable-pinch --overscroll-history-navigation=0 \
  --autoplay-policy=no-user-gesture-required \
  --password-store=basic \
  --disable-features=Translate,TranslateUI \
  $RENDER_FLAGS \
  --user-data-dir="$PROFILE" \
  "$URL"
