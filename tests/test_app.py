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
