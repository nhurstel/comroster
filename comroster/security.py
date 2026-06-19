from functools import wraps

from flask import session, redirect, url_for, jsonify, request
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

csrf = CSRFProtect()
limiter = Limiter(key_func=get_remote_address, default_limits=[])


def log_in():
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
