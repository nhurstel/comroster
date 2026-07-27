import contextlib
import queue
import threading


class Broker:
    def __init__(self):
        self._subscribers = []
        self._lock = threading.Lock()

    def subscribe(self):
        q = queue.Queue(maxsize=100)
        with self._lock:
            self._subscribers.append(q)
        return q

    def unsubscribe(self, q):
        with self._lock:
            if q in self._subscribers:
                self._subscribers.remove(q)

    def publish(self, event, data):
        with self._lock:
            targets = list(self._subscribers)
        for q in targets:
            # File pleine = abonné trop lent : on lui abandonne l'évènement plutôt que
            # de bloquer la publication pour tous les autres.
            with contextlib.suppress(queue.Full):
                q.put_nowait((event, data))

    @property
    def subscriber_count(self):
        with self._lock:
            return len(self._subscribers)
