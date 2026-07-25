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
    # admin.css est AUTONOME (source : design/maquette-admin-7.html) : recharger
    # main.css réintroduirait l'héritage global qui faussait la refonte.
    assert "css/main.css" not in html
    assert "css/admin.css" in html
    assert 'id="publish-btn"' in html      # bouton de publication (libellé « Envoyer à l'affichage »)
    assert "csrf-token" in html


def test_admin_un_bouton_par_fonction(auth_client):
    """Chaque fonction a UN accès : pas de lanceurs en doublon (revue 2026-07-25)."""
    html = auth_client.get("/admin").get_data(as_text=True)
    assert 'href="/admin/journal"' in html          # Journal = page dédiée (lien d'onglet)
    assert "journal-dialog" not in html             # plus de dialogue Journal
    assert "data-launch" not in html                # aucun onglet-lanceur en doublon
    assert 'id="add-beltpack-btn"' not in html      # ajout beltpack = réserve seule
    assert 'id="status-preview"' not in html        # aperçu = témoin « Affichage en cours »
    assert ">Historique<" in html                   # entrée latérale des publications passées


def test_admin_has_antenna_panel(auth_client):
    html = auth_client.get("/admin").get_data(as_text=True)
    assert 'id="antenna-btn"' in html
    assert 'id="antenna-dialog"' in html
    assert "antenna-wizard" in html
    assert "antenna-dashboard" in html
    assert "import-dialog" in html
    assert "settings-dialog" not in html      # ancien dialog retiré


def test_admin_color_palette_replaces_native_picker(auth_client):
    html = auth_client.get("/admin").get_data(as_text=True)
    assert 'id="color-dialog"' in html          # palette bornée
    assert 'id="color-grid"' in html
    assert 'type="color"' not in html            # plus de sélecteur natif illisible


def test_admin_has_configs_and_selection(auth_client):
    html = auth_client.get("/admin").get_data(as_text=True)
    assert "configs-dialog" in html
    assert 'id="configs-btn"' in html
    assert "ranges-list" in html
    assert "selection-bar" in html           # sélection par clic direct (plus de bouton dédié)
    assert 'id="selection-delete"' in html


def test_display_page_renders(client):
    r = client.get("/display")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "js/display.js" in html
    assert "css/main.css" in html
    assert "display-grid" in html


def test_display_template_error_is_not_swallowed(client, monkeypatch):
    # Politique appliance : fail-safe sur les DONNÉES, jamais de masquage des BUGS.
    # Une erreur de template doit remonter (500/exception), pas un faux "OK".
    import pytest
    import comroster.display as display_mod

    def boom(*args, **kwargs):
        raise RuntimeError("template cassé")
    monkeypatch.setattr(display_mod, "render_template", boom)
    with pytest.raises(RuntimeError):
        client.get("/display")


def test_display_has_no_inline_style_block(client):
    # CSP stricte (default-src 'self') : tout <style>/style inline est bloqué par le
    # navigateur → mise en page cassée. Le CSS du display doit être un fichier statique.
    html = client.get("/display").data.decode()
    assert "<style" not in html
    assert "/static/css/display.css?v=" in html


def test_display_reflects_perf_mode(app, client):
    # Le mode perf publié doit produire data-perf="on" sur le body du display,
    # ce qui déclenche la surcharge CSS (flou désactivé).
    from comroster.services import model
    st = model.empty_state()
    st["perf"] = True
    app.extensions["storage"].save_published(st)
    html = client.get("/display").data.decode()
    assert 'data-perf="on"' in html

def test_display_perf_off_by_default(client):
    html = client.get("/display").data.decode()
    assert 'data-perf="off"' in html
