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


def test_une_session_expiree_s_annonce_comme_telle_et_non_en_400(tmp_path):
    """Une session morte doit être DISCERNABLE d'une requête malformée.

    Flask-WTF valide le jeton CSRF AVANT que login_required ne s'exécute : sans
    session, c'est donc un 400 générique qui partait, et jamais le 401
    « unauthorized » que security.py sait pourtant produire. Le client recevait le
    même signal pour « ta session est morte, reconnecte-toi » (définitif) et pour
    « la requête est invalide » (passager) — d'où une interface qui laissait
    l'utilisateur travailler dans le vide.

    Le CSRF est désactivé sous TESTING : on le rallume, sinon ce test passerait
    sans jamais atteindre le défaut qu'il vise.
    """
    from comroster import create_app

    app = create_app({"DATA_DIR": str(tmp_path), "SECRET_KEY": "x", "TESTING": True})
    app.config["WTF_CSRF_ENABLED"] = True
    client = app.test_client()

    reponse = client.put("/api/draft", json={"groups": []},
                         headers={"X-CSRFToken": "jeton-perime"})

    assert reponse.status_code == 401, "une session expirée doit rendre 401, pas 400"
    assert reponse.get_json()["error"] == "session_expired"
