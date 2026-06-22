import json
import logging
import os
import shutil
import tempfile
import threading

from . import model

_WRITE_LOCK = threading.Lock()
_log = logging.getLogger("comroster.storage")


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
            # Sauvegarde de la dernière version connue-bonne (récupération si corruption)
            if os.path.exists(path):
                try:
                    shutil.copyfile(path, path + ".bak")
                except OSError:
                    pass
            fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    fh.write(payload)
                    fh.flush()
                    os.fsync(fh.fileno())
                os.replace(tmp, path)
                # Durabilité : fsync du répertoire pour que le rename survive à une coupure
                try:
                    dfd = os.open(directory, os.O_RDONLY)
                    os.fsync(dfd)
                    os.close(dfd)
                except OSError:
                    pass
            except BaseException:
                if os.path.exists(tmp):
                    os.unlink(tmp)
                raise

    def _read_json(self, path):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)

    def _load(self, path):
        if not os.path.exists(path):
            return None
        try:
            return self._read_json(path)
        except (OSError, json.JSONDecodeError) as exc:
            # Fichier corrompu (ex. coupure de courant) → on récupère plutôt que bricker
            # le boîtier, mais sans masquer : on journalise l'incident.
            bak = path + ".bak"
            if os.path.exists(bak):
                try:
                    data = self._read_json(bak)
                    _log.warning("%s corrompu (%s) — récupéré depuis %s", path, exc, bak)
                    return data
                except (OSError, json.JSONDecodeError):
                    pass
            _log.error("%s corrompu (%s) et aucune sauvegarde valide — état réinitialisé", path, exc)
            return None

    def read_json(self, path):
        """Lecture JSON tolérante (récupère depuis .bak si corrompu, None si illisible).

        Partagée par les stores secondaires (settings, configs, history) pour qu'un
        fichier corrompu ne fasse jamais planter le boîtier.
        """
        return self._load(path)

    def load_draft(self):
        state = self._load(self.draft_path)
        return state if state is not None else model.empty_state()

    def save_draft(self, state):
        self.atomic_write(self.draft_path, state)

    def load_published(self):
        return self._load(self.published_path)

    def save_published(self, state):
        self.atomic_write(self.published_path, state)
