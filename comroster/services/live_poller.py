"""Poussée temps réel de l'état des beltpacks (SSE) au lieu du polling client.

Un seul thread de fond interroge l'antenne et publie un évènement `live` sur le
broker *uniquement quand l'état change* — et *uniquement s'il y a des abonnés*
(afficheurs connectés). Le flux `/events` relaie l'évènement tel quel ; côté
navigateur, plus aucune requête périodique. L'antenne n'est interrogée qu'une
fois, quel que soit le nombre d'écrans.
"""
import threading
import time

from ..security import state_lock
from . import model
from .antenna import AntennaError
from .publisher import broadcast_published


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


def sync_roster_once(app):
    """Aligne le brouillon sur le roster de l'antenne et publie si ça a changé.

    Ne fait rien tant que l'auto-sync est désactivée ou l'antenne déconnectée.
    Stateless et idempotent : chaque appel relit le roster et n'agit QUE sur un
    vrai écart (nom/ajout/retrait dans le périmètre des plages). L'appel réseau
    se fait HORS `state_lock` ; seul le read-modify-write du brouillon est verrouillé.
    """
    settings = app.extensions["settings"]
    if not settings.get("auto_sync", False):
        return
    client = app.extensions["antenna"]
    if not getattr(client, "connected", False):
        return
    try:
        items = client.fetch_beltpacks()
    except AntennaError:
        return                              # réseau : on retentera au prochain tick

    storage = app.extensions["storage"]
    with state_lock:
        ranges = settings.get("antenna_ranges", [])
        filtered = model.filter_by_ranges(items, ranges)
        state = storage.load_draft()
        res = model.mirror_beltpacks(state, filtered, ranges=ranges)
        if not (res["created"] or res["updated"] or res["removed"]):
            return                          # rien de neuf → ni écriture ni publication
        storage.save_draft(state)
        try:
            model.validate_state(state)
        except model.ValidationError:
            return                          # brouillon invalide → maj brouillon seule
        broadcast_published(app, state)     # décision Nathan : publie direct sur l'affichage


def start_live_poller(app):
    broker = app.extensions["broker"]
    client = app.extensions["antenna"]
    interval = app.config.get("ANTENNA_POLL_INTERVAL", 3.0)
    roster_interval = app.config.get("ANTENNA_ROSTER_INTERVAL", 10.0)

    def loop():
        prev = None
        last_roster = 0.0
        while True:
            time.sleep(interval)
            prev = poll_once(broker, client, prev)
            now = time.monotonic()
            if now - last_roster >= roster_interval:
                last_roster = now
                try:
                    sync_roster_once(app)
                except Exception:           # noqa: BLE001 — le poller ne meurt jamais
                    pass

    threading.Thread(target=loop, daemon=True, name="antenna-live-poller").start()
