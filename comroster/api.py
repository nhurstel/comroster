import re

from flask import Blueprint, jsonify, current_app, render_template

from .security import login_required, exclusive_state, json_body
from .services import model

bp = Blueprint("api", __name__)

_CODE_TO_HTTP = {
    "beltpack_conflict": 409,
    "beltpack_empty": 409,
    "not_found": 404,
}


def _storage():
    return current_app.extensions["storage"]


def _history():
    return current_app.extensions["history"]


def _netconfig():
    return current_app.extensions["netconfig"]


def _error(exc):
    return jsonify({"error": str(exc), "code": exc.code}), _CODE_TO_HTTP.get(exc.code, 400)


@bp.get("/admin")
@login_required
def admin_page():
    return render_template("admin.html", initial_data=_storage().load_draft())


@bp.get("/api/state")
@login_required
def get_state():
    return jsonify(_storage().load_draft())


@bp.get("/api/network")
@login_required
def get_network():
    # Vue publique : le psk Wi-Fi est write-only (psk_set en lecture).
    return jsonify(_netconfig().load_public())


@bp.put("/api/network")
@login_required
def put_network():
    data = json_body()
    try:
        _netconfig().save(data)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    # L'application réelle (nmcli) se fait au redémarrage par un service système.
    # Vue publique dans la réponse : le psk ne doit jamais ressortir.
    return jsonify({"ok": True, "config": _netconfig().load_public(), "reboot_required": True})


@bp.post("/api/reboot")
@login_required
def reboot_box():
    # En dev (debug) ou sous tests, on ne redémarre pas vraiment la machine.
    if current_app.debug or current_app.testing:
        return jsonify({"ok": True, "simulated": True})
    import subprocess
    try:
        # Le compte comroster doit avoir sudo NOPASSWD sur `systemctl reboot` (cf setup-pi.sh).
        subprocess.Popen(["sudo", "systemctl", "reboot"])
    except Exception as exc:   # noqa: BLE001 — renvoyer proprement l'échec au client
        return jsonify({"ok": False, "error": str(exc)}), 500
    return jsonify({"ok": True})


@bp.post("/api/groups")
@login_required
@exclusive_state
def create_group():
    data = json_body()
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Nom de groupe requis", "code": "invalid"}), 400
    state = _storage().load_draft()
    try:
        g = model.add_group(state, name, data.get("color", "#888888"), data.get("order"))
    except model.ValidationError as exc:
        return _error(exc)
    _storage().save_draft(state)
    return jsonify(g)


@bp.patch("/api/groups/<gid>")
@login_required
@exclusive_state
def patch_group(gid):
    data = json_body()
    fields = {k: data[k] for k in ("name", "color", "order") if k in data}
    state = _storage().load_draft()
    try:
        g = model.update_group(state, gid, **fields)
    except model.ValidationError as exc:
        return _error(exc)
    _storage().save_draft(state)
    return jsonify(g)


@bp.delete("/api/groups/<gid>")
@login_required
@exclusive_state
def delete_group(gid):
    state = _storage().load_draft()
    try:
        model.delete_group(state, gid)
    except model.ValidationError as exc:
        return _error(exc)
    _storage().save_draft(state)
    return jsonify({"ok": True})


@bp.post("/api/people")
@login_required
@exclusive_state
def create_person():
    data = json_body()
    state = _storage().load_draft()
    try:
        p = model.add_person(state, data.get("role", ""), data.get("beltpack"), data.get("group_id"))
    except model.ValidationError as exc:
        return _error(exc)
    _storage().save_draft(state)
    return jsonify(p)


@bp.patch("/api/people/<pid>")
@login_required
@exclusive_state
def patch_person(pid):
    data = json_body()
    fields = {k: data[k] for k in ("role", "beltpack", "group_id") if k in data}
    state = _storage().load_draft()
    try:
        p = model.update_person(state, pid, **fields)
    except model.ValidationError as exc:
        return _error(exc)
    _storage().save_draft(state)
    return jsonify(p)


@bp.delete("/api/people/<pid>")
@login_required
@exclusive_state
def delete_person(pid):
    state = _storage().load_draft()
    try:
        model.delete_person(state, pid)
    except model.ValidationError as exc:
        return _error(exc)
    _storage().save_draft(state)
    return jsonify({"ok": True})


@bp.post("/api/people/delete-batch")
@login_required
@exclusive_state
def delete_people_batch():
    data = json_body()
    ids = data.get("ids") or []
    state = _storage().load_draft()
    deleted = model.delete_people(state, ids)
    _storage().save_draft(state)
    return jsonify({"deleted": deleted})


@bp.put("/api/draft")
@login_required
@exclusive_state
def replace_draft():
    """Remplace le brouillon complet (édition en bloc depuis l'admin)."""
    payload = json_body()
    try:
        state = model.build_draft(payload)
    except model.ValidationError as exc:
        return _error(exc)
    _storage().save_draft(state)
    return jsonify(state)


@bp.get("/api/export")
@login_required
def export_state():
    resp = jsonify(_storage().load_draft())
    resp.headers["Content-Disposition"] = "attachment; filename=comroster.json"
    return resp


@bp.post("/api/import")
@login_required
@exclusive_state
def import_state():
    # Même chemin que PUT /api/draft : build_draft normalise (ids, champs, scale)
    # et valide — un JSON malformé donne 400/409, jamais un 500.
    payload = json_body()
    try:
        state = model.build_draft(payload)
    except model.ValidationError as exc:
        return _error(exc)
    _storage().save_draft(state)
    return jsonify(state)


@bp.post("/api/publish")
@login_required
@exclusive_state
def publish():
    state = _storage().load_draft()
    try:
        model.validate_state(state)
    except model.ValidationError as exc:
        # Brouillon invalide : on refuse de publier (409, cf. cahier des charges §10.3).
        return jsonify({"error": str(exc), "code": exc.code}), 409
    from .services.publisher import broadcast_published
    broadcast_published(current_app, state)
    return jsonify({"ok": True, "updated_at": state["updated_at"]})


@bp.get("/api/history")
@login_required
def history_list():
    return jsonify(_history().list())


@bp.post("/api/history/clear")
@login_required
def history_clear():
    return jsonify({"cleared": _history().clear()})


@bp.post("/api/history/<ts>/restore")
@login_required
@exclusive_state
def history_restore(ts):
    if not re.fullmatch(r"\d{8}T\d{6}\d*Z", ts):     # format des snapshots uniquement
        return jsonify({"error": "not_found", "code": "not_found"}), 404
    try:
        snapshot = _history().load(ts)
    except KeyError:
        return jsonify({"error": "not_found", "code": "not_found"}), 404
    model.touch(snapshot)
    _storage().save_draft(snapshot)
    return jsonify(snapshot)
