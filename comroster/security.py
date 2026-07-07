import threading
from functools import wraps

from flask import session, redirect, url_for, jsonify, request
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.exceptions import BadRequest

csrf = CSRFProtect()
limiter = Limiter(key_func=get_remote_address, default_limits=[])

# Sérialise les cycles load → mutate → save sur l'état (1 worker, N threads gthread) :
# sans lui, deux requêtes simultanées peuvent s'écraser mutuellement (last-write-wins).
state_lock = threading.RLock()


def exclusive_state(view):
    """À poser sur tout handler qui fait un read-modify-write de l'état."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        with state_lock:
            return view(*args, **kwargs)
    return wrapped


def json_body():
    """Corps JSON de la requête, obligatoirement un objet — 400 sinon.

    `silent=True` + vérification du type : un payload malformé ou non-dict donne
    une erreur client propre, jamais un KeyError/TypeError → 500.
    """
    data = request.get_json(force=True, silent=True)
    if not isinstance(data, dict):
        raise BadRequest("Objet JSON attendu")
    return data


def log_in():
    session.permanent = True    # borné par PERMANENT_SESSION_LIFETIME
    session["authenticated"] = True


def log_out():
    session.pop("authenticated", None)


def current_is_authenticated():
    return bool(session.get("authenticated"))


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_is_authenticated():
            if request.path.startswith("/api/") or request.accept_mimetypes.best == "application/json":
                return jsonify({"error": "unauthorized"}), 401
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)
    return wrapped
