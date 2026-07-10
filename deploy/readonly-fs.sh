#!/usr/bin/env bash
#
# Racine en LECTURE SEULE (overlayfs) — protège la carte SD de la corruption sur
# coupure de courant. Les écritures système vont en RAM (effacées au reboot) ;
# SEULES les données ComRoster (instance/) doivent rester sur un stockage persistant.
#
#     sudo deploy/readonly-fs.sh        # active l'overlay (avec garde-fou)
#     sudo deploy/readonly-fs.sh off    # désactive
#
# ⚠️ À VALIDER SUR UN VRAI PI. Garde-fou intégré : refuse d'activer l'overlay si
# instance/ serait volatile (sinon mot de passe admin / config seraient perdus).
set -euo pipefail

[ "$(id -u)" -eq 0 ] || { echo "Lancer avec sudo : sudo deploy/readonly-fs.sh"; exit 1; }
command -v raspi-config >/dev/null 2>&1 || { echo "raspi-config requis (Raspberry Pi OS)."; exit 1; }

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DATA_DIR="${DATA_DIR:-$APP_DIR/instance}"
ACTION="${1:-on}"

if [ "$ACTION" = "off" ]; then
  raspi-config nonint disable_overlayfs
  echo "✅ Overlay désactivé. Redémarre : sudo reboot"
  exit 0
fi

# Garde-fou : instance/ doit être sur une partition DISTINCTE de la racine,
# sinon l'overlay le rendrait volatile (données perdues à chaque reboot).
root_dev="$(stat -c %d /)"
data_dev="$(stat -c %d "$DATA_DIR" 2>/dev/null || echo "$root_dev")"
if [ "$data_dev" = "$root_dev" ]; then
  cat <<MSG
⚠️  REFUS — $DATA_DIR est sur la racine : avec l'overlay il deviendrait VOLATILE
    (mot de passe admin, config antenne, historique PERDUS à chaque redémarrage).

    Avant d'activer l'overlay, place les données sur un stockage persistant :
    une partition ext4 dédiée ou une clé USB, montée sur $DATA_DIR via /etc/fstab.
    Procédure : deploy/build-image.md, section « Données persistantes ».

    (Rien n'a été modifié.)
MSG
  exit 1
fi

raspi-config nonint enable_overlayfs
echo "✅ Overlay activé — la carte SD est protégée, $DATA_DIR reste persistant."
echo "   Redémarre pour appliquer : sudo reboot"
echo "   Pour modifier la config ensuite : sudo deploy/readonly-fs.sh off → régler → réactiver."
