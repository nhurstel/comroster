"""Scan Wi-Fi — LECTURE SEULE des réseaux à proximité, pour le sélecteur du dialogue réseau.

Distinct de l'application de config (apply-network.sh, root) : lister les points d'accès
ne modifie RIEN, on peut donc le faire depuis le process web sans le chemin privilégié.
`nmcli` est invoqué en argv fixe (aucune donnée utilisateur dans la commande → pas
d'injection). Les SSID renvoyés sont diffusés par le voisinage : DONNÉES NON DE CONFIANCE,
assainies ici (contrôle de longueur, caractères de contrôle retirés) et échappées à l'affichage.

Tolérant aux pannes (esprit appliance) : nmcli absent, refusé par polkit, ou délai dépassé
→ `available: False`, jamais une exception. Le champ SSID manuel reste le repli.
"""
import re
import subprocess

_CTRL = re.compile(r"[\x00-\x1f\x7f]")


def parse_scan(output):
    """Transforme la sortie terse `nmcli -t -f SIGNAL,SECURITY,SSID dev wifi list`.

    SSID en dernier car il peut contenir des « : » (échappés `\\:` par nmcli) ; SIGNAL et
    SECURITY n'en contiennent pas. On coupe donc en 3 au plus, puis on déséchappe le SSID.
    Doublons fusionnés (SSID répété par plusieurs bornes) en gardant le meilleur signal.
    """
    best = {}
    for raw in output.splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = line.split(":", 2)
        if len(parts) < 3:
            continue
        signal_raw, security, ssid_raw = parts
        ssid = _CTRL.sub("", ssid_raw.replace("\\:", ":").replace("\\\\", "\\")).strip()
        if not ssid or len(ssid) > 32:      # SSID masqué (vide) ou aberrant : ignoré
            continue
        try:
            signal = max(0, min(100, int(signal_raw)))
        except ValueError:
            signal = 0
        sec = security.strip()
        secured = bool(sec) and sec not in ("--", "none")
        prev = best.get(ssid)
        if prev is None or signal > prev["signal"]:
            best[ssid] = {"ssid": ssid, "signal": signal, "secured": secured}
    return sorted(best.values(), key=lambda n: n["signal"], reverse=True)


def scan(timeout=8):
    """Liste les réseaux Wi-Fi visibles. Retourne {'available': bool, 'networks': [...]}.

    `list` (sans forcer de rescan) lit le cache de NetworkManager : c'est la variante la
    plus permissive sans privilège (un rescan actif peut être refusé par polkit hors
    session active). NM rafraîchit ce cache périodiquement.
    """
    try:
        proc = subprocess.run(
            ["nmcli", "-t", "-f", "SIGNAL,SECURITY,SSID", "dev", "wifi", "list"],
            check=False,                    # nmcli absent ou refusé = pas une exception
            capture_output=True, text=True, timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"available": False, "networks": []}
    if proc.returncode != 0:
        return {"available": False, "networks": []}
    return {"available": True, "networks": parse_scan(proc.stdout)}


def sample():
    """Jeu de réseaux fictif pour le mode dev/test (aucun nmcli disponible)."""
    return [
        {"ssid": "Intercom-AP", "signal": 88, "secured": True},
        {"ssid": "Régie-5G", "signal": 72, "secured": True},
        {"ssid": "Loge-Wifi", "signal": 54, "secured": True},
        {"ssid": "Backstage", "signal": 38, "secured": True},
        {"ssid": "Public-Salle", "signal": 21, "secured": False},
    ]
