"""Santé du boîtier (lecture seule) — la page de monitoring de l'appliance.

Agrège ce qui prévient les pannes silencieuses d'un Pi qui tourne sans surveillance :
température (le Pi *throttle* quand il chauffe), sous-tension/throttling, RAM, disque
(carte SD), uptime, afficheurs SSE connectés, état de l'antenne, dernière publication.

Tout est tolérant à l'absence (dev/non-Pi → champ à None, jamais d'exception) et sans
privilège. Les parseurs sont purs (testables sans matériel).
"""
import os
import shutil
import subprocess
import time
from datetime import datetime, timezone

# Import ≈ démarrage du process → sert d'origine pour l'uptime applicatif.
_APP_START = time.time()


def _now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


# ---------- Parseurs purs (testables sans Pi) ----------

def parse_thermal(raw):
    """`/sys/class/thermal/thermal_zone0/temp` (millidegrés) → °C, ou None."""
    try:
        return round(int(raw.strip()) / 1000, 1)
    except (ValueError, AttributeError):
        return None


def parse_meminfo(raw):
    """`/proc/meminfo` → {'total','available','used'} en octets, ou None."""
    vals = {}
    for line in (raw or "").splitlines():
        parts = line.split(":")
        if len(parts) == 2:
            num = parts[1].strip().split()
            if num and num[0].isdigit():
                vals[parts[0]] = int(num[0]) * 1024        # kB → octets
    total, avail = vals.get("MemTotal"), vals.get("MemAvailable")
    if total is None or avail is None:
        return None
    return {"total": total, "available": avail, "used": total - avail}


def parse_throttled(raw):
    """`vcgencmd get_throttled` (ex. 'throttled=0x50000') → drapeaux Pi, ou None.

    Bits : 0 sous-tension / 2 throttling / 3 limite thermique (état COURANT) ;
    16/18/19 = les mêmes « s'est produit depuis le démarrage ».
    """
    try:
        value = int((raw or "").strip().split("=")[-1], 16)
    except ValueError:
        return None
    return {
        "undervoltage_now": bool(value & 0x1),
        "throttled_now": bool(value & 0x4),
        "temp_limit_now": bool(value & 0x8),
        "undervoltage_past": bool(value & 0x10000),
        "throttled_past": bool(value & 0x40000),
        "temp_limit_past": bool(value & 0x80000),
    }


def parse_uptime(raw):
    """`/proc/uptime` (« 1234.56 ... ») → secondes (int), ou None."""
    try:
        return int(float((raw or "").split()[0]))
    except (ValueError, IndexError):
        return None


# ---------- Lecture système (tolérante) ----------

def _read_file(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return None


def _cpu_temp():
    return parse_thermal(_read_file("/sys/class/thermal/thermal_zone0/temp"))


def _throttled():
    try:
        proc = subprocess.run(["vcgencmd", "get_throttled"], capture_output=True, text=True, timeout=3)
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return parse_throttled(proc.stdout)


def _loadavg():
    try:
        return [round(x, 2) for x in os.getloadavg()]
    except (OSError, AttributeError):
        return None


def snapshot(app):
    """Instantané complet de la santé du boîtier."""
    storage = app.extensions["storage"]
    broker = app.extensions["broker"]
    antenna = app.extensions.get("antenna")
    published = storage.load_published()

    try:
        du = shutil.disk_usage(app.config["DATA_DIR"])
        disk = {"total": du.total, "used": du.used, "free": du.free}
    except OSError:
        disk = None

    ant = None
    if antenna is not None:
        try:
            st = antenna.status()
            ant = {"connected": bool(st.get("connected")), "ip": st.get("ip")}
        except Exception:          # l'état antenne ne doit jamais faire échouer la page santé
            ant = None

    pub = None
    if published:
        pub = {
            "groups": len(published.get("groups", [])),
            "people": len(published.get("people", [])),
            "updated_at": published.get("updated_at"),
        }

    return {
        "time": _now_iso(),
        "cpu": {
            "temp_c": _cpu_temp(),
            "load": _loadavg(),
            "cores": os.cpu_count(),
            "throttled": _throttled(),
        },
        "memory": parse_meminfo(_read_file("/proc/meminfo")),
        "disk": disk,
        "uptime": {
            "system_s": parse_uptime(_read_file("/proc/uptime")),
            "app_s": int(time.time() - _APP_START),
        },
        "displays": broker.subscriber_count,
        "antenna": ant,
        "published": pub,
    }
