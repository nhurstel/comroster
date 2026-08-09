"""Les réglages et dialogues de l'administration : réserve, indicateurs, réseau, antenne.

Quatre fonctions sans rapport entre elles, qui partagent seulement leur point d'entrée —
l'écran d'administration. Chacune vérifie qu'un réglage prend effet et, quand il est
persistant, qu'il survit au rechargement.

Exclus par défaut (marqueur `e2e`). Lancer :
    .venv/bin/pytest tests/e2e -m e2e
"""
import pytest

# `helpers` s'importe en ABSOLU : tests/e2e n'est pas un package (aucun __init__.py),
# pytest insère donc ce dossier dans sys.path et un import relatif échouerait.
from helpers import enter_admin, open_reglages, open_screen_tab, wait_saved

pytestmark = pytest.mark.e2e


def test_available_filter(page, live_server):
    enter_admin(page, live_server)
    for num, role in [("11", "Regie"), ("22", "Lumiere")]:
        page.click("#add-beltpack-pool")
        # Le dialogue doit être OUVERT avant qu'on écrive dedans : remplir un champ
        # non encore affiché part en silence et soumet un formulaire incomplet.
        page.wait_for_selector("#person-dialog[open]")
        page.fill("#person-beltpack", num)
        page.fill("#person-role", role)
        page.click("#person-form button[type=submit]")
        page.wait_for_selector(f"#available-users .person .bp:has-text('{num}')")
    page.fill("#available-filter", "Lumiere")
    page.wait_for_selector("#available-users .person .bp:has-text('22')")
    assert page.locator("#available-users .person").count() == 1


def test_indicator_toggles_persist(page, live_server):
    enter_admin(page, live_server)
    # Réglages dans l'onglet « Écran » (plus de dialog) : décocher enregistre en direct.
    open_screen_tab(page)
    page.uncheck("#ind-battery")
    wait_saved(page)                                     # brouillon sauvegardé
    page.reload()
    # L'onglet actif est RESTAURÉ au rechargement : on repart donc dans « Écran ».
    # Avant, rafraîchir depuis les réglages ramenait sur « Affectations » — signalé à
    # l'usage, et ce test encodait l'ancien comportement (il attendait #add-block-btn).
    page.wait_for_selector("#skin-select", state="visible")
    assert page.get_attribute('.admin-tabs .tab[data-tab="screen"]', "aria-selected") == "true"
    assert page.is_checked("#ind-battery") is False        # préférence persistée
    assert page.is_checked("#ind-online") is True


def test_network_dialog_sets_static_ip(page, live_server):
    enter_admin(page, live_server)
    open_reglages(page)
    page.click("#network-btn")
    page.wait_for_selector("#network-dialog[open]")
    page.select_option("#net-mode", "static")
    page.wait_for_selector("#net-static-fields:not([hidden])")
    page.fill("#net-address", "192.168.1.50")
    page.click("#network-form button[type=submit]")
    page.wait_for_selector("#net-result:not([hidden])")
    assert "192.168.1.50" in page.inner_text("#net-result")


def test_antenna_dialog_opens_wizard_when_unconfigured(page, live_server):
    enter_admin(page, live_server)
    page.click("#antenna-btn")
    # Antenne non configurée → l'assistant s'affiche, le tableau de bord reste masqué.
    page.wait_for_selector("#antenna-wizard:not([hidden])")
    assert page.is_hidden("#antenna-dashboard")
    assert page.is_visible("#wiz-ip")
