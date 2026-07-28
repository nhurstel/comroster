"""Un onglet d'administration n'est pas un écran de régie.

La page d'admin s'abonne au flux `/events` pour se resynchroniser. Le broker comptait tous
les abonnés indistinctement : ouvrir l'admin, sans le moindre écran branché, affichait
« 1 afficheur » dans la barre d'état ET dans la ligne de vie de la page Santé — celle qui
répond à « puis-je lancer le show ? ». Un écran d'état qui invente un afficheur est pire
qu'un écran d'état absent (audit 2026-07-28).

Deux compteurs distincts, donc, avec deux rôles : le TOTAL borne le pool de threads, les
ÉCRANS seuls vont à l'affichage.
"""
import pytest

from comroster.services import pubsub


@pytest.fixture
def broker(app):
    return app.extensions["broker"]


def test_un_abonne_non_qualifie_compte_comme_un_ecran(broker):
    """Défaut le plus prudent : sans `?role=`, on suppose un écran."""
    q = broker.subscribe()
    try:
        assert broker.display_count == 1
        assert broker.subscriber_count == 1
    finally:
        broker.unsubscribe(q)


def test_un_abonne_admin_ne_compte_pas_comme_un_ecran(broker):
    q = broker.subscribe(pubsub.ADMIN)
    try:
        assert broker.display_count == 0, "l'admin ne diffuse rien en salle"
        assert broker.subscriber_count == 1, "…mais il occupe bien un thread"
    finally:
        broker.unsubscribe(q)


def test_un_role_inconnu_retombe_sur_ecran(broker):
    q = broker.subscribe("n-importe-quoi")
    try:
        assert broker.display_count == 1
    finally:
        broker.unsubscribe(q)


def test_api_status_ne_compte_que_les_ecrans(auth_client, app):
    """C'est le chemin exact qui mentait : /api/status alimente la barre d'état."""
    broker = app.extensions["broker"]
    admin = broker.subscribe(pubsub.ADMIN)
    try:
        assert auth_client.get("/api/status").get_json()["displays"] == 0
        ecran = broker.subscribe(pubsub.DISPLAY)
        try:
            assert auth_client.get("/api/status").get_json()["displays"] == 1
        finally:
            broker.unsubscribe(ecran)
    finally:
        broker.unsubscribe(admin)


def test_api_health_ne_compte_que_les_ecrans(auth_client, app):
    """Même exigence sur la page Santé : c'est elle qui autorise à lancer le show."""
    broker = app.extensions["broker"]
    admin = broker.subscribe(pubsub.ADMIN)
    try:
        assert auth_client.get("/api/health").get_json()["displays"] == 0
    finally:
        broker.unsubscribe(admin)


def test_events_enregistre_le_role_demande(app, client):
    """`/events?role=admin` doit produire un abonné ADMIN, pas un écran."""
    resp = client.get("/events?role=admin")
    try:
        assert resp.status_code == 200
        # Le flux est ouvert : l'abonnement a eu lieu.
        assert app.extensions["broker"].subscriber_count == 1
        assert app.extensions["broker"].display_count == 0
    finally:
        resp.close()


def test_les_onglets_admin_n_evincent_jamais_les_ecrans(app, client):
    """Réserve : l'admin est borné bien en dessous du cap total.

    Sans elle, quelques onglets d'administration oubliés consommeraient les créneaux
    destinés aux écrans — et c'est la SALLE qui perdrait l'affichage.
    """
    broker = app.extensions["broker"]
    admin_max = app.config["SSE_ADMIN_MAX"]
    assert admin_max < app.config["SSE_MAX_CLIENTS"], "la réserve doit laisser de la place"

    queues = [broker.subscribe(pubsub.ADMIN) for _ in range(admin_max)]
    try:
        refuse = client.get("/events?role=admin")
        assert refuse.status_code == 503
        assert refuse.headers.get("Retry-After")

        # …et pendant ce temps un écran est toujours accepté : c'est tout l'objet.
        ecran = client.get("/events")
        try:
            assert ecran.status_code == 200
        finally:
            ecran.close()
    finally:
        for q in queues:
            broker.unsubscribe(q)


# ---------- Annonce du nombre d'écrans ----------

def test_brancher_un_ecran_est_annonce_aux_abonnes(broker):
    """Sans cette annonce, la barre d'état restait figée sur le compte du chargement :
    brancher un écran ne se voyait qu'à la publication suivante (leçon 2026-06-22,
    déclinée à un changement DISTANT — il n'y a ici aucune action locale)."""
    admin = broker.subscribe(pubsub.ADMIN)
    _vider(admin)
    ecran = broker.subscribe(pubsub.DISPLAY)
    try:
        assert _prochain(admin, "displays") == {"displays": 1}
    finally:
        broker.unsubscribe(ecran)
        broker.unsubscribe(admin)


def test_debrancher_un_ecran_est_annonce_aussi(broker):
    admin = broker.subscribe(pubsub.ADMIN)
    ecran = broker.subscribe(pubsub.DISPLAY)
    _vider(admin)
    broker.unsubscribe(ecran)
    try:
        assert _prochain(admin, "displays") == {"displays": 0}
    finally:
        broker.unsubscribe(admin)


def test_un_onglet_admin_n_est_jamais_annonce_comme_un_ecran(broker):
    admin = broker.subscribe(pubsub.ADMIN)
    _vider(admin)
    autre = broker.subscribe(pubsub.ADMIN)
    try:
        assert _prochain(admin, "displays") == {"displays": 0}
    finally:
        broker.unsubscribe(autre)
        broker.unsubscribe(admin)


def _vider(q):
    import queue
    while True:
        try:
            q.get_nowait()
        except queue.Empty:
            return


def _prochain(q, event):
    import queue
    while True:
        try:
            nom, data = q.get_nowait()
        except queue.Empty:
            raise AssertionError(f"aucun évènement « {event} » reçu") from None
        if nom == event:
            return data
