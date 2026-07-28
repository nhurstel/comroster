from comroster.services.live_poller import poll_once
from comroster.services.pubsub import Broker


def _drain(q, event=None):
    """Vide la file en écartant les annonces d'INTENDANCE du broker (`displays`).

    Depuis l'audit 2026-07-28, s'abonner/se désabonner pousse le nombre d'écrans à tout le
    monde : ces tests ne peuvent donc plus supposer « le premier évènement de la file est
    le mien ». On saute donc l'intendance — et, si `event` est donné, on va chercher CE
    type-là plutôt que le premier venu.
    """
    import queue as _q
    while True:
        try:
            item = q.get_nowait()
        except _q.Empty:
            return None
        if item[0] == "displays":
            continue
        if event is None or item[0] == event:
            return item


def _is_empty(q):
    """La file ne contient plus que de l'intendance ?"""
    return _drain(q) is None


class FakeClient:
    def __init__(self, *states):
        self._states = list(states)
        self.calls = 0

    def live_status(self):
        self.calls += 1
        return self._states[min(self.calls - 1, len(self._states) - 1)]


def _sub(broker):
    q = broker.subscribe()
    return q


def test_no_subscribers_does_not_poll():
    broker = Broker()
    client = FakeClient({"connected": True, "beltpacks": {}})
    prev = poll_once(broker, client, None)
    assert prev is None
    assert client.calls == 0          # l'antenne n'est pas sollicitée sans écran


def test_publishes_live_on_change():
    broker = Broker()
    q = _sub(broker)
    a = {"connected": True, "beltpacks": {"7": {"online": True}}}
    b = {"connected": True, "beltpacks": {"7": {"online": False}}}
    prev = poll_once(broker, FakeClient(a), None)
    assert prev == a
    assert _drain(q) == ("live", a)
    # même état → aucun nouveau push
    prev = poll_once(broker, FakeClient(a), prev)
    assert _is_empty(q)
    # état différent → push
    prev = poll_once(broker, FakeClient(b), prev)
    assert prev == b
    assert _drain(q) == ("live", b)


def test_client_error_keeps_previous_state():
    broker = Broker()
    _sub(broker)

    class Boom:
        def live_status(self):
            raise RuntimeError("antenne injoignable")

    prev = {"connected": True, "beltpacks": {}}
    assert poll_once(broker, Boom(), prev) == prev   # ne lève pas, conserve l'état
