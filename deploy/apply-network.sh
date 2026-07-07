#!/bin/sh
# Applique la configuration réseau voulue (instance/network.json) via NetworkManager.
# Exécuté AU DÉMARRAGE par comroster-network.service (root) — jamais depuis le web.
# ⚠️ À VALIDER SUR UN VRAI RASPBERRY PI (nmcli non testable hors matériel).
#
# Deux liaisons possibles (choix pérenne, design 2026-07-06) :
#   ethernet : le RJ45 porte l'IP d'exploitation ; radio Wi-Fi COUPÉE (propreté RF).
#   wifi     : association à un AP (SSID + WPA2-PSK, dhcp ou static) ; le RJ45 reste
#              en link-local = port de service permanent (câble direct PC↔boîtier).
#
# En cas de config invalide, le script s'arrête AVANT de toucher nmcli :
# NetworkManager conserve l'état précédent et le port de service reste joignable.
set -eu

CONF="${1:?usage: apply-network.sh <chemin/network.json>}"
[ -f "$CONF" ] || { echo "Pas de config réseau ($CONF) — défaut NetworkManager (DHCP/link-local)."; exit 0; }

get() { python3 -c "import json;c=json.load(open('$CONF'));print($1)"; }

LINK="$(get "c.get('link','ethernet')")"
MODE="$(get "c.get('mode','link-local')")"

# Connexion filaire active (sinon nom par défaut de Pi OS)
CON="$(nmcli -t -f NAME,TYPE con show 2>/dev/null | awk -F: '$2 ~ /ethernet/ {print $1; exit}')"
[ -n "${CON:-}" ] || CON="Wired connection 1"
echo "Liaison : $LINK — mode : $MODE — connexion filaire : $CON"

# Défense en profondeur : ce script tourne en root sur un JSON écrit par
# l'utilisateur applicatif — on revalide tout avant de toucher nmcli
# (la validation Flask ne suffit pas si le fichier est modifié autrement).
validate_static() {
  ADDR="$(get "'%s/%s' % (c['address'], c.get('prefix',24))")"
  GW="$(get "c.get('gateway','') or ''")"
  DNS="$(get "','.join(c.get('dns',[]))")"
  python3 - "$ADDR" "$GW" "$DNS" <<'PYEOF'
import ipaddress, sys
addr, gw, dns = sys.argv[1:4]
ipaddress.ip_interface(addr)                       # ex. 192.168.1.10/24
if gw:
    ipaddress.ip_address(gw)
for d in filter(None, dns.split(",")):
    ipaddress.ip_address(d)
PYEOF
}

apply_ipv4() {
  # $1 = nom de connexion nmcli ; utilise MODE/ADDR/GW/DNS
  case "$MODE" in
    static)
      nmcli con mod "$1" ipv4.method manual ipv4.addresses "$ADDR"
      nmcli con mod "$1" ipv4.gateway "$GW"
      nmcli con mod "$1" ipv4.dns "$DNS"
      ;;
    dhcp)
      nmcli con mod "$1" ipv4.method auto ipv4.addresses "" ipv4.gateway "" ipv4.dns ""
      ;;
    *)  # link-local (défaut, idéal pour une infra de switchs sans DHCP)
      nmcli con mod "$1" ipv4.method link-local ipv4.addresses "" ipv4.gateway "" ipv4.dns ""
      ;;
  esac
}

if [ "$LINK" = "wifi" ]; then
  SSID="$(get "c.get('wifi',{}).get('ssid','')")"
  PSK="$(get "c.get('wifi',{}).get('psk','')")"
  python3 - "$SSID" "$PSK" <<'PYEOF'
import sys
ssid, psk = sys.argv[1], sys.argv[2]
assert 1 <= len(ssid) <= 32, "SSID invalide"
assert 8 <= len(psk) <= 63, "PSK invalide (WPA2 : 8-63 caractères)"
PYEOF
  [ "$MODE" = "static" ] && validate_static

  nmcli radio wifi on
  WDEV="$(nmcli -t -f DEVICE,TYPE dev 2>/dev/null | awk -F: '$2=="wifi"{print $1; exit}')"
  [ -n "${WDEV:-}" ] || { echo "Aucune interface Wi-Fi détectée."; exit 1; }

  if ! nmcli -t -f NAME con show 2>/dev/null | grep -qx "comroster-wifi"; then
    nmcli con add type wifi ifname "$WDEV" con-name comroster-wifi ssid "$SSID"
  fi
  nmcli con mod comroster-wifi 802-11-wireless.ssid "$SSID" \
    wifi-sec.key-mgmt wpa-psk wifi-sec.psk "$PSK" connection.autoconnect yes
  apply_ipv4 comroster-wifi

  # RJ45 = port de service permanent (link-local) : toujours joignable en câble direct.
  nmcli con mod "$CON" ipv4.method link-local ipv4.addresses "" ipv4.gateway "" ipv4.dns ""
  nmcli con up "$CON" || true
  nmcli con up comroster-wifi || true
else
  [ "$MODE" = "static" ] && validate_static
  # Mode filaire : pas d'émission Wi-Fi parasite en régie, pas d'interface fantôme.
  nmcli radio wifi off || true
  apply_ipv4 "$CON"
  nmcli con up "$CON" || true
fi

echo "Config réseau appliquée."
