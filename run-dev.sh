#!/usr/bin/env bash
# Lancement en DÉVELOPPEMENT local.
# FLASK_DEBUG=true : la factory fournit une clé de session de dev et désactive
# le flag Secure du cookie (indispensable en HTTP local). NE PAS utiliser en prod.
set -e
export FLASK_DEBUG=true
export DATA_DIR="${DATA_DIR:-./instance}"
export PORT="${PORT:-8080}"
echo "ComRoster (dev) → http://127.0.0.1:${PORT}/admin/setup"
exec python app.py
