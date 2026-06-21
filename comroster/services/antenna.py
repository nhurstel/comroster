import base64
import hashlib
import json
import os
import socket
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

from cryptography.fernet import Fernet


class AntennaError(Exception):
    pass


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
        self._ip = self._password = None
        self._connected = False
        self._info = {}
        self._live_cache = None
        self._live_ts = 0.0
        if os.path.exists(self.path):
            os.unlink(self.path)

    def reconnect(self):
        """Re-teste la connexion avec les identifiants déjà en mémoire."""
        if not self._ip:
            return False
        try:
            self.connect(self._ip, self._password or "")
            return True
        except AntennaError:
            return False

    def status(self):
        return {"connected": self._connected, "ip": self._ip, "info": self._info}

    def live_status(self, ttl=3.0):
        """État temps réel {connected, online:{num:bool}} avec cache court.

        Le cache évite de marteler l'antenne quand plusieurs clients (admin + écrans
        TV) interrogent en parallèle. Jamais d'exception : renvoie déconnecté en cas
        d'erreur réseau.
        """
        if not self._connected:
            return {"connected": False, "online": {}}
        now = time.monotonic()
        if self._live_cache is not None and (now - self._live_ts) < ttl:
            return self._live_cache
        try:
            items = self.fetch_beltpacks()
        except AntennaError:
            return {"connected": False, "online": {}}
        self._live_cache = {"connected": True, "online": {i["number"]: i["online"] for i in items}}
        self._live_ts = now
        return self._live_cache

    def fetch_beltpacks(self):
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
            out.append({"number": str(num), "name": cfg.get("bpName", "") or "",
                        "online": bool(bp.get("connectedNodeId"))})
        return out

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
        self._ip = ip
        self._password = password
        self._info = data.get("info", {})
