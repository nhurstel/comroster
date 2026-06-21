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


def _enabled():
    return bool(_settings().get("bolero_enabled", False))


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


def _guard():
    if not _enabled():
        return jsonify({"error": "bolero_disabled"}), 409
    return None


@bp.get("/api/settings")
@login_required
def get_settings():
    return jsonify({"bolero_enabled": _enabled(),
                    "antenna_ranges": _settings().get("antenna_ranges", [])})


@bp.put("/api/settings")
@login_required
def put_settings():
    data = request.get_json(force=True)
    if "bolero_enabled" in data:
        enabled = bool(data.get("bolero_enabled"))
        _settings().set("bolero_enabled", enabled)
        if not enabled:
            _client().disconnect()
    if "antenna_ranges" in data:
        ranges = _valid_ranges(data.get("antenna_ranges"))
        if ranges is None:
            return jsonify({"error": "Plages invalides"}), 400
        _settings().set("antenna_ranges", ranges)
    return jsonify({"bolero_enabled": _enabled(),
                    "antenna_ranges": _settings().get("antenna_ranges", [])})


@bp.post("/api/antenna/connect")
@login_required
def antenna_connect():
    guard = _guard()
    if guard:
        return guard
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
    guard = _guard()
    if guard:
        return guard
    _client().disconnect()
    return jsonify({"connected": False})


@bp.get("/api/antenna/status")
@login_required
def antenna_status():
    guard = _guard()
    if guard:
        return guard
    client = _client()
    if client.ip and not client.connected:
        client.reconnect()
    return jsonify(client.status())


@bp.post("/api/antenna/import/preview")
@login_required
def antenna_import_preview():
    guard = _guard()
    if guard:
        return guard
    try:
        items = _client().fetch_beltpacks()
    except AntennaError as exc:
        return jsonify({"error": str(exc)}), 502
    items = model.filter_by_ranges(items, _settings().get("antenna_ranges", []))
    return jsonify(model.diff_beltpacks(_storage().load_draft(), items))


@bp.post("/api/antenna/import/apply")
@login_required
def antenna_import_apply():
    guard = _guard()
    if guard:
        return guard
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
