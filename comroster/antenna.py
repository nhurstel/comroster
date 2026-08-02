import ipaddress

from flask import Blueprint, current_app, jsonify

from .security import (
    exclusive_state,
    json_body,
    limiter,
    login_required,
    state_lock,
)
from .services import discovery, model, netstatus
from .services.antenna import AntennaError

bp = Blueprint("antenna", __name__)


def _settings():
    return current_app.extensions["settings"]


def _client():
    return current_app.extensions["antenna"]


def _storage():
    return current_app.extensions["storage"]


def _configs():
    return current_app.extensions["configs"]


def _journal():
    return current_app.extensions["journal"]


def _valid_ranges(ranges):
    if not isinstance(ranges, list):
        return None
    out = []
    for r in ranges:
        if not (isinstance(r, (list, tuple)) and len(r) == 2):
            return None
        lo, hi = r
        # bool est un sous-type d'int : True/False ne sont pas des bornes valides
        if isinstance(lo, bool) or isinstance(hi, bool):
            return None
        if not (isinstance(lo, int) and isinstance(hi, int) and lo <= hi):
            return None
        out.append([lo, hi])
    return out


def _settings_public():
    s = _settings()
    return {
        "antenna_ranges": s.get("antenna_ranges", []),
        "auto_sync": bool(s.get("auto_sync", False)),
    }


@bp.get("/api/settings")
@login_required
def get_settings():
    return jsonify(_settings_public())


@bp.put("/api/settings")
@login_required
@exclusive_state
def put_settings():
    data = json_body()
    if "antenna_ranges" in data:
        ranges = _valid_ranges(data.get("antenna_ranges"))
        if ranges is None:
            return jsonify({"error": "Plages invalides"}), 400
        _settings().set("antenna_ranges", ranges)
    if "auto_sync" in data:
        if not isinstance(data.get("auto_sync"), bool):
            return jsonify({"error": "auto_sync doit être un booléen"}), 400
        _settings().set("auto_sync", data["auto_sync"])
    return jsonify(_settings_public())


@bp.post("/api/antenna/discover")
@login_required
@limiter.limit("6 per minute")
def antenna_discover():
    """Antennes Bolero visibles sur le sous-réseau du boîtier.

    ⚠️ N'accepte AUCUNE adresse du client : le périmètre est déduit de l'adresse du
    boîtier lui-même et borné aux plages privées. La garde anti-SSRF de `connect`
    (littéral IP uniquement) reste donc entière — cette route ne lui ouvre pas de porte.

    Elle PROPOSE : c'est l'opérateur qui choisit, puis se connecte par le chemin normal,
    mot de passe compris. La saisie manuelle de l'IP reste disponible en toutes
    circonstances (antenne hors sous-réseau, VLAN dédié, réseau segmenté).

    Rate-limitée : un balayage mobilise plusieurs dizaines de connexions sortantes.
    """
    if current_app.debug or current_app.testing:
        return jsonify({"available": True, "simulated": True, "antennas": discovery.sample()})
    base_ip = _local_ipv4()
    if not base_ip:
        return jsonify({"available": False, "antennas": [],
                        "error": "Adresse du boîtier inconnue — saisissez l'IP de l'antenne."})
    found = discovery.scan(base_ip)
    return jsonify({"available": True, "antennas": found, "scanned_from": base_ip})


def _local_ipv4():
    """Adresse du boîtier sur le réseau — point de départ du balayage."""
    cfg = current_app.extensions["netconfig"].load()
    if cfg.get("mode") == "static" and cfg.get("address"):
        return cfg["address"]
    return netstatus.route_lan_ip() or netstatus.enumerate_lan_ip()


@bp.post("/api/antenna/connect")
@login_required
def antenna_connect():
    data = json_body()
    ip = (data.get("ip") or "").strip()
    password = data.get("password") or ""
    if not ip:
        return jsonify({"error": "IP requise"}), 400
    # Littéral IP uniquement (anti-SSRF) : pas de nom d'hôte, d'URL ni de port.
    try:
        ipaddress.ip_address(ip)
    except ValueError:
        return jsonify({"error": "Adresse IP invalide (ex. 192.168.1.42)"}), 400
    try:
        info = _client().connect(ip, password)
    except AntennaError as exc:
        return jsonify({"error": str(exc)}), 502
    _journal().record("antenna_connect", ip)
    return jsonify({"connected": True, "info": info})


