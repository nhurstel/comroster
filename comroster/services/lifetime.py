"""Carnet de bord du boîtier : depuis quand il existe, et combien il a tourné.

`/proc/uptime` ne répond qu'à « depuis quand est-il allumé ». Sur une appliance qu'on
éteint entre deux prestations, la question utile est plutôt « ce boîtier a-t-il déjà
vécu ? » — d'où trois valeurs persistées : la date de première mise en service, le
cumul de fonctionnement à travers les redémarrages, et le nombre de démarrages.

Le cumul VIT en mémoire (origine monotone) et n'est écrit sur disque que
périodiquement : le fichier n'est qu'un point de reprise. Deux raisons de ne pas
écrire souvent — l'usure de la carte SD, et le fait qu'une coupure de courant ne perd
au pire que l'intervalle. `time.monotonic()` et non `time.time()` : un réglage
d'horloge (NTP au premier boot réseau) ne doit pas créer ni effacer des heures de
fonctionnement.

Politique appliance (fail-safe) : un fichier illisible ou corrompu est mis de côté en
`.bak` et le carnet repart à zéro, avec un avertissement journalisé — jamais une
exception qui empêcherait la page Santé de s'afficher.
"""
import contextlib
import json
import logging
import os
import threading
import time
from datetime import datetime, timezone

log = logging.getLogger(__name__)

#: Intervalle des points de reprise. 5 min = 288 écritures/jour : négligeable pour la
#: carte SD, et une coupure brutale ne coûte au pire que 5 min sur un compteur qui se
#: lit en jours.
CHECKPOINT_S = 300


def _now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class Lifetime:
    def __init__(self, data_dir, checkpoint_s=CHECKPOINT_S):
        self.path = os.path.join(data_dir, "lifetime.json")
        self.checkpoint_s = checkpoint_s
        self._origin = time.monotonic()
        self._lock = threading.Lock()
        self._data = self._load()
        self._base_runtime = int(self._data.get("total_runtime_s") or 0)

    # ---------- persistance ----------
    def _load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("racine non-objet")
            return data
        except FileNotFoundError:
            return {}
        except (OSError, ValueError) as exc:
            # Fail-safe : on préserve la pièce à conviction et on repart à neuf.
            log.warning("Carnet de bord illisible (%s) — remis à zéro, ancien fichier en .bak", exc)
            with contextlib.suppress(OSError):
                os.replace(self.path, self.path + ".bak")
            return {}

    def _write(self, data):
        tmp = self.path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            os.replace(tmp, self.path)          # remplacement atomique
        except OSError as exc:
            log.warning("Carnet de bord non enregistré : %s", exc)

    # ---------- cycle de vie ----------
    def register_start(self):
        """Marque un démarrage. Appelé une fois par processus, au boot."""
        with self._lock:
            self._data.setdefault("installed_at", _now_iso())
            self._data["starts"] = int(self._data.get("starts") or 0) + 1
            self._data["total_runtime_s"] = self._base_runtime
            self._data["last_seen_at"] = _now_iso()
            self._write(dict(self._data))

    def checkpoint(self):
        """Reporte sur disque le fonctionnement écoulé depuis le démarrage."""
        with self._lock:
            self._data["total_runtime_s"] = self._base_runtime + self.session_s()
            self._data["last_seen_at"] = _now_iso()
            self._write(dict(self._data))

    def session_s(self):
        return int(time.monotonic() - self._origin)

    def snapshot(self):
        """Le cumul rendu est CALCULÉ, pas relu : il reste juste entre deux points de
        reprise (sinon la page afficherait une valeur figée jusqu'à 5 min)."""
        with self._lock:
            return {
                "installed_at": self._data.get("installed_at"),
                "starts": int(self._data.get("starts") or 0),
                "total_runtime_s": self._base_runtime + self.session_s(),
                "session_s": self.session_s(),
            }


def start_checkpoints(app):
    """Fil de fond qui pose un point de reprise périodique. Jamais sous tests."""
    lifetime = app.extensions["lifetime"]

    def loop():
        while True:
            time.sleep(lifetime.checkpoint_s)
            try:
                lifetime.checkpoint()
            except Exception:      # un carnet de bord ne fait jamais tomber l'application
                log.exception("Point de reprise du carnet de bord impossible")

    thread = threading.Thread(target=loop, name="comroster-lifetime", daemon=True)
    thread.start()
    return thread
