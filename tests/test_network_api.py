import pytest


@pytest.fixture
def auth_client(client):
    client.post("/admin/setup", data={"password": "motdepasse8"})
    return client


def test_network_requires_auth(client):
    assert client.get("/api/network").status_code in (302, 401, 403)


def test_network_default(auth_client):
    assert auth_client.get("/api/network").get_json() == {"mode": "link-local"}


def test_network_set_static(auth_client):
    r = auth_client.put("/api/network", json={"mode": "static", "address": "192.168.1.50", "prefix": 24})
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True and body["reboot_required"] is True
    assert auth_client.get("/api/network").get_json()["address"] == "192.168.1.50"


def test_network_rejects_invalid(auth_client):
    r = auth_client.put("/api/network", json={"mode": "static", "address": "999.0.0.1", "prefix": 24})
    assert r.status_code == 400 and "error" in r.get_json()
