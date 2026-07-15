from comroster import create_app
from comroster.services import model
from comroster.services.antenna import AntennaError
from comroster.services.live_poller import sync_roster_once


class FakeAntenna:
    """Antenne factice : renvoie un roster fixe, compte les appels réseau."""
    def __init__(self, items, connected=True):
        self._items = items
        self.connected = connected
        self.calls = 0

    def fetch_beltpacks(self):
        self.calls += 1
        return [dict(it) for it in self._items]


def _app(tmp_path):
    return create_app({"TESTING": True, "DATA_DIR": str(tmp_path), "SECRET_KEY": "t"})


def _seed_draft(app, people):
    storage = app.extensions["storage"]
    state = model.empty_state()
    for role, bp in people:
        model.add_person(state, role, bp, None)
    storage.save_draft(state)


def test_disabled_never_touches_the_antenna(tmp_path):
    app = _app(tmp_path)
    fake = FakeAntenna([{"number": "5", "name": "X"}])
    app.extensions["antenna"] = fake
    sync_roster_once(app)                      # auto_sync désactivé par défaut
    assert fake.calls == 0


def test_disconnected_does_nothing(tmp_path):
    app = _app(tmp_path)
    app.extensions["antenna"] = FakeAntenna([{"number": "5", "name": "X"}], connected=False)
    app.extensions["settings"].set("auto_sync", True)
    sync_roster_once(app)
    assert app.extensions["storage"].load_published() is None


def test_publishes_on_roster_change(tmp_path):
    app = _app(tmp_path)
    _seed_draft(app, [("Ancien", "5")])
    app.extensions["antenna"] = FakeAntenna([{"number": "5", "name": "Nouveau"}])
    app.extensions["settings"].set("auto_sync", True)
    q = app.extensions["broker"].subscribe()

    sync_roster_once(app)

    draft = app.extensions["storage"].load_draft()
    assert draft["people"][0]["role"] == "Nouveau"          # brouillon miroité
    published = app.extensions["storage"].load_published()
    assert published["people"][0]["role"] == "Nouveau"      # publié direct sur l'affichage
    event, data = q.get_nowait()
    assert event == "published"


def test_no_publish_when_roster_unchanged(tmp_path):
    app = _app(tmp_path)
    _seed_draft(app, [("Régie", "5")])
    app.extensions["antenna"] = FakeAntenna([{"number": "5", "name": "Régie"}])
    app.extensions["settings"].set("auto_sync", True)
    q = app.extensions["broker"].subscribe()

    sync_roster_once(app)

    assert app.extensions["storage"].load_published() is None   # rien à publier
    assert q.empty()


def test_antenna_error_is_swallowed(tmp_path):
    app = _app(tmp_path)
    _seed_draft(app, [("Régie", "5")])

    class Boom:
        connected = True

        def fetch_beltpacks(self):
            raise AntennaError("injoignable")

    app.extensions["antenna"] = Boom()
    app.extensions["settings"].set("auto_sync", True)
    sync_roster_once(app)                       # ne lève pas
    assert app.extensions["storage"].load_published() is None
