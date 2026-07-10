#!/usr/bin/env bash
#
# Désinstalle proprement ComRoster d'un Raspberry Pi — inverse de setup-pi.sh.
# Arrête et retire les services système (serveur, réseau, kiosk cage, agent), la
# config, le profil kiosk et restaure le boot. Les données (instance/) et le dépôt
# sont conservés par défaut.
#
#     sudo deploy/uninstall-pi.sh
#
# Idempotent : fonctionne quel que soit le rôle installé (autonome/serveur/afficheur)
# et même si certains éléments sont déjà absents.
set -euo pipefail

# --- Contexte -------------------------------------------------------------
[ "$(id -u)" -eq 0 ] || { echo "Lancer avec sudo : sudo deploy/uninstall-pi.sh"; exit 1; }
TARGET_USER="${SUDO_USER:-pi}"
TARGET_HOME="$(getent passwd "$TARGET_USER" | cut -d: -f6)"
APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DATA_DIR="$APP_DIR/instance"
ENV_FILE="/etc/comroster.env"

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

# --- 1. Services système (tous : serveur, réseau, kiosk cage, agent) ------
echo "▶ Arrêt et suppression des services…"
systemctl disable --now comroster.service comroster-network.service \
  comroster-kiosk.service comroster-viewer.service 2>/dev/null || true
rm -f /etc/systemd/system/comroster.service \
      /etc/systemd/system/comroster-network.service \
      /etc/systemd/system/comroster-kiosk.service \
      /etc/systemd/system/comroster-viewer.service
systemctl daemon-reload
# Réactive la console sur tty1 (cage la prenait via Conflicts=getty@tty1)
systemctl enable getty@tty1.service 2>/dev/null || true

# --- 2. Configuration + profil kiosk -------------------------------------
echo "▶ Suppression de la configuration…"
rm -f "$ENV_FILE"
rm -rf "$TARGET_HOME/.comroster-kiosk"

# --- 3. Restauration du boot (annule quiet-boot.sh) ----------------------
echo "▶ Restauration du boot (config.txt / cmdline.txt)…"
for f in /boot/firmware/config.txt /boot/config.txt \
         /boot/firmware/cmdline.txt /boot/cmdline.txt; do
  [ -f "$f.comroster.bak" ] && mv "$f.comroster.bak" "$f"
done

# --- 4. Données -----------------------------------------------------------
if $KEEP_DATA; then
  echo "▶ Données CONSERVÉES : $DATA_DIR"
else
  echo "▶ Suppression des données : $DATA_DIR"
  rm -rf "$DATA_DIR"
fi

echo ""
echo "✅ ComRoster désinstallé (rôle quelconque)."
echo "   • Dépôt et venv CONSERVÉS ($APP_DIR) — supprime-les à la main si besoin :"
echo "       rm -rf \"$APP_DIR\""
echo "   • Paquets apt (cage, chromium…) conservés : à retirer toi-même si dédiés :"
echo "       sudo apt purge cage chromium-browser"
