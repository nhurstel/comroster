import os


class Config:
    def __init__(self, overrides=None):
        self.SECRET_KEY = os.environ.get("FLASK_SECRET_KEY")
        self.DATA_DIR = os.environ.get("DATA_DIR", os.getcwd())
        self.PORT = int(os.environ.get("PORT", "8080"))
        self.DEBUG = os.environ.get("FLASK_DEBUG", "").lower() in ("1", "true", "yes")
        # LAN fermé sans TLS : désactive le flag Secure du cookie sans activer le debug.
        self.INSECURE_COOKIE = os.environ.get("COMROSTER_INSECURE_COOKIE", "").lower() in ("1", "true", "yes")
        self.TESTING = False
        if overrides:
            for key, value in overrides.items():
                setattr(self, key, value)

    def as_dict(self):
        return {k: v for k, v in self.__dict__.items()}
