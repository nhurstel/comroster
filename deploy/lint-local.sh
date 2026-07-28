#!/usr/bin/env bash
# Rejoue EN LOCAL le lint de la CI, avec les MÊMES versions d'outils.
#
# Raison d'être : un linter dont la version diffère entre le poste et la CI rend le
# verdict local sans valeur. Ça a coûté deux fois au projet — shellcheck 0.11.0 (brew)
# muet là où la CI en 0.9.0 échouait sur SC2015 (2026-07-12), puis ruff non épinglé qui a
# fait rougir `main` sans qu'une ligne ne change (2026-07-26).
#
# Usage : ./deploy/lint-local.sh
set -euo pipefail

cd "$(dirname "$0")/.."

# Version lue dans le workflow : une seule source de vérité, jamais recopiée ici.
version="$(sed -n 's/^ *SHELLCHECK_VERSION: *"\{0,1\}\([0-9.]*\)"\{0,1\} *$/\1/p' \
  .github/workflows/ci.yml | head -1)"
if [ -z "$version" ]; then
  echo "✗ SHELLCHECK_VERSION introuvable dans .github/workflows/ci.yml" >&2
  exit 1
fi

echo "▸ ruff (version épinglée dans requirements-dev.txt)"
if [ -x .venv/bin/ruff ]; then
  .venv/bin/ruff check .
else
  echo "  ✗ .venv/bin/ruff absent — .venv/bin/pip install -r requirements-dev.txt" >&2
  exit 1
fi

echo "▸ shellcheck v$version (celle de la CI)"
if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  docker run --rm -v "$PWD:/mnt" "koalaman/shellcheck:v$version" deploy/*.sh run-dev.sh
  echo "✓ lint local terminé — mêmes versions que la CI"
else
  # Sans Docker, on lint quand même, mais on REFUSE de laisser croire que c'est
  # équivalent : un « tout vert » sur une autre version ne prouve rien.
  if command -v shellcheck >/dev/null 2>&1; then
    local_version="$(shellcheck --version | sed -n 's/^version: //p')"
    shellcheck deploy/*.sh run-dev.sh
    echo "⚠ shellcheck local $local_version ≠ CI $version — vert ici ne garantit pas vert en CI."
    echo "  Docker donnerait la version exacte : docker run --rm -v \"\$PWD:/mnt\" koalaman/shellcheck:v$version deploy/*.sh run-dev.sh"
  else
    echo "⚠ ni Docker ni shellcheck : scripts shell NON vérifiés." >&2
    exit 1
  fi
fi
