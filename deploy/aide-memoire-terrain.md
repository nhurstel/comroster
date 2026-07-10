# Aide-mémoire terrain — installation & test sur Raspberry Pi

Fiche à garder sous la main pendant les tests. Tout est en une page, du branchement
au dépannage. Détails complets : [raspberry-pi.md](raspberry-pi.md).

---

## 1. Installation (une fois, avec Internet)

> ⚠️ Internet est nécessaire **uniquement pendant l'installation** (apt + pip).
> Ensuite le boîtier fonctionne 100 % hors ligne.

```bash
git clone https://github.com/nhurstel/comroster ~/comroster
cd ~/comroster
sudo deploy/setup-pi.sh
sudo reboot
```

Au reboot, l'écran affiche automatiquement le guide de bienvenue avec QR code.

Première config → depuis un téléphone/PC du même réseau :
1. Scanner le QR (ou ouvrir `http://comroster.local:8080/admin`)
2. Créer le mot de passe admin (4 caractères minimum)
3. Connecter l'antenne, créer les groupes, **Publier**

---

## 2. Plan de test terrain

Cocher au fur et à mesure. Ordre pensé pour tester la porte de secours (RJ45) en premier.

- [ ] **Kiosk au boot** — reboot → `/display` plein écran sans intervention ;
      l'écran ne se met pas en veille après 10 min.
- [ ] **Port de service RJ45** — câble direct PC ↔ Pi → `http://comroster.local:8080/admin`
      répond. (C'est le filet de sécurité : à valider avant de jouer avec le réseau.)
- [ ] **Réseau filaire** — Admin → Réseau → Filaire, IP fixe → reboot →
      l'écran affiche la nouvelle IP. Retour DHCP/link-local : idem.
- [ ] **Réseau Wi-Fi** — Admin → Réseau → Wi-Fi + SSID/mot de passe → reboot →
      le Pi rejoint l'AP **ET** le RJ45 répond toujours en câble direct.
- [ ] **Radio Wi-Fi coupée en filaire** — après un boot en mode filaire :
      `nmcli radio wifi` doit afficher **disabled**.
- [ ] **Antenne Bolero réelle** — connexion, import des beltpacks, pastilles
      batterie/réception visibles sur la TV.
- [ ] **Calibrage réception** — voir §4 (seuils à ajuster avec de vraies mesures).
- [ ] **Coupure de courant** — débrancher/rebrancher l'alim en plein usage :
      le boîtier repart seul, données intactes.

---

## 3. Dépannage express

Accès distant : `ssh pi@comroster.local`

| Symptôme | Commande / piste |
|----------|------------------|
| Voir les logs du serveur en direct | `journalctl -u comroster -f` |
| État du serveur | `systemctl status comroster` |
| État de l'affichage (kiosk cage) | `systemctl status comroster-kiosk` · logs : `journalctl -u comroster-kiosk -b` |
| État de l'application réseau au boot | `systemctl status comroster-network` |
| Écran noir / kiosk absent au boot | `journalctl -u comroster-kiosk -b` (erreurs cage/seat/DRM) ; vérifier que l'utilisateur est dans les groupes `video render input` (`groups`) |
| Admin injoignable sur le LAN | Vérifier `COMROSTER_BIND=0.0.0.0:8080` dans `/etc/comroster.env`, puis `sudo systemctl restart comroster` |
| « Chromium introuvable » | `sudo apt install chromium-browser cage` |
| Connaître l'IP actuelle du Pi | `hostname -I` |
| Config réseau enregistrée | `cat instance/network.json` (le mot de passe Wi-Fi n'apparaît pas via l'admin, mais il est en clair dans ce fichier — normal) |
| Revenir au réseau auto en urgence | `sudo nmcli con mod "Wired connection 1" ipv4.method auto && sudo reboot` |
| **(2 Pi)** Afficheur bloqué sur « Serveur introuvable » | Vérifier `cat instance/viewer.json` et que le serveur répond : `curl http://<ip-serveur>:8080/healthz` |
| **(2 Pi)** Reconfigurer un afficheur | Rebooter et appuyer sur ⚙ pendant les 5 s, ou ouvrir `http://<ip-afficheur>:8081/config` |
| **(2 Pi)** État de l'agent afficheur | `systemctl status comroster-viewer` |

---

## 4. Calibrage des barres de réception

Le mapping `signalLevel` → barres (0 à 4) est une **hypothèse à confirmer** sur la
vraie antenne. Fichier : [../comroster/services/antenna.py](../comroster/services/antenna.py),
fonction `_signal_bars`. Seuils actuels :

| signalLevel mesuré | Barres affichées |
|--------------------|------------------|
| ≤ 0                | 4 (réception maxi) |
| ≤ 2                | 3 |
| ≤ 5                | 2 |
| ≤ 10               | 1 |
| > 10               | 0 (réception nulle) |

**À faire sur place :** éloigner progressivement un beltpack de l'antenne et noter
les valeurs `signalLevel` correspondantes (visibles dans les logs ou l'API
`/api/antenna/live`). Me communiquer ces relevés → on ajustera les seuils ensemble.

---

## 5. Mettre à jour le code sur le Pi

Après un `git push` depuis le Mac :

```bash
cd ~/comroster && git pull
sudo deploy/setup-pi.sh          # réinstalle deps + services (config conservée)
sudo systemctl restart comroster
sudo reboot                      # ou : sudo systemctl restart comroster-kiosk
```

## 5b. Repartir de zéro / désinstaller

| Besoin | Commande |
|--------|----------|
| Réinitialiser la config (garder l'install) | `rm -rf ~/comroster/instance/*` puis `sudo systemctl restart comroster` |
| Désinstaller proprement | `sudo deploy/uninstall-pi.sh` (confirme par `oui`, puis conserver/effacer les données) |
| Tout retirer y compris le dépôt | `sudo deploy/uninstall-pi.sh` puis `rm -rf ~/comroster` |

---

## 6. Services du boîtier (pour mémoire)

| Service | Rôle | Type |
|---------|------|------|
| `comroster.service` | Serveur web (admin + API + données) | système, au boot |
| `comroster-network.service` | Applique `instance/network.json` via nmcli | système, oneshot au boot |
| `comroster-kiosk.service` | Chromium plein écran sur `/display` | utilisateur, session graphique |

Fichier d'environnement : `/etc/comroster.env` · Données : `~/comroster/instance/`
