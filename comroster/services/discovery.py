"""Découverte des antennes Bolero sur le réseau local.

Jusqu'ici, connecter l'antenne exigeait de connaître son adresse IP et de la taper. C'est
la question la plus fréquente à l'installation, et celle à laquelle un régisseur pressé n'a
pas envie de répondre en fouillant une interface Riedel.

⚠️ LA SAISIE MANUELLE RESTE — exigence explicite. La découverte PROPOSE, elle ne connecte
jamais seule : réseau segmenté, antenne hors sous-réseau, VLAN dédié, ou simplement une
salle où deux antennes répondent — dans tous ces cas la saisie directe est la seule qui
marche, et c'est elle qui reste le chemin de référence.

ANTI-SSRF : le balayage n'accepte AUCUNE adresse de l'utilisateur. Il énumère le sous-réseau
déduit de l'adresse du boîtier lui-même, et refuse tout ce qui n'est pas privé. La garde
posée sur `/api/antenna/connect` (littéral IP uniquement) reste donc entière — on ne lui
ouvre pas une porte dérobée par le scan.
"""
import ipaddress
import json
import logging
import socket
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

log = logging.getLogger(__name__)

#: Un /24 fait 254 hôtes : c'est la taille d'un réseau de régie, et le balayage tient en
#: quelques secondes. Au-delà, le temps d'attente dépasserait ce qu'on peut demander à
#: quelqu'un devant un écran — la saisie manuelle reprend alors tout son sens.
MAX_HOSTS = 254
#: Délai par hôte. Une antenne sur le même LAN répond en quelques millisecondes ; ce délai
#: ne borne en pratique que les adresses mortes.
CONNECT_TIMEOUT = 0.35
HTTP_TIMEOUT = 1.5
WORKERS = 48
PORT = 80


def candidate_hosts(base_ip, prefix=24):
    """Hôtes à sonder autour de `base_ip`, hors adresse du boîtier, réseau et diffusion.

    Refuse les plages non privées : un boîtier mal configuré (IP publique par DHCP) ne
    doit pas se mettre à balayer Internet depuis la régie d'un client.
    """
    try:
        addr = ipaddress.ip_address(base_ip)
        net = ipaddress.ip_network(f"{base_ip}/{prefix}", strict=False)
    except ValueError:
        return []
    if addr.version != 4 or not (net.is_private or net.is_link_local):
        return []
    if net.num_addresses - 2 > MAX_HOSTS:
        return []
    return [str(h) for h in net.hosts() if str(h) != str(addr)]


def _looks_like_antenna(payload):
    """Signature d'une réponse `/rest/nodeStatus` d'antenne Bolero."""
    return isinstance(payload, dict) and isinstance(payload.get("nodeStatus"), list)


def probe(ip, port=PORT, connect_timeout=CONNECT_TIMEOUT, http_timeout=HTTP_TIMEOUT):
    """Cet hôte est-il une antenne Bolero ? Retourne une fiche, ou None.

    Deux temps : un `connect` TCP court écarte en quelques centièmes les 250 adresses
    mortes d'un /24 ; seuls les hôtes qui écoutent paient le coût d'une requête HTTP.

    Le port est un PARAMÈTRE et il sert aux DEUX étapes. Il ne l'était pas : la sonde TCP
    lisait la constante tandis que l'URL portait 80 en dur, si bien que changer le port
    n'aurait sondé qu'à moitié. Défaut trouvé par le test, jamais visible en production
    (l'antenne écoute bien sur 80).
    """
    try:
        with socket.create_connection((ip, port), timeout=connect_timeout):
            pass
    except OSError:
        return None
    try:
        req = urllib.request.Request(f"http://{ip}:{port}/rest/nodeStatus", method="GET")
        with urllib.request.urlopen(req, timeout=http_timeout) as resp:
            payload = json.loads(resp.read() or b"{}")
    except (urllib.error.URLError, OSError, ValueError):
        # Un hôte qui écoute sur le 80 sans être une antenne (imprimante, switch…) :
        # ce n'est pas une erreur, juste une non-réponse.
        return None
    if not _looks_like_antenna(payload):
        return None
    nodes = payload.get("nodeStatus") or []
    local = next((n for n in nodes if n.get("isLocal")), nodes[0] if nodes else {})
    beltpacks = sum(len(n.get("bp") or []) for n in nodes)
    return {
        "ip": ip,
        "name": str(local.get("name") or "").strip() or None,
        "nodes": len(nodes),
        "beltpacks": beltpacks,
    }


def scan(base_ip, prefix=24, workers=WORKERS, **kw):
    """Balaie le sous-réseau du boîtier. Retourne les antennes trouvées, triées par IP."""
    hosts = candidate_hosts(base_ip, prefix)
    if not hosts:
        return []
    found = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(probe, ip, **kw): ip for ip in hosts}
        for future in as_completed(futures):
            try:
                fiche = future.result()
            except Exception:   # une sonde ratée n'interrompt jamais le balayage
                log.debug("sonde en échec sur %s", futures[future], exc_info=True)
                continue
            if fiche:
                found.append(fiche)
    return sorted(found, key=lambda f: ipaddress.ip_address(f["ip"]))


def sample():
    """Résultat fictif pour le mode dev/test (aucune antenne à portée)."""
    return [
        {"ip": "192.168.1.11", "name": "Bolero-Régie", "nodes": 2, "beltpacks": 8},
        {"ip": "192.168.1.12", "name": "Bolero-Plateau", "nodes": 1, "beltpacks": 3},
    ]
