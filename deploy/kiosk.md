# Affichage kiosk (cage) — notes techniques

Le Pi affiche `/display` en plein écran, en permanence, via **cage** — un compositeur
Wayland qui n'affiche qu'**une seule application** (Chromium), sans bureau. Tout est
installé et configuré par [setup-pi.sh](setup-pi.sh) ; ce document explique le « comment ».

## Chaîne de lancement

```
comroster-kiosk.service (systemd, système)
  └─ cage -- kiosk-run.sh        ← cage ouvre l'affichage Wayland sur tty1
        └─ chromium --ozone-platform=wayland … file://…/boot-splash.html
              └─ bascule vers http://127.0.0.1:8080/display dès que le serveur répond
```

- **Service système** (pas `--user`) : Raspberry Pi OS Lite n'a pas de session
  graphique. Le service ouvre lui-même une session logind (`PAMName=login`,
  `TTYPath=/dev/tty1`) pour obtenir le « seat » (accès écran DRM + entrées).
- L'utilisateur doit être dans les groupes `video`, `render`, `input` (fait par le script).
- `Conflicts=getty@tty1.service` : cage prend le `tty1`.

## Flags Chromium (dans [kiosk-run.sh](kiosk-run.sh))

- `--ozone-platform=wayland` — rendu Wayland natif (cage). **Ne pas** utiliser
  `--use-gl=egl` : obsolète sur Chromium récent, provoque `gl=none` (GPU KO, rendu lent).
- `--password-store=basic` — pas de popup « trousseau » (gnome-keyring).
- `--disable-features=Translate,TranslateUI` — pas de popup de traduction.
- `--kiosk --incognito` — plein écran, sans état persistant.

## Anti-veille (écran qui ne s'éteint pas)

Trois niveaux :
1. **`consoleblank=0`** dans `cmdline.txt` (posé par [quiet-boot.sh](quiet-boot.sh)) —
   empêche le blanking console.
2. **Screen Wake Lock** — `display.js` peut le demander ; actif car `http://127.0.0.1`
   est un contexte sécurisé.
3. Si le DPMS s'active encore sous cage, ajouter un **idle-inhibitor** Wayland
   (à valider sur le matériel — dépend de la version de cage/wlroots).

## Anti-veille par le firmware

Le boot silencieux ([quiet-boot.sh](quiet-boot.sh)) pose aussi `disable_splash=1`
(config.txt) et `quiet logo.nologo plymouth.enable=0 vt.global_cursor_default=0`
(cmdline.txt) : écran noir de l'allumage jusqu'au splash « Booting ComRoster ».

## Rappel

Le **serveur** (gunicorn, [comroster.service](comroster.service)) et le **kiosk** (cage)
sont deux services système indépendants : en mode « 2 Pi », le serveur peut tourner sur
un autre hôte que l'écran (voir la section « Déploiement 2 Pi » de
[raspberry-pi.md](raspberry-pi.md)).
