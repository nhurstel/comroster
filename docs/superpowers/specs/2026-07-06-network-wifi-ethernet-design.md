# Réseau intercom : Filaire ou Wi-Fi — design validé (2026-07-06)

## Besoin
Le boîtier rejoint le réseau intercom **au choix, de façon pérenne** :
- **Filaire** : RJ45 = interface d'exploitation (existant : link-local / DHCP / IP fixe).
- **Wi-Fi** : le boîtier s'associe à un point d'accès relié au réseau intercom
  (SSID + WPA2-PSK), IP en DHCP ou fixe.

L'admin se pilote depuis un ordinateur distant du même réseau ; le Pi sert
d'affichage (kiosk) et de serveur — c'est déjà le design actuel, inchangé.

## Décisions actées (Nathan)
1. Le mode réseau est un **choix d'exploitation pérenne** (pas un enchaînement câble→Wi-Fi).
2. **RJ45 = port de service permanent en mode Wi-Fi** : l'Ethernet garde une adresse
   link-local ; config initiale et dépannage par câble direct PC↔boîtier (`comroster.local`).
3. En Wi-Fi : **IP fixe OU DHCP au choix** (réseau intercom souvent sans DHCP, AP en pont).
4. En mode filaire, la **radio Wi-Fi est coupée** (`nmcli radio wifi off`) — propreté RF en régie.

## Schéma `instance/network.json`
```json
{
  "link": "ethernet" | "wifi",              // absent → "ethernet" (rétro-compat)
  "mode": "link-local" | "dhcp" | "static", // wifi : "dhcp" | "static" uniquement
  "address": "…", "prefix": 24, "gateway": "", "dns": [],
  "wifi": { "ssid": "…", "psk": "…" }       // requis si link=wifi
}
```
- SSID : 1–32 caractères. PSK : 8–63 caractères (WPA2-PSK obligatoire, pas de réseau ouvert).
- PSK stocké en clair (fichier 0600) : NetworkManager le stocke de toute façon en clair
  côté système — le chiffrer ici serait du théâtre.
- **API write-only pour le psk** : `GET /api/network` renvoie `ssid` + `psk_set: true|false`,
  jamais le psk. Un `PUT` sans psk (ou psk vide) **conserve le psk existant** si le lien
  reste wifi (permet de modifier l'IP sans retaper le mot de passe).

## Application au boot (`deploy/apply-network.sh`, root, comroster-network.service)
- `link=ethernet` : comportement actuel + `nmcli radio wifi off`.
- `link=wifi` : `radio wifi on` → connexion NM `comroster-wifi` créée/mise à jour
  (ssid, psk, ipv4 selon mode) → connexion Ethernet forcée en **link-local** (port de
  service) → up des deux.
- Revalidation root (IP + bornes ssid/psk) avant tout appel nmcli — défense en profondeur.
- ⚠️ nmcli non simulable : à valider sur un vrai Pi (comme l'existant).

## UI admin (onglet Réseau)
Choix ⦿ Filaire / ⦿ Wi-Fi en tête ; si Wi-Fi : champs SSID + mot de passe (placeholder
« inchangé » si psk_set) ; bloc IP commun, option link-local masquée en Wi-Fi.
Enregistrer → « redémarrer le boîtier » (inchangé).

## Écran TV / onboarding
`_primary_lan_ip` lit déjà `address` si `mode=static`, quel que soit le lien → aucun
changement (l'adresse d'exploitation affichée/QR est la bonne dans tous les modes).

## Hors périmètre
Hotspot de secours (AP mode), 802.1X, application à chaud sans reboot.
