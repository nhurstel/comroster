"""Le témoin d'aperçu : il reporte l'écran de régie, et ne coûte aucun flux SSE.

Deux propriétés que rien d'autre ne garde : il suit le PUBLIÉ (pas le brouillon en
cours), et il n'ouvre AUCUN EventSource — monté en permanence dans l'admin, il en
consommerait un par onglet ouvert, sur un pool de threads borné (leçon 2026-07-06).

Exclus par défaut (marqueur `e2e`). Lancer :
    .venv/bin/pytest tests/e2e -m e2e
"""
import pytest

# `helpers` s'importe en ABSOLU : tests/e2e n'est pas un package (aucun __init__.py),
# pytest insère donc ce dossier dans sys.path et un import relatif échouerait.
from helpers import enter_admin, open_board_tab, open_screen_tab, wait_saved

pytestmark = pytest.mark.e2e


def _wait_frame(page, name, timeout_ms=6000):
    """Attend l'iframe portant ce `name`. Deux aperçus coexistent (le témoin de la barre
    latérale et le grand), donc on ne peut plus les distinguer par leur URL."""
    for _ in range(timeout_ms // 100):
        frame = next((f for f in page.frames if f.name == name), None)
        if frame and "/admin/preview" in frame.url:
            return frame
        page.wait_for_timeout(100)
    raise AssertionError(f"iframe « {name} » absente ou non chargée")


def test_preview_tracks_published_and_opens_no_sse(page, live_server):
    """Le témoin reporte l'écran de régie : il suit le PUBLIÉ, pas le brouillon en cours.
    Et il n'ouvre AUCUN flux SSE — monté en permanence dans l'admin, il en consommerait
    un par onglet ouvert (SSE_MAX_CLIENTS + un thread par flux, leçon 2026-07-06)."""
    # Compteur de constructions d'EventSource, posé par frame avant tout chargement.
    page.context.add_init_script(
        """
        window.__es = 0;
        const Orig = window.EventSource;
        if (Orig) {
            const Wrapped = function (...args) { window.__es++; return new Orig(...args); };
            Wrapped.prototype = Orig.prototype;
            window.EventSource = Wrapped;
        }
        """
    )
    enter_admin(page, live_server)
    open_screen_tab(page)
    page.select_option("#skin-select", "grille")
    open_board_tab(page)                                 # « + Groupe » vit dans Affectations
    page.click("#add-block-btn")
    page.fill("#block-name", "Régie")
    page.click("#block-form button[type=submit]")
    wait_saved(page)                                     # brouillon écrit, jamais publié

    # Le témoin est chargé sans qu'on ait rien ouvert, et reste VIDE : rien n'est publié.
    mini = _wait_frame(page, "preview-mini")
    mini.wait_for_selector("#display-grid", state="attached")
    assert mini.evaluate("document.body.dataset.preview") == "on"
    assert mini.evaluate("document.querySelectorAll('#display-grid .block').length") == 0
    assert mini.evaluate("document.body.dataset.skin") == "basique"      # ni l'apparence du brouillon

    # Après publication, il rattrape l'écran de régie.
    page.click("#publish-btn")               # arme le décompte
    page.keyboard.press("Control+Enter")     # envoyer maintenant (court-circuite le garde-fou 5 s)
    page.wait_for_selector("#sync-label:has-text('À jour')")
    mini = _wait_frame(page, "preview-mini")
    mini.wait_for_selector("#display-grid .block")
    assert mini.evaluate("document.body.dataset.skin") == "grille"
    assert mini.evaluate("window.__es") == 0, "le témoin a ouvert un flux SSE"

    # Cliquer N'IMPORTE OÙ sur la vignette agrandit. On vise volontairement un coin :
    # cliquer `#preview-btn` passerait par son centre et ne dirait rien de sa couverture
    # réelle — c'est ce qui a laissé passer un bouton réduit à une pilule de 2rem en haut.
    box = page.locator(".preview-tile-frame").bounding_box()
    page.mouse.click(box["x"] + box["width"] - 6, box["y"] + box["height"] - 6)
    page.wait_for_selector("#preview-dialog[open]")
    frame = _wait_frame(page, "preview-full")
    frame.wait_for_selector("#display-grid .block")
    assert frame.evaluate("document.querySelectorAll('#display-grid .block').length") == 1
    assert frame.evaluate("window.__es") == 0, "le grand aperçu a ouvert un flux SSE"
    # Le grand aperçu rend le défilement (le témoin permanent, lui, reste immobile) :
    # sans lui il mentirait sur la seule question qui compte, « est-ce que tout tient ? ».
    assert frame.evaluate("document.body.dataset.previewScroll") == "on"
    assert mini.evaluate("document.body.dataset.previewScroll") is None

    # Un clic dans le vide ferme le grand aperçu. On vise un point hors du rectangle du
    # dialog (coin haut-gauche de la fenêtre), pas un `<button>` : c'est la géométrie du
    # backdrop qu'on teste, et elle ne se déduit d'aucun sélecteur.
    page.mouse.click(4, 4)
    # `state="attached"` : un dialog fermé n'est jamais « visible » (leçon 2026-07-23).
    page.wait_for_selector("#preview-dialog:not([open])", state="attached")

    # Le témoin se replie, et son repli survit au rechargement de l'admin.
    page.click("#preview-dock-toggle")
    assert page.get_attribute("#preview-dock", "data-open") == "0"
    page.reload()
    page.wait_for_selector("#preview-dock[data-open='0']")
    assert not page.is_visible(".preview-tile-frame")
