def test_security_headers_present(client):
    r = client.get("/healthz")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "SAMEORIGIN"
    assert r.headers["Referrer-Policy"] == "no-referrer"


def test_api_404_returns_json(client):
    r = client.get("/api/does-not-exist")
    assert r.status_code == 404
    assert r.get_json() == {"error": "not_found"}


def test_non_api_404_is_html(client):
    r = client.get("/pas-une-page")
    assert r.status_code == 404
    assert "application/json" not in r.headers.get("Content-Type", "")


def test_recover_is_rate_limited(client):
    client.post("/admin/setup", data={"password": "motdepasse8"})
    last = None
    for _ in range(8):
        last = client.post("/admin/recover", data={"recovery_code": "AAAA-AAAA-AAAA-AAAA",
                                                   "password": "nouveau123"})
    assert last.status_code == 429        # bloqué après plusieurs tentatives
