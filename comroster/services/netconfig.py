"""Configuration réseau du boîtier (IP fixe sur infra à base de switchs).

Le service ne fait que valider et persister la config voulue dans `network.json`.
L'application réelle (nmcli) est faite au démarrage par un service système privilégié
(voir deploy/apply-network.sh) — jamais depuis le process web, pour éviter tout
verrouillage en cours de requête.
"""
import ipaddress
import json
import os

MODES = ("dhcp", "link-local", "static")


def validate(cfg):
    """Retourne (ok: bool, erreur: str|None)."""
    if not isinstance(cfg, dict) or cfg.get("mode") not in MODES:
        return False, "Mode invalide"
    if cfg["mode"] != "static":
        return True, None

    try:
        ipaddress.ip_address(cfg.get("address", ""))
    except ValueError:
        return False, "Adresse IP invalide"

    prefix = cfg.get("prefix", 24)
    if not (isinstance(prefix, int) and 1 <= prefix <= 32):
        return False, "Masque (préfixe) invalide"

    net = ipaddress.ip_network(f"{cfg['address']}/{prefix}", strict=False)

    gw = cfg.get("gateway")
    if gw:
        try:
            if ipaddress.ip_address(gw) not in net:
                return False, "La passerelle n'est pas dans le sous-réseau"
        except ValueError:
            return False, "Passerelle invalide"

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
        if not os.path.exists(self.path):
            return {"mode": "link-local"}
        try:
            with open(self.path, encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, json.JSONDecodeError):
            return {"mode": "link-local"}

    def save(self, cfg):
        ok, err = validate(cfg)
        if not ok:
            raise ValueError(err)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)
        return cfg
