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


def test_admin_has_antenna_panel(auth_client):
    html = auth_client.get("/admin").get_data(as_text=True)
    assert 'id="antenna-btn"' in html
    assert 'id="antenna-dialog"' in html
    assert "antenna-wizard" in html
    assert "antenna-dashboard" in html
    assert "import-dialog" in html
    assert "settings-dialog" not in html      # ancien dialog retiré


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
