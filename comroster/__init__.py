from flask import Flask, jsonify

from .config import Config


def create_app(config_overrides=None):
    app = Flask(
        __name__,
        template_folder="../templates",
        static_folder="../static",
    )
    config = Config(config_overrides)
    app.config.from_mapping(config.as_dict())

    if not app.config.get("TESTING") and not app.config.get("DEBUG"):
        if not app.config.get("SECRET_KEY"):
            raise RuntimeError("FLASK_SECRET_KEY est obligatoire en production")
    if not app.config.get("SECRET_KEY"):
        app.config["SECRET_KEY"] = "dev-insecure-key"

    # Durcissement du cookie de session
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=not (app.config.get("DEBUG") or app.config.get("TESTING")),
    )

    @app.get("/healthz")
    def healthz():
        return jsonify({"status": "ok"})

    # Services partagés
    from .services.storage import Storage
    from .services.secret import SecretStore
    from .security import csrf, limiter, login_required

    app.extensions["storage"] = Storage(app.config["DATA_DIR"])
    app.extensions["secret"] = SecretStore(app.config["DATA_DIR"])

    if app.config.get("TESTING"):
        app.config["WTF_CSRF_ENABLED"] = False
    csrf.init_app(app)
    limiter.init_app(app)

    from .auth import bp as auth_bp
    app.register_blueprint(auth_bp)

    # Stub api (remplacé par le vrai blueprint en P3)
    from flask import Blueprint
    api_stub = Blueprint("api", __name__)

    @api_stub.get("/admin")
    @login_required
    def admin_page():
        return "ADMIN OK"

    @api_stub.get("/api/state")
    @login_required
    def get_state():
        return jsonify(app.extensions["storage"].load_draft())

    app.register_blueprint(api_stub)

    return app
