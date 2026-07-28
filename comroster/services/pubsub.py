"""Diffusion d'évènements aux abonnés SSE (écrans de régie et pages d'administration).

Les abonnés sont TYPÉS. Sans cette distinction, la page d'administration — qui ouvre elle
aussi un flux `/events` pour se resynchroniser — se comptait comme un écran de régie :
ouvrir l'admin sans le moindre écran branché affichait « 1 afficheur », dans la barre
d'état ET dans la ligne de vie de la page Santé, celle qui répond à « puis-je lancer le
show ? ». Un écran d'état qui invente un afficheur est pire qu'un écran d'état absent
(audit 2026-07-28).

Deux compteurs, deux usages distincts :
  • `subscriber_count` (TOTAL) borne l'occupation du pool de threads gunicorn — chaque
    flux en occupe un en continu, quel que soit son type.
  • `display_count` répond à « combien d'écrans de régie affichent réellement ? ». C'est
    lui, et lui seul, qui a le droit d'aller à l'écran.
"""
import contextlib
import queue
import threading

#: Écran de régie (/display, kiosk). C'est le DÉFAUT : un abonné non qualifié est traité
#: comme un écran — l'hypothèse la plus prudente, pour le cap comme pour l'affichage.
DISPLAY = "display"
#: Page d'administration. Occupe un thread, mais n'affiche rien en salle.
ADMIN = "admin"
KINDS = (DISPLAY, ADMIN)


def sanitize_kind(value):
    """Allowlist stricte : un `?role=` inconnu ou absent compte comme un écran."""
    return value if value in KINDS else DISPLAY


class Broker:
    def __init__(self):
        # dict {queue: kind} — ordre d'insertion garanti, et retrait en O(1) (la liste
        # imposait un parcours complet à chaque désabonnement).
        self._subscribers = {}
        self._lock = threading.Lock()

    def subscribe(self, kind=DISPLAY):
        q = queue.Queue(maxsize=100)
        with self._lock:
            self._subscribers[q] = sanitize_kind(kind)
        self._announce_displays()
        return q

    def unsubscribe(self, q):
        with self._lock:
            partait = self._subscribers.pop(q, None) is not None
        if partait:
            self._announce_displays()

    def _announce_displays(self):
        """Pousse le nouveau nombre d'écrans à tous les abonnés.

        Sans cette annonce, la barre d'état de l'admin restait figée sur le compte du
        chargement : brancher un écran de régie ne se voyait qu'à la publication
        suivante. C'est le corollaire de la leçon du 2026-06-22 pour un changement
        DISTANT — il n'y a ici aucune action locale après laquelle rafraîchir, c'est donc
        au serveur d'annoncer.

        HORS VERROU, impérativement : `publish()` reprend le même verrou, non réentrant.
        """
        self.publish("displays", {"displays": self.display_count})

    def publish(self, event, data):
        with self._lock:
            targets = list(self._subscribers)
        for q in targets:
            # File pleine = abonné trop lent : on lui abandonne l'évènement plutôt que
            # de bloquer la publication pour tous les autres.
            with contextlib.suppress(queue.Full):
                q.put_nowait((event, data))

    def count(self, kind=None):
        """Abonnés de ce type — ou tous types confondus si `kind` est None."""
        with self._lock:
            if kind is None:
                return len(self._subscribers)
            return sum(1 for k in self._subscribers.values() if k == kind)

    @property
    def subscriber_count(self):
        """TOTAL des flux ouverts : la mesure de l'occupation du pool de threads."""
        return self.count()

    @property
    def display_count(self):
        """Écrans de régie seuls : la seule valeur qu'on ait le droit d'afficher."""
        return self.count(DISPLAY)
