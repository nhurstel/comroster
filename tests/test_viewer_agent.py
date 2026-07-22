import json
import threading
import urllib.request
import urllib.error
import urllib.parse
import pytest
from comroster.viewer_agent import build_server


@pytest.fixture
def agent(tmp_path):
    srv = build_server(str(tmp_path), port=0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]
    yield f"http://127.0.0.1:{port}", tmp_path
    srv.shutdown()
    srv.server_close()      # ferme le socket d'écoute (shutdown seul le laisse ouvert)


def _get(base, path):
    with urllib.request.urlopen(base + path) as r:
        return r.status, r.read().decode()


def _post(base, path, fields):
    data = urllib.parse.urlencode(fields).encode()
    req = urllib.request.Request(base + path, data=data, method="POST")
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def test_server_status_unreachable_by_default(agent):
    base, _ = agent
    status, body = _get(base, "/api/server-status")
    assert status == 200
    payload = json.loads(body)
    assert payload["reachable"] is False
    assert payload["display_url"] is None


def test_post_config_writes_viewer_and_network(agent):
    base, tmp = agent
    status, body = _post(base, "/config", {
        "server_ip": "192.168.42.10",
        "network_mode": "static",
        "network_address": "192.168.42.50",
        "network_prefix": "24",
    })
    assert status == 200
    assert json.loads(body)["ok"] is True
    with open(tmp / "viewer.json") as fh:
        viewer = json.load(fh)
    assert viewer["server_ip"] == "192.168.42.10"
    with open(tmp / "network.json") as fh:
        net = json.load(fh)
    assert net["mode"] == "static" and net["address"] == "192.168.42.50"


def test_post_config_rejects_bad_server_ip(agent):
    base, _ = agent
    status, body = _post(base, "/config", {"server_ip": "nope", "network_mode": "dhcp"})
    assert status == 400
    assert "error" in json.loads(body)


def test_post_config_dhcp_no_address(agent):
    base, tmp = agent
    status, _ = _post(base, "/config", {"server_ip": "192.168.42.10", "network_mode": "dhcp"})
    assert status == 200
    with open(tmp / "network.json") as fh:
        assert json.load(fh)["mode"] == "dhcp"


def test_boot_page_served(agent):
    base, _ = agent
    status, body = _get(base, "/")
    assert status == 200
    assert "server-status" in body        # le JS interroge l'agent
    assert "Configurer" in body           # bannière de config


def test_config_page_has_fields(agent):
    base, _ = agent
    status, body = _get(base, "/config")
    assert status == 200
    assert 'name="server_ip"' in body
    assert 'name="network_mode"' in body


def test_qr_is_svg(agent):
    base, _ = agent
    status, body = _get(base, "/qr.svg")
    assert status == 200
    assert "<svg" in body


def test_main_callable_exists():
    from comroster import viewer_agent
    assert callable(viewer_agent.main)
