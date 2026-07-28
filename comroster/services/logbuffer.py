"""Tampon circulaire des logs applicatifs — le volet « Technique » de la page Journal.

Un `logging.Handler` accroché à la racine capte tout ce que le process journalise
(app Flask, services, bibliothèques) dans un deque borné, consultable par l'API :
du debug SANS SSH sur le boîtier, là où `journalctl` demanderait un accès machine.

En mémoire seulement, volontairement : les logs techniques servent au diagnostic de
la session en cours ; ce qui doit survivre à un redémarrage a sa place dans le
journal d'ÉVÉNEMENTS (services/journal.py), pas ici. Le deque est thread-safe pour
append/lecture (verrou GIL), et `logging` sérialise déjà les emit par handler.
"""
import collections
import logging
from datetime import datetime, timezone

#: Journaux d'ACCÈS HTTP : une ligne par requête, fichiers statiques compris. Un seul
#: chargement de page en produit plusieurs dizaines, qui chassent du tampon les lignes
#: réellement utiles au diagnostic. Savoir qu'un .woff2 a été servi n'a jamais aidé
#: personne en régie. `werkzeug` est le serveur de développement, `gunicorn.access` son
#: équivalent en production.
ACCESS_LOGGERS = ("werkzeug", "gunicorn.access")


class LogBuffer(logging.Handler):
    CAPACITY = 500

    def __init__(self):
        super().__init__(level=logging.INFO)
        self.records = collections.deque(maxlen=self.CAPACITY)

    def emit(self, record):
        # Écartés SEULEMENT en dessous de WARNING : une vraie erreur du serveur HTTP
        # (requête refusée, exception non rattrapée) doit rester visible sans SSH.
        if record.levelno < logging.WARNING and record.name.startswith(ACCESS_LOGGERS):
            return
        try:
            message = record.getMessage()
            if record.exc_info and record.exc_info[1] is not None:
                message += f" — {type(record.exc_info[1]).__name__}: {record.exc_info[1]}"
        except Exception:      # noqa: BLE001 — jamais de crash depuis un handler de log
            message = "<message informatable>"
        self.records.append({
            "ts": datetime.fromtimestamp(record.created, timezone.utc)
                  .isoformat(timespec="seconds").replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": message,
        })

    def entries(self):
        """Les logs captés, le plus récent d'abord."""
        return list(self.records)[::-1]


def install(app):
    """Accroche un tampon à la racine du logging et l'enregistre comme extension.

    La racine est abaissée à INFO (défaut Python : WARNING) pour capter la vie
    normale de l'app — le handler « lastResort » vers stderr reste à WARNING, la
    sortie console ne change donc pas. Les tampons d'apps précédentes (suites de
    tests : une app par test) sont décrochés pour ne pas s'empiler.
    """
    root = logging.getLogger()
    for h in list(root.handlers):
        if isinstance(h, LogBuffer):
            root.removeHandler(h)
    buf = LogBuffer()
    root.addHandler(buf)
    if root.level in (logging.NOTSET, logging.WARNING):
        root.setLevel(logging.INFO)
    app.extensions["logbuffer"] = buf
    return buf
