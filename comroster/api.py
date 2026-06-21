from flask import Blueprint, request, jsonify, current_app, render_template

from .security import login_required
from .services import model

bp = Blueprint("api", __name__)

_CODE_TO_HTTP = {
    "beltpack_conflict": 409,
    "beltpack_empty": 409,
    "not_found": 404,
}


def _storage():
    return current_app.extensions["storage"]


def _broker():
    return current_app.extensions["broker"]


def _history():
    return current_app.extensions["history"]


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


@bp.post("/api/groups")
@login_required
def create_group():
    data = request.get_json(force=True)
    state = _storage().load_draft()
    try:
        g = model.add_group(state, data["name"], data.get("color", "#888888"), data.get("order"))
    except model.ValidationError as exc:
        return _error(exc)
    _storage().save_draft(state)
    return jsonify(g)


@bp.patch("/api/groups/<gid>")
@login_required
def patch_group(gid):
    data = request.get_json(force=True)
    state = _storage().load_draft()
    try:
        g = model.update_group(state, gid, **data)
    except model.ValidationError as exc:
        return _error(exc)
    _storage().save_draft(state)
    return jsonify(g)


@bp.delete("/api/groups/<gid>")
@login_required
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
def create_person():
    data = request.get_json(force=True)
    state = _storage().load_draft()
    try:
        p = model.add_person(state, data.get("role", ""), data["beltpack"], data.get("group_id"))
    except model.ValidationError as exc:
        return _error(exc)
    _storage().save_draft(state)
    return jsonify(p)


@bp.patch("/api/people/<pid>")
@login_required
def patch_person(pid):
    data = request.get_json(force=True)
    state = _storage().load_draft()
    try:
        p = model.update_person(state, pid, **data)
    except model.ValidationError as exc:
        return _error(exc)
    _storage().save_draft(state)
    return jsonify(p)


@bp.delete("/api/people/<pid>")
@login_required
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
def delete_people_batch():
    data = request.get_json(force=True)
    ids = data.get("ids") or []
    state = _storage().load_draft()
    deleted = model.delete_people(state, ids)
    _storage().save_draft(state)
    return jsonify({"deleted": deleted})


@bp.put("/api/draft")
@login_required
def replace_draft():
    """Remplace le brouillon complet (édition en bloc depuis l'admin)."""
    payload = request.get_json(force=True)
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
def import_state():
    data = request.get_json(force=True)
    try:
        if not all(k in data for k in ("version", "groups", "people")):
            raise model.ValidationError("Structure invalide", code="invalid")
        model.validate_state(data)
    except model.ValidationError as exc:
        return jsonify({"error": str(exc), "code": exc.code}), 400
    model.touch(data)
    _storage().save_draft(data)
    return jsonify(data)


@bp.post("/api/publish")
@login_required
def publish():
    state = _storage().load_draft()
    try:
        model.validate_state(state)
    except model.ValidationError as exc:
        # Brouillon invalide : on refuse de publier (409, cf. cahier des charges §10.3).
        return jsonify({"error": str(exc), "code": exc.code}), 409
    _storage().save_published(state)
    _history().archive(state)
    _broker().publish("published", state)
    return jsonify({"ok": True, "updated_at": state["updated_at"]})


@bp.get("/api/history")
@login_required
def history_list():
    return jsonify(_history().list())


@bp.post("/api/history/<ts>/restore")
@login_required
def history_restore(ts):
    try:
        snapshot = _history().load(ts)
    except KeyError:
        return jsonify({"error": "not_found", "code": "not_found"}), 404
    model.touch(snapshot)
    _storage().save_draft(snapshot)
    return jsonify(snapshot)
