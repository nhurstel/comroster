"""Parcours bout-en-bout via navigateur (Playwright headless).

Exclus par défaut (marqueur `e2e`). Lancer :
    .venv/bin/pytest tests/e2e -m e2e
"""
import pytest

pytestmark = pytest.mark.e2e


def _enter_admin(page, base):
    """Configuration initiale → connexion automatique → page d'administration."""
    page.goto(base + "/admin/setup")
    page.fill("input[name=password]", "motdepasse8")
    page.click("button[type=submit]")
    page.click("a.auth-submit")                 # « Accéder à l'administration »
    page.wait_for_selector("#add-block-btn")


def test_setup_create_publish_display(page, live_server):
    _enter_admin(page, live_server)

    # Créer un groupe
    page.click("#add-block-btn")
    page.fill("#block-name", "Plateau")
    page.click("#block-form button[type=submit]")
    page.wait_for_selector("#blocks-container >> text=Plateau")

    # Créer un beltpack affecté au groupe
    page.click("#add-user-btn")
    page.fill("#person-beltpack", "42")
    page.fill("#person-role", "Régie")
    page.select_option("#person-assign", label="Plateau")
    page.click("#person-form button[type=submit]")
    page.wait_for_selector(".person .bp:has-text('42')")

    # Publier vers l'affichage
    page.click("#publish-btn")
    page.wait_for_selector("text=Publié vers l'affichage")

    # L'écran TV affiche bien le beltpack publié
    display = page.context.new_page()
    display.goto(live_server + "/display")
    display.wait_for_selector("#display-grid .person")
    grid = display.inner_text("#display-grid")
    assert "42" in grid and "Régie" in grid


def test_fresh_box_shows_onboarding(page, live_server):
    # Box neuve (aucun mot de passe défini) → l'écran TV affiche le guide + QR.
    page.goto(live_server + "/display")
    page.wait_for_selector("#onboarding:not([hidden])")
    assert page.is_visible("#ob-qr-img")
    assert page.inner_text("#ob-url").strip() != ""
    # Le QR est bien servi (image chargée)
    loaded = page.eval_on_selector("#ob-qr-img", "img => img.complete && img.naturalWidth > 0")
    assert loaded is True


def test_available_filter(page, live_server):
    _enter_admin(page, live_server)
    for num, role in [("11", "Regie"), ("22", "Lumiere")]:
        page.click("#add-user-btn")
        page.fill("#person-beltpack", num)
        page.fill("#person-role", role)
        page.click("#person-form button[type=submit]")
        page.wait_for_selector(f"#available-users .person .bp:has-text('{num}')")
    page.fill("#available-filter", "Lumiere")
    page.wait_for_selector("#available-users .person .bp:has-text('22')")
    assert page.locator("#available-users .person").count() == 1


def test_indicator_toggles_persist(page, live_server):
    _enter_admin(page, live_server)
    page.click("#edit-meta-btn")
    page.wait_for_selector("#meta-dialog[open]")
    page.uncheck("#ind-battery")
    page.click("#meta-form button[type=submit]")
    page.wait_for_selector("#sync-label:has-text('enregistré')")   # brouillon sauvegardé
    page.reload()
    page.wait_for_selector("#add-block-btn")
    page.click("#edit-meta-btn")
    page.wait_for_selector("#meta-dialog[open]")
    assert page.is_checked("#ind-battery") is False        # préférence persistée
    assert page.is_checked("#ind-online") is True


def test_network_dialog_sets_static_ip(page, live_server):
    _enter_admin(page, live_server)
    page.click("#network-btn")
    page.wait_for_selector("#network-dialog[open]")
    page.select_option("#net-mode", "static")
    page.wait_for_selector("#net-static-fields:not([hidden])")
    page.fill("#net-address", "192.168.1.50")
    page.click("#network-form button[type=submit]")
    page.wait_for_selector("#net-result:not([hidden])")
    assert "192.168.1.50" in page.inner_text("#net-result")


def test_antenna_dialog_opens_wizard_when_unconfigured(page, live_server):
    _enter_admin(page, live_server)
    page.click("#antenna-btn")
    # Antenne non configurée → l'assistant s'affiche, le tableau de bord reste masqué.
    page.wait_for_selector("#antenna-wizard:not([hidden])")
    assert page.is_hidden("#antenna-dashboard")
    assert page.is_visible("#wiz-ip")


def test_display_requests_screen_wake_lock(page, live_server):
    # Anti-veille : /display doit demander un Screen Wake Lock au chargement.
    # On instrumente l'API AVANT le chargement pour capturer l'appel (le vrai
    # verrou peut être refusé en headless, peu importe : on teste l'intention).
    page.add_init_script(
        """
        window.__wakeLockType = null;
        const fake = { addEventListener() {}, release() { return Promise.resolve(); } };
        const spy = (type) => { window.__wakeLockType = type; return Promise.resolve(fake); };
        if (navigator.wakeLock) { navigator.wakeLock.request = spy; }
        else { Object.defineProperty(navigator, 'wakeLock', { value: { request: spy }, configurable: true }); }
        """
    )
    page.goto(live_server + "/display")
    page.wait_for_timeout(400)
    assert page.evaluate("window.__wakeLockType") == "screen"
