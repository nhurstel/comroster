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
# Cible : Raspberry Pi OS Bookworm (64-bit). Desktop pour Autonome/Afficheur,
# Lite possible pour Serveur. Idempotent (relançable).
set -euo pipefail

# --- Contexte -------------------------------------------------------------
[ "$(id -u)" -eq 0 ] || { echo "Lancer avec sudo : sudo deploy/setup-pi.sh"; exit 1; }
TARGET_USER="${SUDO_USER:-pi}"
TARGET_UID="$(id -u "$TARGET_USER")"
TARGET_HOME="$(getent passwd "$TARGET_USER" | cut -d: -f6)"
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
PKGS="python3 python3-venv python3-pip curl ca-certificates"
$NEEDS_DISPLAY && PKGS="$PKGS chromium-browser unclutter"
apt-get install -y --no-install-recommends $PKGS

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
After=network.target

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

# --- 4b. Service d'application réseau (IP fixe, au démarrage) -------------
# Toujours installé : applique l'IP propre du Pi (serveur OU afficheur).
echo "▶ Service réseau (applique instance/network.json au boot)…"
chmod +x "$APP_DIR/deploy/apply-network.sh"
cat > /etc/systemd/system/comroster-network.service <<EOF
[Unit]
Description=ComRoster — application de la configuration réseau
After=NetworkManager.service
Wants=NetworkManager.service
Before=comroster.service

[Service]
Type=oneshot
ExecStart=$APP_DIR/deploy/apply-network.sh $DATA_DIR/network.json

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable comroster-network.service

# --- 5. Services utilisateur (kiosk + agent afficheur) -------------------
# Les services --user ne peuvent pas lire /etc/comroster.env (root 600) :
# on injecte les variables nécessaires directement dans les unités.
if $NEEDS_DISPLAY; then
  echo "▶ Services utilisateur (session graphique)…"
  KIOSK_DIR="$TARGET_HOME/.config/systemd/user"
  install -d -o "$TARGET_USER" -g "$TARGET_USER" "$KIOSK_DIR"

  cat > "$KIOSK_DIR/comroster-kiosk.service" <<EOF
[Unit]
Description=ComRoster — affichage kiosk
After=graphical-session.target
PartOf=graphical-session.target

[Service]
Environment=COMROSTER_ROLE=$ROLE
ExecStart=$APP_DIR/deploy/kiosk-run.sh
Restart=on-failure
RestartSec=3

[Install]
WantedBy=graphical-session.target
EOF
  chmod +x "$APP_DIR/deploy/kiosk-run.sh"

  # Agent de configuration afficheur (sert la page de config locale sur :8081)
  if [ "$ROLE" = "viewer" ]; then
    cat > "$KIOSK_DIR/comroster-viewer.service" <<EOF
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
WantedBy=default.target
EOF
  fi

  chown -R "$TARGET_USER:$TARGET_USER" "$TARGET_HOME/.config/systemd"

  # Le manager utilisateur doit tourner même hors session SSH → linger
  loginctl enable-linger "$TARGET_USER"
  sudo -u "$TARGET_USER" XDG_RUNTIME_DIR="/run/user/$TARGET_UID" \
    systemctl --user daemon-reload || true
  sudo -u "$TARGET_USER" XDG_RUNTIME_DIR="/run/user/$TARGET_UID" \
    systemctl --user enable comroster-kiosk.service || true
  if [ "$ROLE" = "viewer" ]; then
    sudo -u "$TARGET_USER" XDG_RUNTIME_DIR="/run/user/$TARGET_UID" \
      systemctl --user enable comroster-viewer.service || true
  fi

  # --- 6. Autologin bureau (lance la session graphique au boot) ----------
  if command -v raspi-config >/dev/null 2>&1; then
    echo "▶ Activation de l'autologin bureau…"
    raspi-config nonint do_boot_behaviour B4 || true
  else
    echo "⚠ raspi-config absent : configurer manuellement l'autologin vers le bureau."
  fi
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
