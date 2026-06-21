import json
import os


class Settings:
    def __init__(self, storage):
        self.storage = storage
        self.path = os.path.join(storage.data_dir, "settings.json")

    def all(self):
        if not os.path.exists(self.path):
            return {}
        with open(self.path, encoding="utf-8") as fh:
            return json.load(fh)

    def get(self, key, default=None):
        return self.all().get(key, default)

    def set(self, key, value):
        data = self.all()
        data[key] = value
        self.storage.atomic_write(self.path, data)
