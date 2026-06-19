from comroster.services.pubsub import Broker


def test_subscribe_receives_published_event():
    b = Broker()
    q = b.subscribe()
    b.publish("published", {"x": 1})
    event, data = q.get_nowait()
    assert event == "published" and data == {"x": 1}


def test_unsubscribe_stops_delivery():
    b = Broker()
    q = b.subscribe()
    assert b.subscriber_count == 1
    b.unsubscribe(q)
    assert b.subscriber_count == 0
    b.publish("published", {"x": 1})
    assert q.empty()


def test_multiple_subscribers():
    b = Broker()
    q1, q2 = b.subscribe(), b.subscribe()
    b.publish("published", {"v": 2})
    assert q1.get_nowait()[1] == {"v": 2}
    assert q2.get_nowait()[1] == {"v": 2}
