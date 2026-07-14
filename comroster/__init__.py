import os
from datetime import timedelta

from flask import Flask, jsonify, request

from .config import Config


def create_app(config_overrides=None):
    app = Flask(
        __name__,
        template_folder="../templates",
        static_folder="../static",
    )
    config = Config(config_overrides)
    app.config.from_mapping(config.as_dict())

    if app.config.get("BEHIND_PROXY"):
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

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
        SESSION_COOKIE_SECURE=not (app.config.get("DEBUG") or app.config.get("TESTING")
                                   or app.config.get("INSECURE_COOKIE")),
        # Session admin bornée : un cookie volé ne reste pas valable indéfiniment.
        PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
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

    from .services.settings import Settings
    from .services.antenna import AntennaClient
    app.extensions["settings"] = Settings(app.extensions["storage"])
    app.extensions["antenna"] = AntennaClient(app.config["DATA_DIR"], app.config.get("SECRET_KEY", ""))
    app.extensions["antenna"].load_persisted()  # recharge les identifiants s'ils existent

    from .services.configs import Configs
    app.extensions["configs"] = Configs(app.extensions["storage"])

    from .services.netconfig import NetConfig
    app.extensions["netconfig"] = NetConfig(app.config["DATA_DIR"])

    # Pousse l'état antenne via SSE (au lieu du polling client). Pas sous tests.
    if not app.config.get("TESTING"):
        from .services.live_poller import start_live_poller
        start_live_poller(app)

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

    from .antenna import bp as antenna_bp
    app.register_blueprint(antenna_bp)

    _register_security(app)

    @app.url_defaults
    def _bust_static_cache(endpoint, values):
        # Ajoute ?v=<mtime> aux URLs static → toute modif de JS/CSS force le rechargement
        # navigateur (indispensable en kiosk : pas de hard-refresh possible).
        if endpoint == "static" and "filename" in values:
            try:
                fpath = os.path.join(app.static_folder, values["filename"])
                values["v"] = int(os.stat(fpath).st_mtime)
            except OSError:
                pass

    return app


def _register_security(app):
    @app.after_request
    def _headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        resp.headers.setdefault("Referrer-Policy", "no-referrer")
        # Toutes les ressources sont locales (JS/CSS/fonts vendorisés) et il n'y a
        # ni script ni style inline : une CSP stricte est possible sans nonce.
        resp.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; object-src 'none'; base-uri 'self'; "
            "frame-ancestors 'self'; form-action 'self'",
        )
        return resp

    @app.errorhandler(400)
    def _400(err):
        if request.path.startswith("/api/"):
            return jsonify({"error": "bad_request"}), 400
        return err

    @app.errorhandler(404)
    def _404(err):
        if request.path.startswith("/api/"):
            return jsonify({"error": "not_found"}), 404
        return err

    @app.errorhandler(429)
    def _429(err):
        if request.path.startswith("/api/"):
            return jsonify({"error": "rate_limited"}), 429
        return "Trop de tentatives. Réessayez plus tard.", 429

    @app.errorhandler(500)
    def _500(err):
        if request.path.startswith("/api/"):
            return jsonify({"error": "server_error"}), 500
        return err
