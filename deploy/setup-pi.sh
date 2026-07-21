#!/usr/bin/env bash
#
# Provisionne un Raspberry Pi ComRoster selon un rôle choisi à l'installation :
#   • Autonome  : serveur gunicorn + affichage kiosk sur le même Pi (défaut).
#   • Serveur   : données + admin seuls (pas d'affichage).
#   • Afficheur : écran seul, branché sur un Pi serveur distant (par IP).
#
# À lancer avec sudo depuis le dépôt cloné :
#     sudo deploy/setup-pi.sh
#
# Cible : Raspberry Pi OS Bookworm (64-bit) LITE. L'affichage utilise cage
# (compositeur Wayland « une seule app plein écran »), sans bureau. Idempotent.
set -euo pipefail

# --- Contexte -------------------------------------------------------------
[ "$(id -u)" -eq 0 ] || { echo "Lancer avec sudo : sudo deploy/setup-pi.sh"; exit 1; }
TARGET_USER="${SUDO_USER:-pi}"
APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV="$APP_DIR/.venv"
DATA_DIR="$APP_DIR/instance"
ENV_FILE="/etc/comroster.env"

echo "▶ Utilisateur : $TARGET_USER   Dépôt : $APP_DIR"

# --- 0. Choix du rôle -----------------------------------------------------
echo "▶ Rôle de ce boîtier :"
echo "   1) Autonome  — serveur + affichage (défaut)"
echo "   2) Serveur   — données + admin seuls"
echo "   3) Afficheur — écran seul, se branche sur un serveur distant"
printf "Choix [1] : "
if read -r ROLE_CHOICE </dev/tty 2>/dev/null; then :; else ROLE_CHOICE=1; fi
case "${ROLE_CHOICE:-1}" in
  2) ROLE=server ;;
  3) ROLE=viewer ;;
  *) ROLE=autonomous ;;
esac
echo "▶ Rôle retenu : $ROLE"

SERVER_IP=""
if [ "$ROLE" = "viewer" ]; then
  printf "IP du Pi serveur (ex. 192.168.42.10) : "
  if read -r SERVER_IP </dev/tty 2>/dev/null; then :; else SERVER_IP=""; fi
fi

# Rôles ayant besoin d'un affichage graphique (kiosk Chromium)
NEEDS_DISPLAY=false
[ "$ROLE" != "server" ] && NEEDS_DISPLAY=true
# Rôles faisant tourner le serveur Flask
RUNS_SERVER=false
[ "$ROLE" != "viewer" ] && RUNS_SERVER=true

# --- 1. Dépendances système ----------------------------------------------
echo "▶ Installation des paquets…"
apt-get update -qq
PKGS=(python3 python3-venv python3-pip curl ca-certificates)
# Affichage kiosk minimal : cage (compositeur mono-app) + Chromium + police mono
# pour le splash. Aucun bureau, aucun gestionnaire de fenêtres.
if $NEEDS_DISPLAY; then PKGS+=(cage chromium-browser fonts-dejavu-core); fi
apt-get install -y --no-install-recommends "${PKGS[@]}"

# --- 2. Environnement Python ---------------------------------------------
# Tous les rôles installent requirements.txt (segno inclus). Sur l'afficheur,
# Flask est présent mais jamais lancé (le paquet comroster l'importe au chargement).
echo "▶ Environnement virtuel + dépendances Python…"
sudo -u "$TARGET_USER" python3 -m venv "$VENV"
sudo -u "$TARGET_USER" "$VENV/bin/pip" install -q --upgrade pip
sudo -u "$TARGET_USER" "$VENV/bin/pip" install -q -r "$APP_DIR/requirements.txt"
install -d -o "$TARGET_USER" -g "$TARGET_USER" "$DATA_DIR"

# --- 3. Fichier d'environnement (secret + options appliance) --------------
if [ ! -f "$ENV_FILE" ]; then
  echo "▶ Génération de la clé de session et de $ENV_FILE…"
  SECRET="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
  cat > "$ENV_FILE" <<EOF
# ComRoster — configuration appliance (LAN fermé sans TLS).
FLASK_SECRET_KEY=$SECRET
DATA_DIR=$DATA_DIR
COMROSTER_BIND=0.0.0.0:8080
COMROSTER_ROLE=$ROLE
# ⚠️ LAN fermé sans HTTPS : nécessaire pour que l'admin se connecte sur
# http://<ip-du-pi>:8080, MAIS le mot de passe et le cookie de session circulent
# en clair sur le réseau. À réserver à une régie isolée (pas de Wi-Fi ouvert,
# pas d'accès invité). Pour un réseau partagé : passer par Nginx + TLS
# (deploy/nginx.conf) et supprimer cette ligne.
COMROSTER_INSECURE_COOKIE=true
EOF
  chmod 600 "$ENV_FILE"
