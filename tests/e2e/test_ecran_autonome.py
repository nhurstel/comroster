"""L'écran de régie SEUL, sans passer par l'administration.

Les deux seuls e2e qui n'ouvrent jamais l'admin : ce que /display fait de lui-même, sur
une box neuve (guide + QR) et à chaque chargement (anti-veille).

Exclus par défaut (marqueur `e2e`). Lancer :
    .venv/bin/pytest tests/e2e -m e2e
"""
import pytest

pytestmark = pytest.mark.e2e


def test_fresh_box_shows_onboarding(page, live_server):
    # Box neuve (aucun mot de passe défini) → l'écran TV affiche le guide + QR.
    page.goto(live_server + "/display")
    page.wait_for_selector("#onboarding:not([hidden])")
    assert page.is_visible("#ob-qr-img")
    assert page.inner_text("#ob-url").strip() != ""
    # Le QR est bien servi (image chargée)
    loaded = page.eval_on_selector("#ob-qr-img", "img => img.complete && img.naturalWidth > 0")
    assert loaded is True


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
