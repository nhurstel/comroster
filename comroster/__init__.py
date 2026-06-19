from flask import Flask, jsonify

from .config import Config


def create_app(config_overrides=None):
    app = Flask(__name__)
    config = Config(config_overrides)
    app.config.from_mapping(config.as_dict())

    if not app.config.get("TESTING") and not app.config.get("DEBUG"):
        if not app.config.get("SECRET_KEY"):
            raise RuntimeError("FLASK_SECRET_KEY est obligatoire en production")
    if not app.config.get("SECRET_KEY"):
        app.config["SECRET_KEY"] = "dev-insecure-key"

    @app.get("/healthz")
    def healthz():
        return jsonify({"status": "ok"})

    return app