else
  echo "▶ $ENV_FILE déjà présent — conservé."
fi

# En profil afficheur : cible serveur (lue par kiosk-run.sh et l'agent)
if [ "$ROLE" = "viewer" ] && [ -n "$SERVER_IP" ]; then
  echo "▶ Cible serveur de l'afficheur : $SERVER_IP"
  cat > "$DATA_DIR/viewer.json" <<JSON
{"server_ip": "$SERVER_IP", "server_port": 8080}
JSON
  chown "$TARGET_USER:$TARGET_USER" "$DATA_DIR/viewer.json"
fi

# --- 4. Service serveur (système) — sauf profil afficheur ----------------
if $RUNS_SERVER; then
  echo "▶ Service systemd serveur…"
  cat > /etc/systemd/system/comroster.service <<EOF
[Unit]
Description=ComRoster — serveur (appliance)
# Aucune dépendance réseau : l'affichage est LOCAL (127.0.0.1), gunicorn doit
# démarrer au plus tôt. Le réseau (nmcli) se configure en parallèle ; le bind
# 0.0.0.0 écoute aussi les interfaces qui montent ensuite (admin distant OK).

[Service]
Type=simple
User=$TARGET_USER
WorkingDirectory=$APP_DIR
EnvironmentFile=$ENV_FILE
ExecStart=$VENV/bin/gunicorn -c gunicorn.conf.py app:app
Restart=on-failure
RestartSec=3
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload
  systemctl enable --now comroster.service
fi

# --- 4a-bis. Droits root ciblés de l'admin web -----------------------------
# Le compte applicatif peut, sans mot de passe et RIEN D'AUTRE :
#   • redémarrer la machine          → bouton « Redémarrer le boîtier »
#   • rejouer le service réseau      → bouton « Appliquer maintenant » (IP sans reboot)
echo "▶ Droits sudo ciblés (reboot + application réseau)…"
cat > /etc/sudoers.d/comroster-reboot <<EOF
$TARGET_USER ALL=(root) NOPASSWD: /usr/bin/systemctl reboot, /bin/systemctl reboot, /sbin/reboot, /usr/bin/systemctl restart comroster-network.service, /bin/systemctl restart comroster-network.service, /usr/bin/systemctl start comroster-network.service, /bin/systemctl start comroster-network.service
EOF
chmod 440 /etc/sudoers.d/comroster-reboot

# --- 4b. Service d'application réseau (IP fixe, au démarrage) -------------
# Toujours installé : applique l'IP propre du Pi (serveur OU afficheur).
echo "▶ Service réseau (applique instance/network.json au boot)…"
chmod +x "$APP_DIR/deploy/apply-network.sh"
cat > /etc/systemd/system/comroster-network.service <<EOF
[Unit]
Description=ComRoster — application de la configuration réseau
After=NetworkManager.service
Wants=NetworkManager.service
# Volontairement PAS de Before=comroster.service : le serveur n'attend pas la
# configuration réseau (affichage local). Le réseau s'applique en parallèle.

[Service]
Type=oneshot
ExecStart=$APP_DIR/deploy/apply-network.sh $DATA_DIR/network.json

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable comroster-network.service

# Boot rapide : ne pas bloquer multi-user.target en attendant le réseau « online ».
# L'appliance répond en local ; le réseau se configure en parallèle (cf. services
# ci-dessus, volontairement sans dépendance réseau).
systemctl disable NetworkManager-wait-online.service 2>/dev/null || true
systemctl disable systemd-networkd-wait-online.service 2>/dev/null || true

# --- 4c. Watchdog matériel : redémarre le Pi s'il se fige -----------------
# systemd « nourrit » le watchdog matériel du Pi (bcm2835_wdt). Si le système
# ne répond plus (kernel hang, blocage GPU), le Pi redémarre tout seul.
echo "▶ Watchdog matériel…"
CONFIG_TXT=/boot/firmware/config.txt; [ -f "$CONFIG_TXT" ] || CONFIG_TXT=/boot/config.txt
if [ -f "$CONFIG_TXT" ] && ! grep -q '^dtparam=watchdog=on' "$CONFIG_TXT"; then
  printf '\n# ComRoster : watchdog matériel\ndtparam=watchdog=on\n' >> "$CONFIG_TXT"
