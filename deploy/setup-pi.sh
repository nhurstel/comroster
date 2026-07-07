#!/usr/bin/env bash
#
# Provisionne un Raspberry Pi en « appliance » ComRoster autonome (tout-en-un) :
# serveur gunicorn + affichage kiosk Chromium, démarrage automatique au boot,
# relance auto en cas de crash. À lancer avec sudo depuis le dépôt cloné :
#
#     sudo deploy/setup-pi.sh
#
# Cible : Raspberry Pi OS Bookworm (64-bit) Desktop. Idempotent (relançable).
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

# --- 1. Dépendances système ----------------------------------------------
echo "▶ Installation des paquets…"
apt-get update -qq
apt-get install -y --no-install-recommends \
  python3 python3-venv python3-pip curl \
  chromium-browser unclutter ca-certificates

# --- 2. Environnement Python ---------------------------------------------
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

# --- 4. Service serveur (système) ----------------------------------------
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

# --- 4b. Service d'application réseau (IP fixe, au démarrage) -------------
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

# --- 5. Affichage kiosk (service utilisateur) ----------------------------
echo "▶ Service kiosk (session graphique)…"
KIOSK_DIR="$TARGET_HOME/.config/systemd/user"
install -d -o "$TARGET_USER" -g "$TARGET_USER" "$KIOSK_DIR"
cat > "$KIOSK_DIR/comroster-kiosk.service" <<EOF
[Unit]
Description=ComRoster — affichage kiosk
After=graphical-session.target
PartOf=graphical-session.target

[Service]
ExecStart=$APP_DIR/deploy/kiosk-run.sh
Restart=on-failure
RestartSec=3

[Install]
WantedBy=graphical-session.target
EOF
chmod +x "$APP_DIR/deploy/kiosk-run.sh"
chown -R "$TARGET_USER:$TARGET_USER" "$TARGET_HOME/.config/systemd"

# Le manager utilisateur doit tourner même hors session SSH → linger
loginctl enable-linger "$TARGET_USER"
sudo -u "$TARGET_USER" XDG_RUNTIME_DIR="/run/user/$TARGET_UID" \
  systemctl --user daemon-reload || true
sudo -u "$TARGET_USER" XDG_RUNTIME_DIR="/run/user/$TARGET_UID" \
  systemctl --user enable comroster-kiosk.service || true

# --- 6. Autologin bureau (pour lancer la session graphique au boot) ------
if command -v raspi-config >/dev/null 2>&1; then
  echo "▶ Activation de l'autologin bureau…"
  raspi-config nonint do_boot_behaviour B4 || true
else
  echo "⚠ raspi-config absent : configurer manuellement l'autologin vers le bureau."
fi

IP="$(hostname -I | awk '{print $1}')"
cat <<EOF

✅ Terminé. Redémarre le Pi : sudo reboot

Au boot : le serveur démarre, puis l'écran affiche automatiquement /display.
  • Affichage TV   : ce Pi, plein écran (kiosk)
  • Administration : http://$IP:8080/admin  (depuis un téléphone/laptop du même réseau)

Premier lancement → http://$IP:8080/admin/setup pour créer le mot de passe.
EOF
