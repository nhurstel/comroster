import pytest


@pytest.fixture
def auth_client(client):
    client.post("/admin/setup", data={"password": "motdepasse8"})
    return client


def test_onboarding_unconfigured(client):
    data = client.get("/api/onboarding").get_json()
    assert data["configured"] is False
    assert "/admin" in data["admin_url"]
    assert data["hostname_url"].endswith("/admin")


def test_onboarding_configured_after_setup(auth_client):
    data = auth_client.get("/api/onboarding").get_json()
    assert data["configured"] is True


def test_onboarding_uses_configured_static_ip(auth_client):
    # IP fixe configurée → l'URL admin (et le QR) doivent l'utiliser, pas 127.0.0.1
    auth_client.put("/api/network", json={"mode": "static", "address": "192.168.42.10", "prefix": 24})
    data = auth_client.get("/api/onboarding").get_json()
    assert "192.168.42.10" in data["admin_url"]


def test_onboarding_is_public(client):
    # accessible sans session (l'écran TV est public)
    assert client.get("/api/onboarding").status_code == 200


def test_qr_svg_served(client):
    r = client.get("/display/qr.svg")
    assert r.status_code == 200
    assert r.mimetype == "image/svg+xml"
    assert b"<svg" in r.data
