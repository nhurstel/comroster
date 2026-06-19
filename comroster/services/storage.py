import json
import os
import tempfile
import threading

from . import model

_WRITE_LOCK = threading.Lock()


class Storage:
    def __init__(self, data_dir):
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
        self.draft_path = os.path.join(data_dir, "data_draft.json")
        self.published_path = os.path.join(data_dir, "data_published.json")
        self.history_dir = os.path.join(data_dir, "history")

    def atomic_write(self, path, data):
        payload = json.dumps(data, ensure_ascii=False, indent=2)
        directory = os.path.dirname(path) or "."
        with _WRITE_LOCK:
            fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    fh.write(payload)
                    fh.flush()
                    os.fsync(fh.fileno())
                os.replace(tmp, path)
            except BaseException:
                if os.path.exists(tmp):
                    os.unlink(tmp)
                raise

    def _load(self, path):
        if not os.path.exists(path):
            return None
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)

    def load_draft(self):
        state = self._load(self.draft_path)
        return state if state is not None else model.empty_state()

    def save_draft(self, state):
        self.atomic_write(self.draft_path, state)

    def load_published(self):
        return self._load(self.published_path)

    def save_published(self, state):
        self.atomic_write(self.published_path, state)
