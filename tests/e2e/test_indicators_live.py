"""Vérifie le RENDU des indicateurs batterie/réception avec données antenne live.

Monte un serveur avec une antenne simulée (vraies structures Bolero) connectée et un
beltpack n°13 en ligne, puis ouvre /display dans un navigateur pour vérifier l'affichage.
"""
import socket
import threading

import pytest
from werkzeug.serving import make_server

from comroster import create_app
from comroster.services import model

pytestmark = pytest.mark.e2e


def _real_request(method, path, body=None, timeout=None):
    if path == "/rest/nodeStatus":
        return True, {"nodeStatus": [{"isLocal": True, "bp": [
            {"id": 13, "signalLevel": 0,
             "battery": {"currentCharge": 3120, "maxCharge": 4800, "usbPower": 0}},
        ]}]}
    if path == "/rest/firmware":
        return True, {"firmware": {"version": "3.4.1-15"}}
    if path == "/rest/bp":
        return True, {"bp": [
            {"registered": True, "id": 13, "bpConfig": {"bpNumber": 13, "bpName": "SON 2"}},
        ]}
    return False, {"error": "x"}


@pytest.fixture
def antenna_server(tmp_path):
    app = create_app({"DATA_DIR": str(tmp_path), "SECRET_KEY": "e2e", "DEBUG": True})
    ant = app.extensions["antenna"]
    ant._connected = True
    ant._ip = "1.1.1.1"
    ant._request = _real_request                       # antenne simulée
    app.extensions["secret"].setup("motdepasse8")      # configuré → pas d'écran de bienvenue
    st = model.empty_state()
    g = model.add_group(st, "Son", "#3AAFA9")
    model.add_person(st, "SON 2", "13", g["id"])       # pack 13 affecté
    app.extensions["storage"].save_published(st)

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    srv = make_server("127.0.0.1", port, app, threaded=True)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        srv.shutdown()
        t.join(timeout=5)


def test_display_shows_battery_and_signal(page, antenna_server):
    page.goto(antenna_server + "/display")
    page.wait_for_selector("#display-grid .person")
    page.wait_for_selector(".bp-batt[data-bp='13']:not([hidden])")
    assert "65%" in page.inner_text(".bp-batt[data-bp='13']")
    bars_on = page.eval_on_selector(".bp-sig[data-bp='13']",
                                    "el => el.querySelectorAll('i.on').length")
    assert bars_on == 4
