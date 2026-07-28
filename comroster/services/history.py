"""Historique des publications : des ÉTATS restaurables, horodatés.

Chaque publication est archivée telle quelle. S'y ajoutent depuis l'audit 2026-07-28 deux
notions qui manquaient cruellement en production :

  • un NOM facultatif — une équipe ne pense pas ses publications en horodatages mais en
    « Filage », « Générale », « Première ». Une liste de dates n'est navigable que si l'on
    se souvient de l'heure qu'il était, ce qui n'arrive jamais ;
  • l'ÉPINGLAGE, qui met un repère à l'abri de la purge. Sans lui, la configuration de la
    première ne survivait pas à trente jours de filages.

Les métadonnées vivent dans un `index.json` unique plutôt qu'en fichiers jumeaux : un
instantané reste un état pur, restaurable sans nettoyage, et la purge n'a qu'un fichier à
tenir à jour.
"""
import os
from datetime import datetime, timedelta, timezone

TS_FORMAT = "%Y%m%dT%H%M%S%fZ"


class History:
    RETENTION_DAYS = 30     # les publications de plus de 30 jours sont supprimées automatiquement
    MAX_SNAPSHOTS = 50      # garde-fou anti-débordement de la carte SD du boîtier
    #: Les repères épinglés échappent à la purge : sans plafond, ils la videraient de son
    #: sens et rempliraient la carte SD à la longue. 20 = large pour une production.
    MAX_PINNED = 20
    LABEL_MAX = 60

    def __init__(self, storage):
        self.storage = storage
        self.dir = storage.history_dir
        os.makedirs(self.dir, exist_ok=True)
        self.index_path = os.path.join(self.dir, "index.json")

    # ---------- métadonnées ----------
    def _index(self):
        data = self.storage.read_json(self.index_path)
        return data if isinstance(data, dict) else {}

    def _save_index(self, index):
        self.storage.atomic_write(self.index_path, index)

    def _meta(self, index, ts):
        entry = index.get(ts)
        if not isinstance(entry, dict):
            return {"label": "", "pinned": False}
        return {"label": str(entry.get("label") or "")[:self.LABEL_MAX],
                "pinned": bool(entry.get("pinned"))}

    def pinned_count(self):
        index = self._index()
        return sum(1 for ts in index if self._meta(index, ts)["pinned"])

    def annotate(self, timestamp, label=None, pinned=None):
        """Nomme et/ou épingle un instantané. Retourne ses métadonnées à jour."""
        if not os.path.exists(os.path.join(self.dir, f"{timestamp}.json")):
            raise KeyError(timestamp)
        index = self._index()
        meta = self._meta(index, timestamp)
        if label is not None:
            meta["label"] = str(label).strip()[:self.LABEL_MAX]
        if pinned is not None:
            pinned = bool(pinned)
            if pinned and not meta["pinned"]:
                autres = sum(1 for ts in index
                             if ts != timestamp and self._meta(index, ts)["pinned"])
                if autres >= self.MAX_PINNED:
                    raise ValueError(
                        f"{self.MAX_PINNED} repères épinglés au maximum — "
                        "détachez-en un avant d'en ajouter un autre."
                    )
            meta["pinned"] = pinned
        if meta["label"] or meta["pinned"]:
            index[timestamp] = meta
        else:
            index.pop(timestamp, None)      # pas de ligne d'index pour un instantané nu
        self._save_index(index)
        return meta

    # ---------- cycle de vie ----------
    def archive(self, state, label="", pinned=False):
        ts = datetime.now(timezone.utc).strftime(TS_FORMAT)
        self.storage.atomic_write(os.path.join(self.dir, f"{ts}.json"), state)
        if label or pinned:
            index = self._index()
            index[ts] = {"label": str(label).strip()[:self.LABEL_MAX], "pinned": bool(pinned)}
            self._save_index(index)
        self._prune()
        return ts

    def _remove(self, fname):
        try:
            os.unlink(os.path.join(self.dir, fname))
            return True
        except OSError:
            return False

    def _snapshots(self):
        return sorted(f for f in os.listdir(self.dir)
                      if f.endswith(".json") and f != "index.json")

    def _prune(self):
        """Purge par ÂGE puis par NOMBRE. Les repères épinglés traversent les deux :
        c'est exactement ce qu'on leur demande."""
        index = self._index()
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.RETENTION_DAYS)
        supprimes = []
        kept = []
        for fname in self._snapshots():
            ts = fname[:-5]
            if self._meta(index, ts)["pinned"]:
                continue                                   # épinglé : jamais purgé
            dt = self._parse_ts(ts)
            if dt is not None and dt < cutoff:
                self._remove(fname)                        # trop ancien (> 30 jours)
                supprimes.append(ts)
            else:
                kept.append(fname)
        for fname in kept[:-self.MAX_SNAPSHOTS]:           # au-delà du plafond, les plus vieux
            self._remove(fname)
            supprimes.append(fname[:-5])
        if supprimes:
            for ts in supprimes:
                index.pop(ts, None)                        # pas de métadonnée orpheline
            self._save_index(index)

    def clear(self, keep_pinned=True):
        """Supprime l'historique. Retourne le nombre d'instantanés effacés.

        Les repères épinglés sont conservés par défaut : les avoir mis à l'abri de la
        purge automatique et les perdre au premier « vider » serait incohérent.
        """
        index = self._index()
        efface = 0
        for fname in self._snapshots():
            ts = fname[:-5]
            if keep_pinned and self._meta(index, ts)["pinned"]:
                continue
            if self._remove(fname):
                efface += 1
                index.pop(ts, None)
        self._save_index(index)
        return efface

    @staticmethod
    def _parse_ts(ts):
        try:
            return datetime.strptime(ts, TS_FORMAT).replace(tzinfo=timezone.utc)
        except ValueError:
            return None

    def list(self):
        index = self._index()
        items = []
        for fname in self._snapshots():
            ts = fname[:-5]
            meta = self._meta(index, ts)
            items.append({"timestamp": ts, "datetime": self._humanize(ts),
                          "label": meta["label"], "pinned": meta["pinned"]})
        return sorted(items, key=lambda x: x["timestamp"], reverse=True)

    def load(self, timestamp):
        path = os.path.join(self.dir, f"{timestamp}.json")
        if not os.path.exists(path):
            raise KeyError(timestamp)
        data = self.storage.read_json(path)   # tolérant à la corruption (.bak / None)
        if data is None:
            raise KeyError(timestamp)
        return data

    @staticmethod
    def _humanize(ts):
        try:
            # Le « Z » du format est un littéral : strptime rendrait un datetime naïf.
            # On rattache UTC explicitement — l'affichage est inchangé, mais la valeur
            # devient comparable sans piège si elle sert un jour à autre chose.
            dt = datetime.strptime(ts, TS_FORMAT).replace(tzinfo=timezone.utc)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            return ts