fi
install -d /etc/systemd/system.conf.d
cat > /etc/systemd/system.conf.d/comroster-watchdog.conf <<'WDOG'
[Manager]
# systemd redémarre le matériel s'il ne peut plus pinguer le watchdog en 15 s.
RuntimeWatchdogSec=15
RebootWatchdogSec=2min
WDOG

# --- 5. Affichage kiosk via cage (Wayland mono-app, pas de bureau) --------
# cage lance Chromium plein écran directement sur tty1, en service SYSTÈME.
# PAMName=login + TTYPath ouvrent une session logind avec accès au « seat »
# (écran DRM + entrées), sans root et sans gestionnaire d'affichage.
if $NEEDS_DISPLAY; then
  echo "▶ Affichage kiosk (cage)…"
  chmod +x "$APP_DIR/deploy/kiosk-run.sh"

  # Accès matériel (écran DRM, entrées) pour l'utilisateur du kiosk.
  for g in video render input tty; do
    if getent group "$g" >/dev/null 2>&1; then usermod -aG "$g" "$TARGET_USER" || true; fi
  done

  cat > /etc/systemd/system/comroster-kiosk.service <<EOF
[Unit]
Description=ComRoster — affichage kiosk (cage)
After=systemd-user-sessions.service comroster.service getty@tty1.service
Conflicts=getty@tty1.service

[Service]
Type=simple
User=$TARGET_USER
PAMName=login
TTYPath=/dev/tty1
StandardInput=tty
StandardOutput=journal
StandardError=journal
TTYReset=yes
TTYVHangup=yes
Environment=COMROSTER_ROLE=$ROLE
ExecStart=/usr/bin/cage -- $APP_DIR/deploy/kiosk-run.sh
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
EOF

  # Agent de configuration afficheur (page locale sur :8081), service système.
  if [ "$ROLE" = "viewer" ]; then
    cat > /etc/systemd/system/comroster-viewer.service <<EOF
[Unit]
Description=ComRoster — agent de configuration afficheur
After=network.target

[Service]
Type=simple
Environment=DATA_DIR=$DATA_DIR
ExecStart=$VENV/bin/python -m comroster.viewer_agent
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
  fi

  # Boot silencieux : plus de logo Raspberry ni de logs → écran noir jusqu'au splash.
  echo "▶ Boot silencieux (config.txt / cmdline.txt)…"
  chmod +x "$APP_DIR/deploy/quiet-boot.sh"
  "$APP_DIR/deploy/quiet-boot.sh" || echo "⚠ boot silencieux non appliqué (vérifier /boot/firmware)"

  # Démarrage en console (Lite n'a pas de gestionnaire d'affichage) : cage prend tty1.
  systemctl set-default multi-user.target >/dev/null 2>&1 || true
  systemctl daemon-reload
  systemctl enable comroster-kiosk.service
  [ "$ROLE" = "viewer" ] && systemctl enable comroster-viewer.service
fi

IP="$(hostname -I | awk '{print $1}')"
echo ""
echo "✅ Terminé (rôle : $ROLE). Redémarre le Pi : sudo reboot"
echo ""
case "$ROLE" in
  autonomous)
    cat <<EOF
Au boot : le serveur démarre, puis l'écran affiche automatiquement /display.
  • Affichage TV   : ce Pi, plein écran (kiosk)
  • Administration : http://$IP:8080/admin  (depuis un téléphone/laptop du même réseau)

Premier lancement → http://$IP:8080/admin/setup pour créer le mot de passe.
EOF
    ;;
  server)
    cat <<EOF
Ce Pi est un SERVEUR (pas d'affichage).
  • Administration : http://$IP:8080/admin
  • Les afficheurs devront viser cette IP : $IP

Premier lancement → http://$IP:8080/admin/setup pour créer le mot de passe.
EOF
    ;;
  viewer)
    cat <<EOF
Ce Pi est un AFFICHEUR. Il vise le serveur : ${SERVER_IP:-<non défini>}
  • Au boot : 5 s pour ouvrir la config (bouton ⚙ / QR), sinon il affiche le serveur.
  • Reconfigurer plus tard : http://$IP:8081/config  (IP serveur + IP de cet afficheur)

Si l'IP du serveur change, repointe l'afficheur via cette page puis redémarre.
EOF
    ;;
esac
