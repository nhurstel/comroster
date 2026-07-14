import os
from datetime import datetime, timedelta, timezone


class History:
    RETENTION_DAYS = 30     # les publications de plus de 30 jours sont supprimées automatiquement
    MAX_SNAPSHOTS = 50      # garde-fou anti-débordement de la carte SD du boîtier

    def __init__(self, storage):
        self.storage = storage
        self.dir = storage.history_dir
        os.makedirs(self.dir, exist_ok=True)

    def archive(self, state):
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        self.storage.atomic_write(os.path.join(self.dir, f"{ts}.json"), state)
        self._prune()
        return ts

    def _remove(self, fname):
        try:
            os.unlink(os.path.join(self.dir, fname))
            return True
        except OSError:
            return False

    def _prune(self):
        snaps = sorted(f for f in os.listdir(self.dir) if f.endswith(".json"))
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.RETENTION_DAYS)
        kept = []
        for fname in snaps:
            dt = self._parse_ts(fname[:-5])
            if dt is not None and dt < cutoff:
                self._remove(fname)                    # trop ancien (> 30 jours)
            else:
                kept.append(fname)
        for fname in kept[:-self.MAX_SNAPSHOTS]:       # garde-fou : au-delà du plafond, on coupe les plus vieux
            self._remove(fname)

    def clear(self):
        """Supprime tout l'historique. Retourne le nombre de snapshots effacés."""
        return sum(
            self._remove(f) for f in os.listdir(self.dir) if f.endswith(".json")
        )

    @staticmethod
    def _parse_ts(ts):
        try:
            return datetime.strptime(ts, "%Y%m%dT%H%M%S%fZ").replace(tzinfo=timezone.utc)
        except ValueError:
            return None

    def list(self):
        items = []
        for fname in os.listdir(self.dir):
            if fname.endswith(".json"):
                ts = fname[:-5]
                items.append({"timestamp": ts, "datetime": self._humanize(ts)})
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
            dt = datetime.strptime(ts, "%Y%m%dT%H%M%S%fZ")
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            return ts
