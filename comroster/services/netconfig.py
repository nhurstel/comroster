"""Configuration réseau du boîtier — lien Filaire (RJ45) ou Wi-Fi, choix pérenne.

Le service ne fait que valider et persister la config voulue dans `network.json`.
L'application réelle (nmcli) est faite au démarrage par un service système privilégié
(voir deploy/apply-network.sh) — jamais depuis le process web, pour éviter tout
verrouillage en cours de requête.

Modes de lien (design 2026-07-06) :
  - ethernet : le RJ45 porte l'IP d'exploitation (link-local / dhcp / static),
    la radio Wi-Fi est coupée au boot (propreté RF en régie).
  - wifi     : le boîtier s'associe à un AP (SSID + WPA2-PSK, dhcp ou static) ;
    le RJ45 reste en link-local = port de service permanent (config/dépannage
    par câble direct PC↔boîtier).

Le PSK est stocké en clair (fichier 0600) : NetworkManager le stocke de toute
façon en clair côté système. Il ne sort JAMAIS par l'API (voir load_public).
"""
import ipaddress
import json
import os

MODES = ("dhcp", "link-local", "static")
LINKS = ("ethernet", "wifi")
WIFI_MODES = ("dhcp", "static")     # link-local n'a pas de sens sur du Wi-Fi


def validate(cfg):
    """Retourne (ok: bool, erreur: str|None)."""
    if not isinstance(cfg, dict):
        return False, "Config invalide"
    if cfg.get("link", "ethernet") not in LINKS:
        return False, "Lien réseau invalide"
    if cfg.get("mode") not in MODES:
        return False, "Mode invalide"

    if cfg.get("link") == "wifi":
        if cfg["mode"] not in WIFI_MODES:
            return False, "En Wi-Fi : DHCP ou IP fixe uniquement"
        wifi = cfg.get("wifi")
        if not isinstance(wifi, dict):
            return False, "Paramètres Wi-Fi requis"
        ssid = (wifi.get("ssid") or "").strip()
        if not (1 <= len(ssid) <= 32):
            return False, "SSID invalide (1 à 32 caractères)"
        psk = wifi.get("psk") or ""
        if not (8 <= len(psk) <= 63):
            return False, "Mot de passe Wi-Fi invalide (8 à 63 caractères, WPA2)"

    if cfg["mode"] != "static":
        return True, None

    try:
        ipaddress.ip_address(cfg.get("address", ""))
    except ValueError:
        return False, "Adresse IP invalide — saisir une IP seule (ex. 192.168.1.50, sans /24)"

    prefix = cfg.get("prefix", 24)
    if not (isinstance(prefix, int) and not isinstance(prefix, bool) and 1 <= prefix <= 32):
        return False, "Masque (préfixe) invalide"

    net = ipaddress.ip_network(f"{cfg['address']}/{prefix}", strict=False)

    gw = cfg.get("gateway")
    if gw:
        try:
            gw_addr = ipaddress.ip_address(gw)
        except ValueError:
            return False, "Passerelle invalide"
        # `in net` lève TypeError si les familles diffèrent (gw IPv6, adresse IPv4) :
        # on compare d'abord la version pour renvoyer une erreur claire, pas un 500.
        if gw_addr.version != net.version or gw_addr not in net:
            return False, "La passerelle n'est pas dans le sous-réseau"

    for d in cfg.get("dns") or []:
        try:
            ipaddress.ip_address(d)
        except ValueError:
            return False, "Serveur DNS invalide"

    return True, None


class NetConfig:
    def __init__(self, data_dir):
        self.path = os.path.join(data_dir, "network.json")

    def load(self):
        cfg = {"mode": "link-local"}
        if os.path.exists(self.path):
            try:
                with open(self.path, encoding="utf-8") as fh:
                    cfg = json.load(fh)
            except (OSError, json.JSONDecodeError):
                cfg = {"mode": "link-local"}
        # Rétro-compat : les fichiers d'avant le design Wi-Fi n'ont pas `link`.
        cfg.setdefault("link", "ethernet")
        return cfg

    def load_public(self):
        """Vue API : le psk ne sort JAMAIS, remplacé par psk_set (write-only)."""
        cfg = dict(self.load())
        wifi = cfg.pop("wifi", None)
        if cfg.get("link") == "wifi" and isinstance(wifi, dict):
            cfg["wifi"] = {"ssid": wifi.get("ssid", ""), "psk_set": bool(wifi.get("psk"))}
        return cfg

    def save(self, cfg):
        # L'UI ne connaît jamais le psk : un PUT sans psk conserve celui déjà
        # enregistré (permet de changer l'IP sans retaper le mot de passe).
        if isinstance(cfg, dict) and cfg.get("link") == "wifi":
            wifi = cfg.get("wifi") if isinstance(cfg.get("wifi"), dict) else {}
            if not (wifi.get("psk") or ""):
                prev = self.load()
                prev_psk = (prev.get("wifi") or {}).get("psk") if prev.get("link") == "wifi" else None
                if prev_psk:
                    cfg = dict(cfg, wifi=dict(wifi, psk=prev_psk))
        ok, err = validate(cfg)
        if not ok:
            raise ValueError(err)
        tmp = self.path + ".tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)
        return cfg
