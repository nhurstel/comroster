"""⌘Z / ⌘⇧Z : ce que l'annulation couvre, et ce à quoi elle ne doit JAMAIS toucher.

Deux gardes. La PORTÉE : l'historique ne connaît que le brouillon, la configuration du
boîtier (réseau, IP, Wi-Fi, antenne) a ses propres endpoints — le test le vérifie plutôt
que de le supposer. Et la RÉSERVE : dans un champ de saisie, ⌘Z reste l'annulation native
du navigateur, sans quoi corriger une faute de frappe effacerait le dernier groupe créé.

Exclus par défaut (marqueur `e2e`). Lancer :
    .venv/bin/pytest tests/e2e -m e2e
"""
import pytest

# `helpers` s'importe en ABSOLU : tests/e2e n'est pas un package (aucun __init__.py),
# pytest insère donc ce dossier dans sys.path et un import relatif échouerait.
from helpers import enter_admin, open_board_tab, open_reglages, open_screen_tab

pytestmark = pytest.mark.e2e


def test_undo_redo_scoped_to_the_draft(page, live_server):
    """⌘Z annule une modification du BROUILLON, et rien d'autre.

    La portée est garantie par construction : la configuration du boîtier (réseau, IP,
    Wi-Fi, antenne) ne transite pas par `state.data`, elle a ses propres endpoints. Ce
    test le VÉRIFIE plutôt que de le supposer : une IP fixe enregistrée avant l'annulation
    doit être intacte après.
    """
    enter_admin(page, live_server)
    open_reglages(page)
    page.click("#network-btn")
    page.wait_for_selector("#network-dialog[open]")
    page.select_option("#net-mode", "static")
    page.wait_for_selector("#net-static-fields:not([hidden])")
    page.fill("#net-address", "192.168.1.50")
    page.click("#network-form button[type=submit]")
    page.wait_for_selector("#net-result:not([hidden])")
    page.click('#network-dialog button[data-close="network-dialog"]')
    page.wait_for_selector("#network-dialog:not([open])", state="attached")

    for name in ("Plateau", "Lumière"):
        page.click("#add-block-btn")
        page.fill("#block-name", name)
        page.click("#block-form button[type=submit]")
        page.wait_for_selector(f"#blocks-container >> text={name}")

    page.keyboard.press("Control+z")
    page.wait_for_selector("#blocks-container >> text=Lumière", state="detached")
    assert page.locator("#blocks-container .admin-block").count() == 1   # Plateau survit

    page.keyboard.press("Control+Shift+z")
    page.wait_for_selector("#blocks-container >> text=Lumière")

    # La config du boîtier n'a pas bougé d'un iota au passage.
    open_reglages(page)
    page.click("#network-btn")
    page.wait_for_selector("#network-dialog[open]")
    assert page.input_value("#net-address") == "192.168.1.50"
    assert page.input_value("#net-mode") == "static"


def test_undo_ignored_inside_a_text_field(page, live_server):
    """Dans un champ de saisie, ⌘Z reste l'annulation NATIVE du navigateur.

    Sans cette réserve, corriger une faute de frappe dans le titre effacerait le dernier
    groupe créé — une surprise coûteuse en régie.
    """
    enter_admin(page, live_server)
    page.click("#add-block-btn")
    page.fill("#block-name", "Plateau")
    page.click("#block-form button[type=submit]")
    page.wait_for_selector("#blocks-container >> text=Plateau")

    open_screen_tab(page)
    page.click("#meta-title")
    page.keyboard.press("Control+z")
    page.wait_for_timeout(300)
    open_board_tab(page)
    assert page.locator("#blocks-container .admin-block").count() == 1   # le groupe est là
