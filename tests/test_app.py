def test_healthz(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok"}


def test_prod_requires_secret_key():
    import pytest
    from comroster import create_app
    with pytest.raises(RuntimeError):
        create_app({"TESTING": False, "DEBUG": False, "SECRET_KEY": None})


def test_secure_cookie_on_by_default_in_prod():
    from comroster import create_app
    app = create_app({"TESTING": False, "DEBUG": False, "SECRET_KEY": "x"})
    assert app.config["SESSION_COOKIE_SECURE"] is True


def test_static_urls_are_cache_busted(client):
    # Les assets portent un ?v=… (mtime) pour casser le cache à chaque mise à jour
    html = client.get("/display").data.decode()
    assert "/static/js/display.js?v=" in html
    assert "/static/css/main.css?v=" in html


def test_insecure_cookie_flag_disables_secure():
    # LAN fermé sans TLS : on désactive Secure SANS activer le debug
    from comroster import create_app
    app = create_app({"TESTING": False, "DEBUG": False, "SECRET_KEY": "x", "INSECURE_COOKIE": True})
    assert app.config["SESSION_COOKIE_SECURE"] is False
    assert app.config["DEBUG"] is False        # le debug n'est PAS activé pour autant


def test_request_body_size_is_limited(client):
    # DoS mémoire : un POST énorme doit être refusé (413), pas chargé en RAM
    client.post("/admin/setup", data={"password": "motdepasse8"})
    big = b'{"title": "' + b"x" * (2 * 1024 * 1024) + b'"}'
    resp = client.post("/api/import", data=big, content_type="application/json")
    assert resp.status_code == 413


def test_remote_addr_without_proxy_ignores_forwarded_for(app):
    # Sans COMROSTER_BEHIND_PROXY, un client ne peut pas usurper son IP
    @app.get("/_test/ip")
    def _ip():
        from flask import request
        return request.remote_addr
    resp = app.test_client().get("/_test/ip", headers={"X-Forwarded-For": "1.2.3.4"})
    assert resp.data.decode() != "1.2.3.4"


def test_remote_addr_behind_proxy_uses_forwarded_for():
    # Derrière Nginx (COMROSTER_BEHIND_PROXY) : le rate-limit doit voir l'IP réelle
    from comroster import create_app
    app = create_app({"TESTING": True, "SECRET_KEY": "x", "BEHIND_PROXY": True})

    @app.get("/_test/ip")
    def _ip():
        from flask import request
        return request.remote_addr
    resp = app.test_client().get("/_test/ip", headers={"X-Forwarded-For": "1.2.3.4"})
    assert resp.data.decode() == "1.2.3.4"


def test_csp_header_present(client):
    resp = client.get("/display")
    csp = resp.headers.get("Content-Security-Policy", "")
    assert "default-src 'self'" in csp
