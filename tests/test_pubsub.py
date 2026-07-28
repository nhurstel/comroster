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


def test_subscribe_receives_published_event():
    b = Broker()
    q = b.subscribe()
    b.publish("published", {"x": 1})
    event, data = _drain(q)
    assert event == "published" and data == {"x": 1}


def test_unsubscribe_stops_delivery():
    b = Broker()
    q = b.subscribe()
    assert b.subscriber_count == 1
    b.unsubscribe(q)
    assert b.subscriber_count == 0
    b.publish("published", {"x": 1})
    assert _is_empty(q)


def test_multiple_subscribers():
    b = Broker()
    q1, q2 = b.subscribe(), b.subscribe()
    b.publish("published", {"v": 2})
    assert _drain(q1)[1] == {"v": 2}
    assert _drain(q2)[1] == {"v": 2}
