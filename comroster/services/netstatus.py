"""État réseau COURANT (lecture seule) — « où le boîtier est-il joignable en ce moment ? ».

Complément du scan Wi-Fi : ne modifie rien, donc pas de chemin privilégié. Interroge nmcli
en argv fixe et tolère toute panne (esprit appliance) : nmcli absent / refusé / délai
dépassé → available:false, jamais d'exception. Les parseurs sont purs (testables sans Pi).
"""
import subprocess

_TYPES = ("ethernet", "wifi")


def _unescape(v):
    return v.replace("\\:", ":").replace("\\\\", "\\")


def parse_device_status(out):
    """`nmcli -t -f DEVICE,TYPE,STATE,CONNECTION device status` → liens gérés connectés."""
    links = []
    for line in out.splitlines():
        parts = line.split(":", 3)
        if len(parts) < 4:
            continue
        device, dtype, state, connection = parts
        if dtype in _TYPES and state == "connected":
            links.append({"device": device, "type": dtype, "connection": _unescape(connection)})
    return links


def parse_ip4(out):
    """Première IPv4 de `nmcli -t -f IP4.ADDRESS device show <dev>` (sans le préfixe)."""
    for line in out.splitlines():
        if line.startswith("IP4.ADDRESS") and ":" in line:
            value = line.split(":", 1)[1].strip()
            return value.split("/", 1)[0] or None
    return None


def parse_active_ssid(out):
    """SSID de la ligne active de `nmcli -t -f ACTIVE,SSID device wifi`."""
    for line in out.splitlines():
        parts = line.split(":", 1)
        if len(parts) == 2 and parts[0] == "yes":
            return _unescape(parts[1]).strip() or None
    return None


def _run(args, timeout=6):
    proc = subprocess.run(["nmcli", "-t", *args], capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise OSError(proc.stderr.strip() or f"nmcli code {proc.returncode}")
    return proc.stdout


def current(timeout=6):
    """Liens actifs : type, IP, et SSID en Wi-Fi. {'available': bool, 'links': [...]}."""
    try:
        links = parse_device_status(_run(["-f", "DEVICE,TYPE,STATE,CONNECTION", "device", "status"], timeout))
        ssid = None
        if any(link["type"] == "wifi" for link in links):
            ssid = parse_active_ssid(_run(["-f", "ACTIVE,SSID", "device", "wifi"], timeout))
        out = []
        for link in links:
            ip = parse_ip4(_run(["-f", "IP4.ADDRESS", "device", "show", link["device"]], timeout))
            out.append({"type": link["type"], "ip": ip,
                        "ssid": ssid if link["type"] == "wifi" else None})
    except (OSError, subprocess.TimeoutExpired):
        return {"available": False, "links": []}
    return {"available": True, "links": out}


def sample():
    """État fictif pour le mode dev/test (aucun nmcli disponible)."""
    return [
        {"type": "wifi", "ssid": "Intercom-AP", "ip": "192.168.1.42"},
        {"type": "ethernet", "ssid": None, "ip": "169.254.7.3"},
    ]
