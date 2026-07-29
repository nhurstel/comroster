#!/bin/sh
# Lance Chromium en kiosk plein écran sur l'affichage ComRoster.
# Prévu pour être lancé par cage (Wayland mono-app) : `cage -- kiosk-run.sh`.
# Pointe sur 127.0.0.1 (contexte sécurisé → Screen Wake Lock possible).
set -eu

ROLE="${COMROSTER_ROLE:-autonomous}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Version gravée au déploiement. Le splash s'ouvre en file:// AVANT que le serveur
# réponde : il ne peut rien demander à personne, la version doit lui arriver par l'URL —
# comme `next` et `health`.
#
# `+`, `&` et `#` DOIVENT être encodés : dans une chaîne de requête `+` se décode en
# espace (« v1.4.0+7 » s'afficherait « v1.4.0 7 »), et `&`/`#` sont légaux dans un nom
# de tag git mais couperaient le paramètre d'URL (nouveau paramètre / fragment) —
# tronquant la version affichée. sed et non substitution bash : on est en sh.
ver=""
VERSION_FILE="$SCRIPT_DIR/../comroster/VERSION"
if [ -r "$VERSION_FILE" ]; then
  # Piège POSIX n°1 : `read` renvoie un code d'échec quand la DERNIÈRE ligne du
  # fichier n'a pas de saut de ligne final — mais `ver` est quand même correctement
  # assignée avant ce code d'échec. `|| ver=""` écraserait donc une valeur pourtant
  # bonne ; `|| true` se contente d'avaler le code de sortie sans toucher `ver`.
  # Piège POSIX n°2 : sous `set -eu`, un `read` qui échoue SANS ce `|| true` termine
  # le script — le kiosk n'ouvrirait rien du tout, écran noir en régie.
  read -r ver _ < "$VERSION_FILE" || true
  ver=$(printf '%s' "$ver" | sed 's/+/%2B/g; s/&/%26/g; s/#/%23/g')
fi

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
  URL="file://$SCRIPT_DIR/boot-splash.html?next=$TARGET&health=$HEALTH&v=$ver"
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
