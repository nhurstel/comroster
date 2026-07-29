#!/usr/bin/env bash
#
# MARQUE CLIENT — pose ou retire le pack de marque du boîtier.
#
#     sudo deploy/set-branding.sh ~/packs/acme-live/   # pose la marque
#     sudo deploy/set-branding.sh --reset              # revient à ComRoster
#
# Un pack contient brand.json et ses logos :
#     brand.json  {"name": "Acme Live", "logo": "logo.svg",
#                  "logo_print": "logo-noir.svg", "mono": false}
#     logo.svg  logo-noir.svg          (.svg ou .png ; pas de .jpg)
#
# Le pack vit dans /etc/comroster/branding — HORS de DATA_DIR, donc hors de portée de
# l'administration et des sauvegardes. C'est là le verrou : aucun code de l'application
# n'écrit jamais vers ce dossier. Sur le déploiement manuel de référence
# (deploy/comroster.service), `ProtectSystem=full` interdit même au processus, au niveau
# noyau, toute écriture dans /etc.
#
# ⚠️ À POSER AVANT d'activer l'overlay lecture seule (deploy/readonly-fs.sh) : sous
#    overlay, toute écriture dans /etc part en RAM et disparaît au redémarrage.
set -euo pipefail

DEST=/etc/comroster/branding
UNIT=/etc/systemd/system/comroster.service
ENV_LINE="COMROSTER_BRAND_DIR=$DEST"

[ "$(id -u)" -eq 0 ] || { echo "Lancer avec sudo : sudo deploy/set-branding.sh …"; exit 1; }
[ -f "$UNIT" ] || { echo "Unité systemd introuvable ($UNIT) — ComRoster est-il installé ?"; exit 1; }

# Garde-fou overlay, dans l'esprit de celui de readonly-fs.sh : mieux vaut refuser que
# poser une marque qui s'évaporerait au prochain redémarrage.
if [ "$(findmnt -no FSTYPE / 2>/dev/null || echo '')" = "overlay" ]; then
  cat <<'MSG'
⚠️  REFUS — la racine est montée en overlay (lecture seule).

    Toute écriture dans /etc part en RAM et serait PERDUE au redémarrage : la marque
    ne tiendrait pas. Ordre correct :

      sudo deploy/readonly-fs.sh off && sudo reboot
      sudo deploy/set-branding.sh <pack>
      sudo deploy/readonly-fs.sh on  && sudo reboot

    (Rien n'a été modifié.)
MSG
  exit 1
fi

# Deux façons dont l'unité déclare ses variables d'environnement, selon l'installation :
#   • boîtier (deploy/setup-pi.sh)      → EnvironmentFile=/etc/comroster.env (KEY=valeur)
#   • référence manuelle (comroster.service ci-versionné) → Environment=KEY=valeur, en dur
# On détecte laquelle s'applique plutôt que d'en supposer une seule — sur un boîtier réel,
# ancrer sur une ligne « Environment=… » qui n'existe pas laisserait `sed` ne rien faire,
# SANS ERREUR : la marque semblerait posée alors que la variable ne serait jamais définie.
ENV_FILE="$(grep -m1 '^EnvironmentFile=' "$UNIT" | cut -d= -f2- || true)"

# ---------- retrait ----------
if [ "${1:-}" = "--reset" ]; then
  rm -rf "$DEST"
  if [ -n "$ENV_FILE" ]; then
    sed -i "\|^${ENV_LINE}\$|d" "$ENV_FILE"
  else
    sed -i "\|^Environment=${ENV_LINE}\$|d" "$UNIT"
  fi
  systemctl daemon-reload
  systemctl restart comroster
  echo "✅ Marque retirée — le boîtier réaffiche ComRoster."
  exit 0
fi

SRC="${1:-}"
if [ -z "$SRC" ] || [ ! -d "$SRC" ]; then
  echo "Usage : sudo deploy/set-branding.sh <dossier-du-pack> | --reset"
  exit 1
fi

# ---------- validation AVANT de toucher au système ----------
# Un pack invalide est refusé ici, bruyamment, plutôt qu'ignoré en silence au prochain
# démarrage (l'application, elle, retombe sur ComRoster sans rien casser — mais on ne veut
# pas le découvrir le jour du show).
python3 - "$SRC" <<'PY'
import json, os, sys

src = sys.argv[1]

def refus(motif):
    print(f"⚠️  REFUS — pack invalide : {motif}")
    print("    (Rien n'a été modifié.)")
    sys.exit(1)

try:
    with open(os.path.join(src, "brand.json"), encoding="utf-8") as f:
        manifeste = json.load(f)
except FileNotFoundError:
    refus("brand.json absent du dossier")
except ValueError as exc:
    refus(f"brand.json illisible ({exc})")

if not isinstance(manifeste, dict):
    refus("brand.json : la racine doit être un objet")
if not (manifeste.get("name") or "").strip():
    refus("champ « name » absent ou vide")
if not manifeste.get("logo"):
    refus("champ « logo » absent")

for cle in ("logo", "logo_print"):
    nom = manifeste.get(cle)
    if not nom:
        continue
    if nom != os.path.basename(nom):
        refus(f"« {nom} » doit être un simple nom de fichier, pas un chemin")
    if os.path.splitext(nom)[1].lower() not in (".svg", ".png"):
        refus(f"« {nom} » : seuls .svg et .png sont acceptés")
    if not os.path.isfile(os.path.join(src, nom)):
        refus(f"« {nom} » introuvable dans le pack")

print(f"Pack valide : {manifeste['name']}")
PY

# ---------- pose ----------
install -d -o root -g root -m 0755 "$DEST"
rm -f "$DEST"/*
find "$SRC" -maxdepth 1 -type f \
     \( -name 'brand.json' -o -name '*.svg' -o -name '*.png' \) \
     -exec install -o root -g root -m 0644 {} "$DEST"/ \;

if [ -n "$ENV_FILE" ]; then
  grep -qxF "$ENV_LINE" "$ENV_FILE" || printf '%s\n' "$ENV_LINE" >> "$ENV_FILE"
else
  grep -qxF "Environment=${ENV_LINE}" "$UNIT" || sed -i "/^\[Service\]/a Environment=${ENV_LINE}" "$UNIT"
fi

systemctl daemon-reload
systemctl restart comroster

echo "✅ Marque posée dans $DEST."
echo "   Vérifie /display, puis /admin/print."
