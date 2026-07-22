import json
import os
import re
import unicodedata
from datetime import datetime, timezone


def _slug(name):
    # Translittère les accents ("Éclairage" → "eclairage") au lieu de les supprimer
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9]+", "-", ascii_name.strip().lower()).strip("-")
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
        name = (name or "").strip()
        if not name:
            raise ValueError("Nom de configuration requis")
        path = self._path(name)
        # Le nom est réduit à un slug pour le nom de fichier : deux noms distincts
        # peuvent donc viser le même fichier ("Jour 2" / "jour-2"). On refuse d'écraser
        # silencieusement une config au nom différent ; un même nom = mise à jour normale.
        if os.path.exists(path):
            existing = self.storage.read_json(path)
            if existing and existing.get("name", "").strip().lower() != name.lower():
                raise ValueError(
                    f"Un nom trop proche existe déjà (« {existing.get('name')} ») — "
                    "choisissez un nom plus distinct."
                )
        payload = {"name": name,
                   "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                   "state": state}
        self.storage.atomic_write(path, payload)

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
