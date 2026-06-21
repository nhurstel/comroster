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


def test_antenna_dialog_opens_wizard_when_unconfigured(page, live_server):
    _enter_admin(page, live_server)
    page.click("#antenna-btn")
    # Antenne non configurée → l'assistant s'affiche, le tableau de bord reste masqué.
    page.wait_for_selector("#antenna-wizard:not([hidden])")
    assert page.is_hidden("#antenna-dashboard")
    assert page.is_visible("#wiz-ip")
