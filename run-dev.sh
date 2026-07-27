#!/usr/bin/env bash
# Lancement en DÉVELOPPEMENT local.
# FLASK_DEBUG=true : la factory fournit une clé de session de dev et désactive
# le flag Secure du cookie (indispensable en HTTP local). NE PAS utiliser en prod.
set -euo pipefail
cd "$(dirname "$0")"          # DATA_DIR relatif au projet, pas au dossier d'appel

export FLASK_DEBUG=true
export DATA_DIR="${DATA_DIR:-./instance}"
export PORT="${PORT:-8080}"

# L'interpréteur du venv est appelé par son CHEMIN, jamais via le PATH : `activate`
# y injecte un chemin absolu figé à la création, qu'un déplacement du projet rend
# caduc. On obtenait alors « exec: python: not found » avec un prompt affichant
# pourtant (.venv) — l'indicateur vient du NOM du dossier, pas d'une vérification.
PY=".venv/bin/python"
if [ ! -x "$PY" ]; then
  echo "Environnement Python absent ou cassé ($PY introuvable)." >&2
  echo "  python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt -r requirements-dev.txt" >&2
  exit 1
fi

# Le port est vérifié AVANT d'annoncer l'URL. Sans ça la bannière s'affiche, le bind
# échoue derrière, et l'échec ressemble à un démarrage réussi qui « ne marche pas ».
if command -v lsof >/dev/null 2>&1; then
  # `|| true` obligatoire : lsof sort en 1 quand il ne trouve rien, et sous `set -e`
  # l'affectation tuerait le script SANS message — le défaut même qu'on corrige ici.
  occupant=$(lsof -i "tcp:${PORT}" -sTCP:LISTEN -t 2>/dev/null || true)
  if [ -n "$occupant" ]; then
    echo "Port ${PORT} déjà occupé (PID ${occupant//$'\n'/ })." >&2
    echo "  • le libérer    :  lsof -ti tcp:${PORT} | xargs kill" >&2
    echo "  • ou en changer :  PORT=8081 ./run-dev.sh" >&2
    exit 1
  fi
fi

echo "ComRoster (dev) → http://127.0.0.1:${PORT}/admin/setup"
exec "$PY" app.py
