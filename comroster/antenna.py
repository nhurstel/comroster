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


def _enabled():
    return bool(_settings().get("bolero_enabled", False))


def _guard():
    if not _enabled():
        return jsonify({"error": "bolero_disabled"}), 409
    return None


@bp.get("/api/settings")
@login_required
def get_settings():
    return jsonify({"bolero_enabled": _enabled()})


@bp.put("/api/settings")
@login_required
def put_settings():
    data = request.get_json(force=True)
    enabled = bool(data.get("bolero_enabled"))
    _settings().set("bolero_enabled", enabled)
    if not enabled:
        _client().disconnect()
    return jsonify({"bolero_enabled": enabled})


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
    state = _storage().load_draft()
    result = model.merge_beltpacks(state, items)
    _storage().save_draft(state)
    return jsonify(result)
