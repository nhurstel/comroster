#!/bin/sh
# Applique la configuration réseau voulue (instance/network.json) via NetworkManager.
# Exécuté AU DÉMARRAGE par comroster-network.service (root) — jamais depuis le web.
# ⚠️ À VALIDER SUR UN VRAI RASPBERRY PI (nmcli non testable hors matériel).
set -eu

CONF="${1:?usage: apply-network.sh <chemin/network.json>}"
[ -f "$CONF" ] || { echo "Pas de config réseau ($CONF) — défaut NetworkManager (DHCP/link-local)."; exit 0; }

get() { python3 -c "import json;c=json.load(open('$CONF'));print($1)"; }

MODE="$(get "c.get('mode','link-local')")"

# Connexion filaire active (sinon nom par défaut de Pi OS)
CON="$(nmcli -t -f NAME,TYPE con show 2>/dev/null | awk -F: '$2 ~ /ethernet/ {print $1; exit}')"
[ -n "${CON:-}" ] || CON="Wired connection 1"
echo "Connexion : $CON — mode : $MODE"

case "$MODE" in
  static)
    ADDR="$(get "'%s/%s' % (c['address'], c.get('prefix',24))")"
    GW="$(get "c.get('gateway','') or ''")"
    DNS="$(get "','.join(c.get('dns',[]))")"
    nmcli con mod "$CON" ipv4.method manual ipv4.addresses "$ADDR"
    nmcli con mod "$CON" ipv4.gateway "$GW"
    nmcli con mod "$CON" ipv4.dns "$DNS"
    ;;
  dhcp)
    nmcli con mod "$CON" ipv4.method auto ipv4.addresses "" ipv4.gateway "" ipv4.dns ""
    ;;
  *)  # link-local (défaut, idéal pour une infra de switchs sans DHCP)
    nmcli con mod "$CON" ipv4.method link-local ipv4.addresses "" ipv4.gateway "" ipv4.dns ""
    ;;
esac

nmcli con up "$CON" || true
echo "Config réseau appliquée."
