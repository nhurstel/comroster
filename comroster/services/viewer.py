import ipaddress
import json
import os
import urllib.error
import urllib.request


def probe_server(health_url, timeout=2.0):
    """True si le serveur ComRoster distant répond sur son /healthz."""
    if not health_url:
        return False
    try:
        with urllib.request.urlopen(health_url, timeout=timeout) as resp:
            return 200 <= resp.status < 400
    except (urllib.error.URLError, OSError, ValueError):
        return False


class ViewerConfig:
    """Cible serveur d'un Pi afficheur (mode 2 Pi). Écrit un JSON simple lu par
    kiosk-run.sh pour savoir quel serveur distant afficher."""

    def __init__(self, data_dir):
        os.makedirs(data_dir, exist_ok=True)
        self.path = os.path.join(data_dir, "viewer.json")

    def load(self):
        cfg = {"server_ip": "", "server_port": 8080}
        if os.path.exists(self.path):
            try:
                with open(self.path, encoding="utf-8") as fh:
                    cfg.update(json.load(fh))
            except (OSError, json.JSONDecodeError):
                return {"server_ip": "", "server_port": 8080}
        return cfg

    def save(self, cfg):
        ip = (cfg.get("server_ip") or "").strip()
        try:
            ipaddress.ip_address(ip)
        except ValueError:
            raise ValueError("Adresse IP du serveur invalide")
        port = cfg.get("server_port", 8080)
        if not (isinstance(port, int) and not isinstance(port, bool) and 1 <= port <= 65535):
            raise ValueError("Port serveur invalide")
        data = {"server_ip": ip, "server_port": port}
        tmp = self.path + ".tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)
        return data

    def _base(self):
        cfg = self.load()
        if not cfg["server_ip"]:
            return None
        return f"http://{cfg['server_ip']}:{cfg['server_port']}"

    def display_url(self):
        base = self._base()
        return f"{base}/display" if base else None

    def health_url(self):
        base = self._base()
        return f"{base}/healthz" if base else None
