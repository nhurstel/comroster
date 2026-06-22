import os


class Settings:
    def __init__(self, storage):
        self.storage = storage
        self.path = os.path.join(storage.data_dir, "settings.json")

    def all(self):
        # Lecture tolérante : un settings.json corrompu ne doit pas planter le boîtier.
        return self.storage.read_json(self.path) or {}

    def get(self, key, default=None):
        return self.all().get(key, default)

    def set(self, key, value):
        data = self.all()
        data[key] = value
        self.storage.atomic_write(self.path, data)
