"""Journal d'événements : ce qu'il s'est PASSÉ sur le boîtier.

Complémentaire de l'historique (qui archive des ÉTATS publiés restaurables) :
le journal trace les ÉVÉNEMENTS — publications, imports, connexions antenne,
changements réseau, redémarrages — pour répondre à « que s'est-il passé ? ».

Fichier JSONL borné dans DATA_DIR, réécrit atomiquement à chaque événement
(≤ MAX_EVENTS lignes : le coût est négligeable et la taille ne dérive jamais —
garde-fou carte SD). Écrit sous verrou : les requêtes arrivent de plusieurs
threads. Fail-safe appliance : une ligne corrompue est ignorée, jamais levée.
"""
import json
import os
import threading
from datetime import datetime, timezone


class Journal:
    MAX_EVENTS = 200

    def __init__(self, data_dir):
        self.path = os.path.join(data_dir, "journal.jsonl")
        self._lock = threading.Lock()

    def record(self, event, detail=""):
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "event": str(event),
            "detail": str(detail),
        }
        with self._lock:
            entries = self._read()
            entries.append(entry)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                for e in entries[-self.MAX_EVENTS:]:
                    f.write(json.dumps(e, ensure_ascii=False) + "\n")
            os.replace(tmp, self.path)
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
