from flask import Blueprint, request, jsonify, current_app

from .security import login_required
from .services import model
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


def _valid_ranges(ranges):
    if not isinstance(ranges, list):
        return None
    out = []
    for r in ranges:
        if not (isinstance(r, (list, tuple)) and len(r) == 2):
            return None
        lo, hi = r
        if not (isinstance(lo, int) and isinstance(hi, int) and lo <= hi):
            return None
        out.append([lo, hi])
    return out


@bp.get("/api/settings")
@login_required
def get_settings():
    return jsonify({"antenna_ranges": _settings().get("antenna_ranges", [])})


@bp.put("/api/settings")
@login_required
def put_settings():
    data = request.get_json(force=True)
    if "antenna_ranges" in data:
        ranges = _valid_ranges(data.get("antenna_ranges"))
        if ranges is None:
            return jsonify({"error": "Plages invalides"}), 400
        _settings().set("antenna_ranges", ranges)
    return jsonify({"antenna_ranges": _settings().get("antenna_ranges", [])})


@bp.post("/api/antenna/connect")
@login_required
def antenna_connect():
    data = request.get_json(force=True)
    ip = (data.get("ip") or "").strip()
    password = data.get("password") or ""
    if not ip:
        return jsonify({"error": "IP requise"}), 400
    try:
        info = _client().connect(ip, password)
    except AntennaError as exc:
        return jsonify({"error": str(exc)}), 502
    return jsonify({"connected": True, "info": info})


@bp.post("/api/antenna/disconnect")
@login_required
def antenna_disconnect():
    _client().disconnect()
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
        return jsonify({"connected": False, "error": "Aucune antenne configurée"}), 400
    if not client.reconnect():
        return jsonify({"connected": False, "error": "Reconnexion échouée — antenne injoignable"}), 502
    return jsonify({"connected": True, "info": client.status()["info"]})


@bp.get("/api/antenna/live")
@login_required
def antenna_live():
    # État temps réel (non bloquant pour le front : jamais d'erreur 5xx).
    return jsonify(_client().live_status())


@bp.get("/api/live")
def public_live():
    # Variante publique en lecture seule pour l'affichage TV (pas de session).
    return jsonify(_client().live_status())


@bp.post("/api/antenna/import/preview")
@login_required
def antenna_import_preview():
    try:
        items = _client().fetch_beltpacks()
    except AntennaError as exc:
        return jsonify({"error": str(exc)}), 502
    items = model.filter_by_ranges(items, _settings().get("antenna_ranges", []))
    return jsonify(model.diff_beltpacks(_storage().load_draft(), items))


@bp.post("/api/antenna/import/apply")
@login_required
def antenna_import_apply():
    try:
        items = _client().fetch_beltpacks()
    except AntennaError as exc:
        return jsonify({"error": str(exc)}), 502
    items = model.filter_by_ranges(items, _settings().get("antenna_ranges", []))
    state = _storage().load_draft()
    result = model.mirror_beltpacks(state, items)
    _storage().save_draft(state)
    return jsonify(result)


@bp.get("/api/configs")
@login_required
def list_configs():
    return jsonify(_configs().list())


@bp.post("/api/configs")
@login_required
def save_config():
    data = request.get_json(force=True)
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Nom requis"}), 400
    _configs().save(name, _storage().load_draft())
    return jsonify({"ok": True})


@bp.post("/api/configs/<name>/load")
@login_required
def load_config(name):
    try:
        state = _configs().load(name)
    except KeyError:
        return jsonify({"error": "not_found"}), 404
    _storage().save_draft(state)
    _client().disconnect()      # charger une config déconnecte l'antenne
    return jsonify({"ok": True})


@bp.delete("/api/configs/<name>")
@login_required
def delete_config(name):
    try:
        _configs().delete(name)
    except KeyError:
        return jsonify({"error": "not_found"}), 404
    return jsonify({"ok": True})
