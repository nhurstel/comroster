import pytest


@pytest.fixture
def auth_client(client):
    client.post("/admin/setup", data={"password": "motdepasse8"})
    return client


def test_admin_page_renders(auth_client):
    r = auth_client.get("/admin")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "js/admin.js" in html
    assert "css/main.css" in html
    assert "css/admin.css" in html
    assert "Publier vers l'affichage" in html
    assert "csrf-token" in html


def test_admin_has_settings_and_import_dialogs(auth_client):
    html = auth_client.get("/admin").get_data(as_text=True)
    assert "settings-dialog" in html
    assert "bolero-enabled" in html
    assert "⚙ Réglages" in html
    assert "import-dialog" in html


def test_admin_has_configs_and_selection(auth_client):
    html = auth_client.get("/admin").get_data(as_text=True)
    assert "configs-dialog" in html
    assert 'id="configs-btn"' in html
    assert 'id="select-btn"' in html
    assert "ranges-list" in html
    assert "selection-bar" in html


def test_display_page_renders(client):
    r = client.get("/display")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "js/display.js" in html
    assert "css/main.css" in html
    assert "display-grid" in html
