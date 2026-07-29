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
#
# Note technique : ce bloc n'est PAS capturé par un « $(...) » — le mélange d'un heredoc
# et de nos apostrophes françaises (n'a, n'importe…) dans un « $(...) » perturbe le
# comptage de guillemets que bash utilise pour trouver la parenthèse fermante. D'où, plus
# bas, un second appel `python3 -c` séparé (sans apostrophe) pour récupérer les noms de
# fichiers déjà validés ici.
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

# Même faute que celle déjà corrigée dans comroster/services/branding.py : un « name »
# JSON valide mais mal typé (nombre, booléen…) ne doit jamais planter le script en
# AttributeError — juste un refus normal, comme n'importe quel manifeste invalide.
nom_client = manifeste.get("name")
if not isinstance(nom_client, str) or not nom_client.strip():
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

# « mono: true » désigne par construction un logo clair, pensé pour le fond sombre du
# tableau de régie. Sans « logo_print », c'est CE logo clair qui part tel quel sur la
# feuille imprimée — blanc sur blanc, invisible. On avertit sans refuser : la politique
# appliance dégrade l'apparence, jamais la disponibilité.
if manifeste.get("mono") and not manifeste.get("logo_print"):
    print(
        "⚠️  ATTENTION — pack « mono: true » sans « logo_print » : ce logo clair est "
        "prévu pour le fond sombre de l'écran de régie. Imprimé tel quel sur la feuille "
        "(fond blanc), il sera ILLISIBLE. Fournissez une variante « logo_print » en "
        "encre noire."
    )

print(f"Pack valide : {manifeste['name']}")
PY

# Noms de fichiers déjà validés ci-dessus (basenames sûrs) : un second appel, isolé du
# heredoc de validation pour la raison expliquée plus haut. Ligne 2 vide si logo_print
# est absent.
NOMS="$(python3 -c '
import json, os, sys
with open(os.path.join(sys.argv[1], "brand.json"), encoding="utf-8") as f:
    manifeste = json.load(f)
print(manifeste["logo"])
print(manifeste.get("logo_print") or "")
' "$SRC")"

LOGO_NAME="$(sed -n '1p' <<<"$NOMS")"
LOGO_PRINT_NAME="$(sed -n '2p' <<<"$NOMS")"

# ---------- pose ----------
install -d -o root -g root -m 0755 "$DEST"
rm -f "$DEST"/*
# On copie NOMMÉMENT brand.json et les fichiers qu'il déclare, plutôt que de s'appuyer
# sur un motif de nom de fichier (`-name '*.svg'`) : la validation ci-dessus accepte
# `.SVG`/`.PNG` en majuscules (elle compare en minuscules), un motif `find` sensible à la
# casse laisserait un tel logo derrière lui — « Pack valide », « ✅ Marque posée », puis
# un repli silencieux sur ComRoster au démarrage suivant. Le manifeste est déjà validé
# ici : ses noms sont sûrs à utiliser tels quels.
install -o root -g root -m 0644 "$SRC/brand.json" "$DEST/"
install -o root -g root -m 0644 "$SRC/$LOGO_NAME" "$DEST/"
if [ -n "$LOGO_PRINT_NAME" ]; then
  install -o root -g root -m 0644 "$SRC/$LOGO_PRINT_NAME" "$DEST/"
fi

if [ -n "$ENV_FILE" ]; then
  grep -qxF "$ENV_LINE" "$ENV_FILE" || printf '%s\n' "$ENV_LINE" >> "$ENV_FILE"
else
  grep -qxF "Environment=${ENV_LINE}" "$UNIT" || sed -i "/^\[Service\]/a Environment=${ENV_LINE}" "$UNIT"
fi

systemctl daemon-reload
systemctl restart comroster

echo "✅ Marque posée dans $DEST."
echo "   Vérifie /display, puis /admin/print."
