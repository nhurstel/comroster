import json
import os
from datetime import datetime, timezone


class History:
    def __init__(self, storage):
        self.storage = storage
        self.dir = storage.history_dir
        os.makedirs(self.dir, exist_ok=True)

    def archive(self, state):
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        self.storage.atomic_write(os.path.join(self.dir, f"{ts}.json"), state)
        return ts

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
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)

    @staticmethod
    def _humanize(ts):
        try:
            dt = datetime.strptime(ts, "%Y%m%dT%H%M%S%fZ")
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            return ts
