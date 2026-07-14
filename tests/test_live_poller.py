from comroster.services.pubsub import Broker
from comroster.services.live_poller import poll_once


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
    assert q.get_nowait() == ("live", a)
    # même état → aucun nouveau push
    prev = poll_once(broker, FakeClient(a), prev)
    assert q.empty()
    # état différent → push
    prev = poll_once(broker, FakeClient(b), prev)
    assert prev == b
    assert q.get_nowait() == ("live", b)


def test_client_error_keeps_previous_state():
    broker = Broker()
    _sub(broker)

    class Boom:
        def live_status(self):
            raise RuntimeError("antenne injoignable")

    prev = {"connected": True, "beltpacks": {}}
    assert poll_once(broker, Boom(), prev) == prev   # ne lève pas, conserve l'état
