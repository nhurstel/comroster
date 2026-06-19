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
            raise RuntimeError(
                "FLASK_SECRET_KEY est obligatoire hors debug/test.\n"
                "  • Développement local : ./run-dev.sh  (ou FLASK_DEBUG=true python app.py)\n"
                "  • Production : définir FLASK_SECRET_KEY "
                "(python -c \"import secrets; print(secrets.token_hex(32))\")"
            )
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
    from .security import csrf, limiter

    app.extensions["storage"] = Storage(app.config["DATA_DIR"])
    app.extensions["secret"] = SecretStore(app.config["DATA_DIR"])

    from .services.pubsub import Broker
    from .services.history import History
    app.extensions["broker"] = Broker()
    app.extensions["history"] = History(app.extensions["storage"])

    if app.config.get("TESTING"):
        app.config["WTF_CSRF_ENABLED"] = False
    csrf.init_app(app)
    limiter.init_app(app)

    from .auth import bp as auth_bp
    app.register_blueprint(auth_bp)

    from .api import bp as api_bp
    app.register_blueprint(api_bp)

    from .display import bp as display_bp
    app.register_blueprint(display_bp)
    csrf.exempt(display_bp)

    return app
