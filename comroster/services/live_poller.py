"""Poussée temps réel de l'état des beltpacks (SSE) au lieu du polling client.

Un seul thread de fond interroge l'antenne et publie un évènement `live` sur le
broker *uniquement quand l'état change* — et *uniquement s'il y a des abonnés*
(afficheurs connectés). Le flux `/events` relaie l'évènement tel quel ; côté
navigateur, plus aucune requête périodique. L'antenne n'est interrogée qu'une
fois, quel que soit le nombre d'écrans.
"""
import threading
import time


def poll_once(broker, client, prev):
    """Un tick : publie `live` si l'état a changé. Retourne le nouvel état de référence.

    - Aucun abonné → on ne sollicite pas l'antenne et on oublie l'état précédent
      (au prochain abonné, on repoussera l'état complet).
    - Erreur réseau → on conserve l'état précédent sans lever.
    """
    if broker.subscriber_count == 0:
        return None
    try:
        data = client.live_status()
    except Exception:              # noqa: BLE001 — le poller ne doit jamais mourir
        return prev
    if data != prev:
        broker.publish("live", data)
        return data
    return prev


def start_live_poller(app):
    broker = app.extensions["broker"]
    client = app.extensions["antenna"]
    interval = app.config.get("ANTENNA_POLL_INTERVAL", 3.0)

    def loop():
        prev = None
        while True:
            time.sleep(interval)
            prev = poll_once(broker, client, prev)

    threading.Thread(target=loop, daemon=True, name="antenna-live-poller").start()
