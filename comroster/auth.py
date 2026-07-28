from flask import (
    Blueprint,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)

from .security import json_body, limiter, log_in, log_out, login_required

bp = Blueprint("auth", __name__)

# Politique appliance : 4 caractères minimum, appliquée au setup ET à la
# récupération (sinon le recover permettrait un mot de passe vide).
MIN_PASSWORD_LENGTH = 4


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
        if len(password) < MIN_PASSWORD_LENGTH:
            flash(f"Mot de passe : {MIN_PASSWORD_LENGTH} caractères minimum.")
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


@bp.post("/admin/password")
@login_required
@limiter.limit("10 per 5 minutes")
def change_password():
    """Rotation du mot de passe depuis l'admin, SANS brûler le code de récupération.

    Jusqu'ici seul `recover` changeait le mot de passe, et il consomme le code : un
    boîtier prêté d'une production à l'autre n'avait donc aucun moyen de rotation.

    Rate-limitée malgré la session : elle vérifie le mot de passe ACTUEL, c'est donc un
    oracle de mot de passe pour quiconque a mis la main sur une session ouverte (un poste
    de régie laissé déverrouillé est le scénario réaliste, pas l'attaque distante).
    """
    data = json_body()
    current = data.get("current") or ""
    new = data.get("new") or ""
    if len(new) < MIN_PASSWORD_LENGTH:
        return jsonify({"error": f"Nouveau mot de passe : {MIN_PASSWORD_LENGTH} caractères minimum."}), 400
    if new == current:
        return jsonify({"error": "Le nouveau mot de passe est identique à l'actuel."}), 400
    try:
        _secret().change_password(current, new)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 403
    current_app.extensions["journal"].record("password_change")
    return jsonify({"ok": True})


@bp.route("/admin/recover", methods=["GET", "POST"])
@limiter.limit("5 per 15 minutes", methods=["POST"])
def recover():
    secret = _secret()
    if request.method == "POST":
        password = request.form.get("password", "")
        if len(password) < MIN_PASSWORD_LENGTH:
            flash(f"Mot de passe : {MIN_PASSWORD_LENGTH} caractères minimum.")
            return render_template("login.html", recover=True), 400
        try:
            new_code = secret.recover(
                request.form.get("recovery_code", ""),
                password,
            )
        except ValueError:
            flash("Code de récupération invalide.")
            return render_template("login.html", recover=True), 401
        return render_template("login.html", recovery_code=new_code)
    return render_template("login.html", recover=True)
