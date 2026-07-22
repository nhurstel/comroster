import base64
import hashlib
import json
import os
import socket
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

from cryptography.fernet import Fernet


class AntennaError(Exception):
    pass


def _battery_percent(battery):
    """% de charge depuis battery.currentCharge / maxCharge (None si indisponible)."""
    cur, mx = battery.get("currentCharge"), battery.get("maxCharge")
    if isinstance(cur, (int, float)) and isinstance(mx, (int, float)) and mx > 0:
        return max(0, min(100, round(cur / mx * 100)))
    return None


class AntennaClient:
    def __init__(self, data_dir, secret_key):
        self._secret_key = secret_key or "dev-insecure-key"
        self.path = os.path.join(data_dir, "antenna.json")
        self._ip = None
        self._password = None
        self._connected = False
        self._info = {}
        self._live_cache = None
        self._live_ts = 0.0
        # L'état ci-dessus est partagé entre les requêtes HTTP (connect/disconnect) et le
        # thread poller (live_status) : ce verrou réentrant sérialise les transitions.
        # Les appels réseau se font HORS verrou (voir live_status) pour ne pas bloquer.
        self._lock = threading.RLock()
        try:
            self.timeout = int(os.environ.get("COMROSTER_ANTENNA_TIMEOUT", "5"))
        except ValueError:
            self.timeout = 5

    @property
    def connected(self):
        return self._connected

    @property
    def ip(self):
        return self._ip

    def _fernet(self):
        key = base64.urlsafe_b64encode(hashlib.sha256(self._secret_key.encode()).digest())
        return Fernet(key)

    def _request(self, method, path, body=None, timeout=None):
        if timeout is None:
            timeout = self.timeout
        if not self._ip:
            return False, {"error": "not connected"}
        url = f"http://{self._ip}{path}"
        data = json.dumps(body).encode() if body is not None else None
        headers = {}
        if data:
            headers["Content-Type"] = "application/json"
        if self._password:
            creds = base64.b64encode(f"admin:{self._password}".encode()).decode()
            headers["Authorization"] = f"Basic {creds}"
        try:
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                return True, (json.loads(raw) if raw and raw.strip() else {})
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                return False, {"error": "Mot de passe incorrect ou accès refusé", "code": "auth"}
            return False, {"error": f"Erreur antenne (HTTP {e.code})", "code": "http"}
        except urllib.error.URLError as e:
            if isinstance(e.reason, (socket.timeout, TimeoutError)):
                return False, {"error": "Antenne injoignable (délai dépassé)", "code": "timeout"}
            return False, {"error": "Antenne injoignable — vérifiez l'IP et le réseau", "code": "network"}
        except (socket.timeout, TimeoutError):
            return False, {"error": "Antenne injoignable (délai dépassé)", "code": "timeout"}
        except Exception as e:
            return False, {"error": str(e), "code": "unknown"}

    def connect(self, ip, password):
        with self._lock:
            self._ip = (ip or "").strip()
            self._password = password or ""
            if not self._ip:
                self._ip = None
                raise AntennaError("IP requise")
            ok, data = self._request("GET", "/rest/nodeStatus", timeout=4)
            if not ok:
                self._ip = None
                self._password = None
                raise AntennaError(data.get("error", "Connexion échouée — vérifiez IP et mot de passe"))
            ok2, fw = self._request("GET", "/rest/firmware")
            nodes = data.get("nodeStatus", [])
            local = next((n for n in nodes if n.get("isLocal")), nodes[0] if nodes else {})
            self._info = {"nodes": nodes, "local": local,
                          "firmware": fw.get("firmware", {}) if ok2 else {}}
            self._connected = True
            self._persist()
            return self._info

    def disconnect(self):
        with self._lock:
            self._ip = self._password = None
            self._connected = False
            self._info = {}
            self._live_cache = None
            self._live_ts = 0.0
            if os.path.exists(self.path):
                os.unlink(self.path)

    def reconnect(self):
        """Re-teste la connexion avec les identifiants déjà en mémoire."""
        with self._lock:
            if not self._ip:
                return False
            try:
                self.connect(self._ip, self._password or "")   # verrou réentrant
                return True
            except AntennaError:
                return False

    def status(self):
        with self._lock:
            return {"connected": self._connected, "ip": self._ip, "info": self._info}

    def live_status(self, ttl=3.0):
        """État temps réel par beltpack (en ligne, batterie %, barres de réception).

        Deux sources : /rest/bp (config id↔numéro/nom) et /rest/nodeStatus (les beltpacks
        réellement connectés, sous nodeStatus[].bp[] : id, battery, signalLevel). Croisement
        par `id` interne. Cache court ; jamais d'exception réseau remontée.

        Forme : {"connected": bool, "beltpacks": {num: {"online", "battery", "charging",
        "signal"}}}. Pour un beltpack hors ligne : {"online": False}.
        """
        empty = {"connected": False, "beltpacks": {}}
        with self._lock:
            if not self._connected:
                return empty
            now = time.monotonic()
            if self._live_cache is not None and (now - self._live_ts) < ttl:
                return self._live_cache
        # Appels réseau HORS verrou (ils peuvent durer jusqu'au timeout) : on ne bloque
        # ni une connexion/déconnexion admin ni un autre lecteur pendant ce temps.
        ok_ns, ns = self._request("GET", "/rest/nodeStatus")
        if not ok_ns:
            return empty
        try:
            config = self._beltpack_config()
        except AntennaError:
            return empty

        live_by_id = {}
        for node in ns.get("nodeStatus", []):
            for cb in (node.get("bp") or []):
                bat = cb.get("battery") or {}
                live_by_id[cb.get("id")] = {
                    "online": True,
                    "battery": _battery_percent(bat),
                    "charging": bool(bat.get("usbPower")),
                }
        beltpacks = {bp["number"]: live_by_id.get(bp["id"], {"online": False}) for bp in config}
        with self._lock:
            if not self._connected:      # une déconnexion a pu survenir pendant le réseau
                return empty
            self._live_cache = {"connected": True, "beltpacks": beltpacks}
            self._live_ts = time.monotonic()
            return self._live_cache

    def _beltpack_config(self):
        """Beltpacks enregistrés depuis /rest/bp : [{id, number, name}] (config seule)."""
        ok, data = self._request("GET", "/rest/bp")
        if not ok:
            raise AntennaError(data.get("error", "Lecture des beltpacks impossible"))
        out = []
        for bp in data.get("bp", []):
            if not bp.get("registered"):
                continue
            cfg = bp.get("bpConfig", {})
            num = cfg.get("bpNumber")
            if num is None:
                continue
            out.append({"id": bp.get("id"), "number": str(num),
                        "name": cfg.get("bpName", "") or ""})
        return out

    def fetch_beltpacks(self):
        """Pour l'import : numéro + nom (l'état en ligne n'est pas dans /rest/bp)."""
        return [{"number": bp["number"], "name": bp["name"]} for bp in self._beltpack_config()]

    def _persist(self):
        token = self._fernet().encrypt(self._password.encode()).decode() if self._password else ""
        payload = {"ip": self._ip, "password_enc": token, "info": self._info,
                   "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False, indent=2))
        os.chmod(self.path, 0o600)

    def load_persisted(self):
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError):
            return
        ip = data.get("ip")
        token = data.get("password_enc") or ""
        password = ""
        if token:
            try:
                password = self._fernet().decrypt(token.encode()).decode()
            except Exception:
                return  # clé changée / corrompu → on ignore les creds
        with self._lock:
            self._ip = ip
            self._password = password
            self._info = data.get("info", {})
