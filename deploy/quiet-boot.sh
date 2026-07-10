#!/usr/bin/env bash
#
# Boot silencieux « appliance » : supprime le splash Raspberry, le logo noyau,
# le curseur clignotant et les logs de démarrage → écran noir jusqu'à ComRoster.
# Idempotent, avec sauvegarde. Appelé par setup-pi.sh (rôles avec écran).
#
#     sudo deploy/quiet-boot.sh            # applique
#     CMDLINE=/chemin CONFIG=/chemin sudo deploy/quiet-boot.sh   # (tests)
set -eu

# Chemins Bookworm (/boot/firmware) avec repli sur l'ancien (/boot)
CONFIG="${CONFIG:-/boot/firmware/config.txt}"
[ -f "$CONFIG" ] || CONFIG=/boot/config.txt
CMDLINE="${CMDLINE:-/boot/firmware/cmdline.txt}"
[ -f "$CMDLINE" ] || CMDLINE=/boot/cmdline.txt

# --- config.txt : couper le splash arc-en-ciel du firmware ----------------
if [ -f "$CONFIG" ]; then
  if ! grep -q '^disable_splash=1' "$CONFIG"; then
    cp "$CONFIG" "$CONFIG.comroster.bak"
    printf '\n# ComRoster : boot silencieux\ndisable_splash=1\n' >> "$CONFIG"
    echo "▶ $CONFIG : disable_splash=1 ajouté"
  else
    echo "▶ $CONFIG : déjà silencieux"
  fi
fi

# --- cmdline.txt : UNE seule ligne ; on retire splash et on ajoute les
#     paramètres de silence sans doublon (logo, curseur, logs). -----------
if [ -f "$CMDLINE" ]; then
  cp "$CMDLINE" "$CMDLINE.comroster.bak"
  line="$(tr -d '\n' < "$CMDLINE")"
  # retire le paramètre plymouth « splash » (mot entier)
  line="$(printf '%s' "$line" | sed -E 's/(^| )splash( |$)/\1\2/g')"
  for p in quiet logo.nologo vt.global_cursor_default=0 loglevel=3 plymouth.enable=0; do
    case " $line " in
      *" $p "*) : ;;                 # déjà présent
      *) line="$line $p" ;;
    esac
  done
  # normalise les espaces multiples et écrit sur une seule ligne (sans newline final)
  printf '%s\n' "$(printf '%s' "$line" | tr -s ' ' | sed -E 's/^ | $//g')" > "$CMDLINE"
  echo "▶ $CMDLINE : paramètres de boot silencieux appliqués"
fi

echo "✅ Boot silencieux configuré (sauvegardes : *.comroster.bak)."
