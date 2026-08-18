"""Journal d'événements : ce qu'il s'est PASSÉ sur le boîtier.

Complémentaire de l'historique (qui archive des ÉTATS publiés restaurables) :
le journal trace les ÉVÉNEMENTS — publications, imports, connexions antenne,
changements réseau, redémarrages — pour répondre à « que s'est-il passé ? ».

Fichier JSONL borné dans DATA_DIR, réécrit atomiquement à chaque événement
(≤ MAX_EVENTS lignes : le coût est négligeable et la taille ne dérive jamais —
garde-fou carte SD). Écrit sous verrou : les requêtes arrivent de plusieurs
threads. Fail-safe appliance : une ligne corrompue est ignorée, jamais levée —
et l'ÉCRITURE l'est tout autant. `record()` est appelé depuis `create_app()`
(événement `startup`) : une exception ici ne casserait plus une seule requête,
elle empêcherait le boîtier de démarrer. Perdre une ligne de journal est
acceptable ; empêcher l'allumage avant un spectacle ne l'est pas.
"""
import contextlib
import json
import logging
import os
import threading
from datetime import UTC, datetime

log = logging.getLogger(__name__)


class Journal:
    MAX_EVENTS = 200

    def __init__(self, data_dir):
        self.path = os.path.join(data_dir, "journal.jsonl")
        self._lock = threading.Lock()

    def record(self, event, detail=""):
        entry = {
            "ts": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "event": str(event),
            "detail": str(detail),
        }
        with self._lock:
            entries = self._read()
            entries.append(entry)
            tmp = self.path + ".tmp"
            try:
                with open(tmp, "w", encoding="utf-8") as f:
                    f.writelines(
                        json.dumps(e, ensure_ascii=False) + "\n"
                        for e in entries[-self.MAX_EVENTS:]
                    )
                os.replace(tmp, self.path)          # remplacement atomique
            except OSError as exc:
                # DATA_DIR non inscriptible, disque plein… : `record()` est appelé
                # depuis create_app() (événement `startup`), donc une exception ici
                # empêcherait le boîtier de démarrer — bien pire que perdre une ligne.
                log.warning("Journal non enregistré : %s", exc)
                with contextlib.suppress(OSError):
                    os.remove(tmp)          # ne laisse pas de fichier partiel derrière
        return entry

    def entries(self):
        """Les événements, le plus récent d'abord."""
        with self._lock:
            return list(reversed(self._read()))

    def _read(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                out = []
                for line in f:
                    try:
                        e = json.loads(line)
                    except ValueError:
                        continue            # ligne corrompue : ignorée (fail-safe)
                    if isinstance(e, dict):
                        out.append(e)
                return out
        except OSError:
            return []
