from flask import (
    Blueprint, request, redirect, url_for,
    render_template, current_app, flash, jsonify,
)

from .security import limiter, log_in, log_out

bp = Blueprint("auth", __name__)


def _secret():
    return current_app.extensions["secret"]


@bp.route("/admin/setup", methods=["GET", "POST"])
def setup():
    secret = _secret()
    if secret.is_configured():
        if request.method == "POST":
            return jsonify({"error": "already_configured"}), 409
        return redirect(url_for("auth.login"))
    if request.method == "POST":
        password = request.form.get("password", "")
        if len(password) < 8:
            flash("Mot de passe : 8 caractères minimum.")
            return render_template("setup.html"), 400
        code = secret.setup(password)
        log_in()
        return render_template("setup.html", recovery_code=code)
    return render_template("setup.html")


@bp.route("/admin/login", methods=["GET", "POST"])
@limiter.limit("5 per 5 minutes", methods=["POST"])
def login():
    secret = _secret()
    if not secret.is_configured():
        return redirect(url_for("auth.setup"))
    if request.method == "POST":
        if secret.verify_password(request.form.get("password", "")):
            log_in()
            return redirect(url_for("api.admin_page"))
        flash("Mot de passe incorrect.")
        return render_template("login.html"), 401
    return render_template("login.html")


@bp.post("/admin/logout")
def logout():
    log_out()
    return redirect(url_for("auth.login"))


@bp.route("/admin/recover", methods=["GET", "POST"])
def recover():
    secret = _secret()
    if request.method == "POST":
        try:
            new_code = secret.recover(
                request.form.get("recovery_code", ""),
                request.form.get("password", ""),
            )
        except ValueError:
            flash("Code de récupération invalide.")
            return render_template("login.html", recover=True), 401
        return render_template("login.html", recovery_code=new_code)
    return render_template("login.html", recover=True)
