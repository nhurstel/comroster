# Fabriquer l'image SD distribuable (master → clones)

Objectif : produire **une image `.img`** qu'on flashe sur les cartes SD des boîtiers livrés.
Chaque client reçoit un boîtier qui démarre directement sur l'écran de bienvenue ComRoster.

Méthode recommandée : **golden master par clonage** (simple, fiable, sans pipeline complexe).

## 1. Préparer le Pi maître

Partir d'un Raspberry Pi OS **Bookworm 64-bit Desktop** fraîchement installé sur un Pi.

```bash
# Hostname = comroster  → l'écran et l'admin seront joignables via comroster.local
sudo raspi-config nonint do_hostname comroster

# mDNS (comroster.local) — Avahi est présent par défaut sur Pi OS, on s'assure qu'il tourne
sudo apt-get update && sudo apt-get install -y avahi-daemon
sudo systemctl enable --now avahi-daemon

# Installer ComRoster en appliance
git clone <url-du-dépôt> ~/comroster
cd ~/comroster
sudo deploy/setup-pi.sh
```

Vérifier sur un écran branché : reboot → l'écran de bienvenue + QR doit s'afficher, et
`http://comroster.local:8080/admin` doit répondre depuis un téléphone du même réseau.

## 2. Réinitialiser pour la distribution (IMPORTANT)

Le master ne doit contenir **aucune donnée ni mot de passe** : chaque boîtier livré doit
démarrer « neuf » (écran de bienvenue). Avant de cloner :

```bash
sudo systemctl stop comroster
# Effacer l'état (mot de passe admin, brouillon, publié, historique, identifiants antenne)
rm -f  ~/comroster/instance/admin_secret.json
rm -f  ~/comroster/instance/data_draft.json ~/comroster/instance/data_published.json
rm -f  ~/comroster/instance/antenna.json
rm -rf ~/comroster/instance/history/
# Vider les logs et l'historique shell (propreté)
sudo journalctl --rotate && sudo journalctl --vacuum-time=1s
history -c 2>/dev/null || true
sudo poweroff
```

> La clé de session dans `/etc/comroster.env` peut rester (elle ne chiffre que des
> identifiants antenne désormais effacés). Pour une étanchéité maximale entre clients,
> la régénérer aussi : `FLASK_SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))')`.

## 2b. IP par défaut (réseau à base de switchs, fortement recommandé)

Sur une infra **sans DHCP ni routeur**, une box sans config réseau n'aurait qu'une adresse
link-local aléatoire — et le QR d'onboarding ne pourrait pas pointer vers une adresse fiable.
Donne au master une **IP fixe par défaut prévisible** : crée `instance/network.json` avant
de réinitialiser/cloner.

```bash
cat > ~/comroster/instance/network.json <<'JSON'
{ "mode": "static", "address": "192.168.1.50", "prefix": 24 }
JSON
```

Conséquences : chaque box démarre toujours à `192.168.1.50`, l'écran de bienvenue affiche
cette adresse et **le QR code l'encode** → le client n'a qu'à mettre son téléphone/laptop
dans le sous-réseau `192.168.1.x`. Il pourra ensuite changer l'IP via la page **Réseau**.

> Adapter l'adresse au plan d'adressage habituel du client (éviter un conflit avec l'antenne
> Bolero). Ce fichier fait partie de l'état « usine » : ne pas l'effacer à l'étape 2.

## 3. Cloner l'image

Retirer la carte SD du Pi maître, l'insérer dans un ordinateur.

- **Le plus simple — Raspberry Pi Imager** : menu « Lire » (*Read*) pour copier la carte vers
  un fichier `comroster-master.img`.
- **En ligne de commande (Linux/macOS)** :
  ```bash
  # Repérer le périphérique (ex. /dev/sdX ou /dev/diskN), PUIS :
  sudo dd if=/dev/sdX of=comroster-master.img bs=4M status=progress
  ```

Réduire l'image (optionnel, pour un fichier plus léger et un flash plus rapide) :
[PiShrink](https://github.com/Drewsif/PiShrink) — `sudo pishrink.sh -z comroster-master.img`.
PiShrink active aussi l'**auto-expansion** au 1er boot (la partition remplit toute la SD).

## 4. Distribuer

Flasher `comroster-master.img` sur chaque carte SD (Raspberry Pi Imager → « Utiliser une
image personnalisée »). Insérer dans le boîtier, joindre la
[carte de démarrage rapide](quick-start-card.html). Terminé.

## Rappels

- **Hostname** `comroster` → adresse `comroster.local` (affichée par l'écran de bienvenue).
  Si plusieurs boîtiers cohabitent sur le **même** réseau, mDNS suffixe automatiquement
  (`comroster-2.local`…) ; pour lever toute ambiguïté, donner un hostname unique par boîtier
  (`raspi-config nonint do_hostname comroster-salle1`).
- **Mise à jour du parc** : `cd ~/comroster && git pull && sudo deploy/setup-pi.sh` sur
  chaque boîtier, ou refaire un master et reflasher.
- **IP fixe** : voir la page « Réseau » de l'administration (à venir) ou fixer un bail DHCP
  côté box internet du client.