@bp.post("/api/antenna/disconnect")
@login_required
def antenna_disconnect():
    _client().disconnect()
    _journal().record("antenna_disconnect")
    return jsonify({"connected": False})


@bp.get("/api/antenna/status")
@login_required
def antenna_status():
    # Non bloquant : on renvoie l'état mémoire sans tenter de reconnexion réseau.
    return jsonify(_client().status())


@bp.post("/api/antenna/reconnect")
@login_required
def antenna_reconnect():
    client = _client()
    if not client.ip:
        return jsonify({"connected": False, "error": "Aucun réseau intercom configuré"}), 400
    if not client.reconnect():
        return jsonify({"connected": False, "error": "Reconnexion échouée — réseau intercom injoignable"}), 502
    return jsonify({"connected": True, "info": client.status()["info"]})


@bp.get("/api/antenna/live")
@login_required
def antenna_live():
    # État temps réel (non bloquant pour le front : jamais d'erreur 5xx).
    return jsonify(_client().live_status())


@bp.get("/api/live")
@limiter.limit("60 per minute")
def public_live():
    """Variante publique en lecture seule pour l'affichage TV (pas de session).

    Seule route publique qui expose des données d'exploitation (numéros de beltpack,
    niveaux de batterie) : c'est le prix à payer pour que l'écran de régie n'ait pas de
    session. Bornée malgré tout — un écran l'appelle UNE fois au chargement puis reçoit
    tout par SSE, donc 60/min laisse une marge considérable au cas légitime tout en
    fermant la boucle serrée. Le cache de 3 s protégeait l'antenne, pas le pool de threads.
    """
    return jsonify(_client().live_status())


@bp.post("/api/antenna/import/preview")
@login_required
def antenna_import_preview():
    try:
        items = _client().fetch_beltpacks()
    except AntennaError as exc:
        return jsonify({"error": str(exc)}), 502
    ranges = _settings().get("antenna_ranges", [])
    items = model.filter_by_ranges(items, ranges)
    return jsonify(model.diff_beltpacks(_storage().load_draft(), items, ranges=ranges))


@bp.post("/api/antenna/import/apply")
@login_required
def antenna_import_apply():
    try:
        items = _client().fetch_beltpacks()
    except AntennaError as exc:
        return jsonify({"error": str(exc)}), 502
    # Lock APRÈS l'appel réseau : on ne bloque pas les autres mutations pendant
    # les ~5 s d'un éventuel timeout antenne.
    with state_lock:
        ranges = _settings().get("antenna_ranges", [])
        items = model.filter_by_ranges(items, ranges)
        state = _storage().load_draft()
        result = model.mirror_beltpacks(state, items, ranges=ranges)
        _storage().save_draft(state)
    _journal().record("antenna_import", f"{len(items)} beltpacks")
    return jsonify(result)


@bp.get("/api/configs")
@login_required
def list_configs():
    return jsonify(_configs().list())


@bp.post("/api/configs")
@login_required
def save_config():
    data = json_body()
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Nom requis"}), 400
    try:
        _configs().save(name, _storage().load_draft())
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 409
    _journal().record("config_save", name)
    return jsonify({"ok": True})


@bp.post("/api/configs/<name>/load")
@login_required
@exclusive_state
def load_config(name):
    try:
        state = _configs().load(name)
    except KeyError:
        return jsonify({"error": "not_found"}), 404
    _storage().save_draft(state)
    _client().disconnect()      # charger une config déconnecte l'antenne
    _journal().record("config_load", name)
    return jsonify({"ok": True})


@bp.get("/api/configs/<name>/export")
@login_required
def export_config(name):
    """Contenu d'une configuration, SANS effet de bord.

    `/load` est l'autre accès à ce contenu, mais il écrase le brouillon et déconnecte
    l'antenne : impossible d'y câbler un bouton « Exporter » sans détruire le plan de
    travail en cours. Pas d'`@exclusive_state` (rien n'est écrit) et rien au journal —
    c'est une lecture, comme `/api/state`.
    """
    try:
        data = _configs().read(name)
    except KeyError:
        return jsonify({"error": "not_found"}), 404
    return jsonify({"name": data.get("name", name),
                    "slug": _configs().slug(name),
                    "state": data["state"]})


@bp.delete("/api/configs/<name>")
@login_required
def delete_config(name):
    try:
        _configs().delete(name)
    except KeyError:
        return jsonify({"error": "not_found"}), 404
    _journal().record("config_delete", name)
    return jsonify({"ok": True})
