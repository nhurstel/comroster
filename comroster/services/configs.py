import json
import os
import re
from datetime import datetime, timezone


def _slug(name):
    s = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return s or "config"


class Configs:
    def __init__(self, storage):
        self.storage = storage
        self.dir = os.path.join(storage.data_dir, "configs")
        os.makedirs(self.dir, exist_ok=True)

    def _path(self, name):
        return os.path.join(self.dir, f"{_slug(name)}.json")

    def list(self):
        items = []
        for fname in os.listdir(self.dir):
            if not fname.endswith(".json"):
                continue
            try:
                with open(os.path.join(self.dir, fname), encoding="utf-8") as fh:
                    data = json.load(fh)
            except (OSError, json.JSONDecodeError):
                continue
            items.append({"name": data.get("name", fname[:-5]),
                          "updated_at": data.get("updated_at", "")})
        return sorted(items, key=lambda x: x["name"].lower())

    def save(self, name, state):
        if not name or not name.strip():
            raise ValueError("Nom de configuration requis")
        payload = {"name": name.strip(),
                   "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                   "state": state}
        self.storage.atomic_write(self._path(name), payload)

    def load(self, name):
        path = self._path(name)
        if not os.path.exists(path):
            raise KeyError(name)
        data = self.storage.read_json(path)   # tolérant à la corruption (.bak / None)
        if data is None:
            raise KeyError(name)
        return data["state"]

    def delete(self, name):
        path = self._path(name)
        if not os.path.exists(path):
            raise KeyError(name)
        os.unlink(path)
        if os.path.exists(path + ".bak"):       # pas d'orphelin de sauvegarde
            os.unlink(path + ".bak")
