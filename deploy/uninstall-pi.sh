#!/usr/bin/env bash
#
# Désinstalle proprement ComRoster d'un Raspberry Pi — inverse de setup-pi.sh.
# Arrête et retire les services (système + utilisateur), la config et le profil
# kiosk. Les données (instance/) et le dépôt lui-même sont conservés par défaut.
#
#     sudo deploy/uninstall-pi.sh
#
# Idempotent : fonctionne quel que soit le rôle installé (autonome/serveur/afficheur)
# et même si certains éléments sont déjà absents.
set -euo pipefail

# --- Contexte -------------------------------------------------------------
[ "$(id -u)" -eq 0 ] || { echo "Lancer avec sudo : sudo deploy/uninstall-pi.sh"; exit 1; }
TARGET_USER="${SUDO_USER:-pi}"
TARGET_UID="$(id -u "$TARGET_USER")"
TARGET_HOME="$(getent passwd "$TARGET_USER" | cut -d: -f6)"
APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DATA_DIR="$APP_DIR/instance"
ENV_FILE="/etc/comroster.env"
KIOSK_DIR="$TARGET_HOME/.config/systemd/user"

run_user() {
  sudo -u "$TARGET_USER" XDG_RUNTIME_DIR="/run/user/$TARGET_UID" "$@"
}

echo "▶ Désinstallation de ComRoster (utilisateur : $TARGET_USER, dépôt : $APP_DIR)"
echo "  → arrêt et suppression des services, de $ENV_FILE et du profil kiosk."
printf "Confirmer ? Tapez 'oui' : "
if read -r CONFIRM </dev/tty 2>/dev/null; then :; else CONFIRM=""; fi
[ "$CONFIRM" = "oui" ] || { echo "Annulé — rien n'a été touché."; exit 0; }

# Conserver les données (mot de passe admin, config antenne, historique, réseau) ?
KEEP_DATA=true
printf "Conserver les données (%s) ? [O/n] : " "$DATA_DIR"
if read -r ANS </dev/tty 2>/dev/null; then
  case "$ANS" in [nN]*) KEEP_DATA=false ;; esac
fi

# --- 1. Services système --------------------------------------------------
echo "▶ Arrêt des services système…"
systemctl disable --now comroster.service comroster-network.service 2>/dev/null || true
rm -f /etc/systemd/system/comroster.service /etc/systemd/system/comroster-network.service
systemctl daemon-reload

# --- 2. Services utilisateur (kiosk + agent afficheur) --------------------
echo "▶ Arrêt des services utilisateur…"
run_user systemctl --user disable --now comroster-kiosk.service comroster-viewer.service 2>/dev/null || true
rm -f "$KIOSK_DIR/comroster-kiosk.service" "$KIOSK_DIR/comroster-viewer.service"
run_user systemctl --user daemon-reload 2>/dev/null || true

# --- 3. Configuration + profil kiosk -------------------------------------
echo "▶ Suppression de la configuration…"
rm -f "$ENV_FILE"
rm -rf "$TARGET_HOME/.comroster-kiosk"

# --- 4. Données -----------------------------------------------------------
if $KEEP_DATA; then
  echo "▶ Données CONSERVÉES : $DATA_DIR"
else
  echo "▶ Suppression des données : $DATA_DIR"
  rm -rf "$DATA_DIR"
fi

# --- 5. Maintien de session utilisateur (linger) -------------------------
# Plus aucun service --user ComRoster : on retire le linger posé par setup-pi.sh.
loginctl disable-linger "$TARGET_USER" 2>/dev/null || true

echo ""
echo "✅ ComRoster désinstallé (rôle quelconque)."
echo "   • Dépôt et venv CONSERVÉS ($APP_DIR) — supprime-les à la main si besoin :"
echo "       rm -rf \"$APP_DIR\""
echo "   • Paquets apt (chromium, unclutter…) conservés : partagés, à retirer toi-même si dédiés :"
echo "       sudo apt purge chromium-browser unclutter"
echo "   • Autologin bureau inchangé : sudo raspi-config → System → Boot pour le modifier."
