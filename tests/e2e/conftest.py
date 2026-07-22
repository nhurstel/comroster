"""Fixtures pour les tests bout-en-bout (serveur live + navigateur Playwright).

Le serveur tourne dans un thread werkzeug sur un port éphémère, avec un DATA_DIR
temporaire et DEBUG=True (désactive le flag Secure du cookie pour permettre HTTP local).
CSRF et rate-limit restent actifs : on valide donc le vrai parcours navigateur.
"""
import socket
import threading

import pytest
from werkzeug.serving import make_server

from comroster import create_app


def _free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture
def live_server(tmp_path):
    app = create_app({"DATA_DIR": str(tmp_path), "SECRET_KEY": "e2e-secret", "DEBUG": True})
    port = _free_port()
    server = make_server("127.0.0.1", port, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
