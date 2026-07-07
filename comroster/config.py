import os


class Config:
    def __init__(self, overrides=None):
        self.SECRET_KEY = os.environ.get("FLASK_SECRET_KEY")
        self.DATA_DIR = os.environ.get("DATA_DIR", os.getcwd())
        self.PORT = int(os.environ.get("PORT", "8080"))
        self.DEBUG = os.environ.get("FLASK_DEBUG", "").lower() in ("1", "true", "yes")
        # LAN fermé sans TLS : désactive le flag Secure du cookie sans activer le debug.
        self.INSECURE_COOKIE = os.environ.get("COMROSTER_INSECURE_COOKIE", "").lower() in ("1", "true", "yes")
        # Derrière un reverse proxy de confiance (Nginx) : fait confiance à X-Forwarded-For
        # pour que le rate-limit du login voie l'IP réelle du client, pas 127.0.0.1.
        self.BEHIND_PROXY = os.environ.get("COMROSTER_BEHIND_PROXY", "").lower() in ("1", "true", "yes")
        # Garde-fou mémoire : les payloads légitimes (draft/import) font quelques Ko.
        self.MAX_CONTENT_LENGTH = 1 * 1024 * 1024
        # Chaque flux SSE occupe un thread gunicorn en continu : on refuse (503)
        # au-delà de ce cap pour garder des threads libres pour l'admin et l'API.
        # À garder STRICTEMENT inférieur à `threads` dans gunicorn.conf.py.
        try:
            self.SSE_MAX_CLIENTS = int(os.environ.get("COMROSTER_SSE_MAX", "12"))
        except ValueError:
            self.SSE_MAX_CLIENTS = 12
        self.TESTING = False
        if overrides:
            for key, value in overrides.items():
                setattr(self, key, value)

    def as_dict(self):
        return {k: v for k, v in self.__dict__.items()}
