import os
from datetime import datetime, timezone


class History:
    MAX_SNAPSHOTS = 50      # rétention : évite que l'historique gonfle la SD du boîtier

    def __init__(self, storage):
        self.storage = storage
        self.dir = storage.history_dir
        os.makedirs(self.dir, exist_ok=True)

    def archive(self, state):
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        self.storage.atomic_write(os.path.join(self.dir, f"{ts}.json"), state)
        self._prune()
        return ts

    def _prune(self):
        snaps = sorted(f for f in os.listdir(self.dir) if f.endswith(".json"))
        for fname in snaps[:-self.MAX_SNAPSHOTS]:      # on garde les MAX_SNAPSHOTS plus récents
            try:
                os.unlink(os.path.join(self.dir, fname))
            except OSError:
                pass

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
