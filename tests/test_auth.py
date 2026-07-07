def test_setup_required_first(client):
    resp = client.get("/admin/login")
    assert resp.status_code in (302, 303)
    assert "/admin/setup" in resp.headers["Location"]


def test_setup_creates_admin(client):
    resp = client.post("/admin/setup", data={"password": "motdepasse8"})
    assert resp.status_code in (200, 201, 302)
    resp2 = client.post("/admin/setup", data={"password": "autre1234"})
    assert resp2.status_code in (409, 302)


def test_login_logout_flow(client):
    client.post("/admin/setup", data={"password": "motdepasse8"})
    # le setup connecte déjà ; on se déconnecte pour tester le cycle complet
    client.post("/admin/logout")
    bad = client.post("/admin/login", data={"password": "faux"})
    assert bad.status_code in (401, 200)
    ok = client.post("/admin/login", data={"password": "motdepasse8"})
    assert ok.status_code in (302, 200)
    protected = client.get("/api/state")
    assert protected.status_code == 200
    client.post("/admin/logout")
    after = client.get("/api/state")
    assert after.status_code in (401, 302)


def test_protected_route_without_login(client):
    client.post("/admin/setup", data={"password": "motdepasse8"})
    client.post("/admin/logout")
    resp = client.get("/api/state")
    assert resp.status_code in (401, 302)


def test_setup_short_password_rejected(client):
    # Politique : 4 caractères minimum (décision 2026-07-06)
    resp = client.post("/admin/setup", data={"password": "abc"})
    assert resp.status_code == 400


def test_setup_four_char_password_accepted(client):
    resp = client.post("/admin/setup", data={"password": "abcd"})
    assert resp.status_code in (200, 201, 302)


def test_recover_short_password_rejected(app, client):
    code = app.extensions["secret"].setup("motdepasse8")
    resp = client.post("/admin/recover", data={"recovery_code": code, "password": "abc"})
    assert resp.status_code == 400
    # L'ancien mot de passe reste valide : rien n'a été modifié
    assert app.extensions["secret"].verify_password("motdepasse8")


def test_recover_empty_password_rejected(app, client):
    code = app.extensions["secret"].setup("motdepasse8")
    resp = client.post("/admin/recover", data={"recovery_code": code, "password": ""})
    assert resp.status_code == 400
    assert app.extensions["secret"].verify_password("motdepasse8")


def test_recover_four_char_password_accepted(app, client):
    code = app.extensions["secret"].setup("motdepasse8")
    resp = client.post("/admin/recover", data={"recovery_code": code, "password": "abcd"})
    assert resp.status_code == 200
    assert app.extensions["secret"].verify_password("abcd")


def test_session_cookie_expires(client):
    # La session admin doit expirer (cookie permanent borné, pas un cookie de session infini)
    resp = client.post("/admin/setup", data={"password": "motdepasse8"})
    cookies = "; ".join(resp.headers.getlist("Set-Cookie"))
    assert "session=" in cookies and "Expires=" in cookies
