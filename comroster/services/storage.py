import contextlib
import json
import logging
import os
import shutil
import tempfile
import threading
import time

from . import model

_WRITE_LOCK = threading.Lock()
_log = logging.getLogger("comroster.storage")

#: Espacement des copies `.bak` DU BROUILLON. Même raisonnement que les points de reprise
#: du carnet de bord : 5 minutes d'écart au pire, contre une copie intégrale du fichier à
#: chaque salve de frappe. Les états qui comptent vraiment — le publié, les instantanés
#: d'historique, les configurations nommées — gardent leur sauvegarde systématique : ils
#: ne s'écrivent qu'à une action explicite, jamais en rafale.
DRAFT_BACKUP_INTERVAL_S = 300


class Storage:
    def __init__(self, data_dir):
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
        self.draft_path = os.path.join(data_dir, "data_draft.json")
        self.published_path = os.path.join(data_dir, "data_published.json")
        self.history_dir = os.path.join(data_dir, "history")

    def _backup_due(self, path, min_interval):
        """La copie `.bak` est-elle due ? (min_interval = 0 → toujours)"""
        if min_interval <= 0:
            return True
        try:
            age = time.time() - os.stat(path + ".bak").st_mtime
        except OSError:
            return True                    # pas encore de sauvegarde : on en veut une
        return age >= min_interval

    def atomic_write(self, path, data, backup_min_interval=0):
        """Écrit `data` en JSON, de façon atomique et durable.

        `backup_min_interval` (secondes, 0 = à chaque écriture) espace les copies `.bak`.
        Le brouillon est réenregistré à chaque salve de frappe : en copier intégralement
        le fichier à chaque fois produisait, sur une saisie soutenue, plusieurs copies par
        seconde sur la carte SD du boîtier — en contradiction directe avec le soin pris
        ailleurs (le carnet de bord, lui, n'écrit que toutes les 5 minutes).

        Espacer la copie ne coûte presque rien : le `.bak` ne sert qu'à récupérer un
        fichier CORROMPU (coupure de courant en pleine écriture), et une sauvegarde vieille
        de quelques minutes vaut infiniment mieux qu'un état vide. L'écriture elle-même
        reste atomique et fsyncée à CHAQUE appel — c'est elle qui protège du scénario
        courant, pas la copie.
        """
        payload = json.dumps(data, ensure_ascii=False, indent=2)
        directory = os.path.dirname(path) or "."
        with _WRITE_LOCK:
            # Sauvegarde de la dernière version connue-bonne (récupération si corruption)
            if os.path.exists(path) and self._backup_due(path, backup_min_interval):
                with contextlib.suppress(OSError):
                    shutil.copyfile(path, path + ".bak")
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
        # Seule écriture en RAFALE de l'application (une par salve de frappe) : c'est la
        # seule à espacer sa sauvegarde. Voir DRAFT_BACKUP_INTERVAL_S.
        self.atomic_write(self.draft_path, state,
                          backup_min_interval=DRAFT_BACKUP_INTERVAL_S)

    def load_published(self):
        return self._load(self.published_path)

    def save_published(self, state):
        self.atomic_write(self.published_path, state)
