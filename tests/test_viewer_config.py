import http.server
import threading

import pytest

from comroster.services.viewer import ViewerConfig, probe_server


def test_default_is_empty(tmp_path):
    vc = ViewerConfig(str(tmp_path))
    assert vc.load() == {"server_ip": "", "server_port": 8080}
    assert vc.display_url() is None
    assert vc.health_url() is None


def test_save_and_urls(tmp_path):
    vc = ViewerConfig(str(tmp_path))
    vc.save({"server_ip": "192.168.42.10", "server_port": 8080})
    assert vc.load()["server_ip"] == "192.168.42.10"
    assert vc.display_url() == "http://192.168.42.10:8080/display"
    assert vc.health_url() == "http://192.168.42.10:8080/healthz"


def test_save_rejects_bad_ip(tmp_path):
    vc = ViewerConfig(str(tmp_path))
    with pytest.raises(ValueError):
        vc.save({"server_ip": "pas-une-ip", "server_port": 8080})


def test_save_rejects_bad_port(tmp_path):
    vc = ViewerConfig(str(tmp_path))
    with pytest.raises(ValueError):
        vc.save({"server_ip": "192.168.42.10", "server_port": 70000})


def test_corrupt_file_falls_back_to_default(tmp_path):
    vc = ViewerConfig(str(tmp_path))
    with open(vc.path, "w") as fh:
        fh.write("{ pas du json")
    assert vc.load() == {"server_ip": "", "server_port": 8080}


def _serve_once(status):
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(status)
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')
        def log_message(self, *a):
            pass
    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]


def test_probe_reachable():
    srv, port = _serve_once(200)
    try:
        assert probe_server(f"http://127.0.0.1:{port}/healthz") is True
    finally:
        srv.shutdown()


def test_probe_unreachable():
    # port fermé : rien n'écoute
    assert probe_server("http://127.0.0.1:59999/healthz", timeout=0.5) is False


def test_probe_none_url():
    assert probe_server(None) is False
