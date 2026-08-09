"""Le parcours nominal, de bout en bout : setup → groupe → beltpack → publication → écran.

C'est le seul test qui traverse TOUTE la chaîne d'un coup. Les autres fichiers e2e
isolent un sujet ; celui-ci répond à « est-ce que le produit fonctionne, tout court ».

Exclus par défaut (marqueur `e2e`). Lancer :
    .venv/bin/pytest tests/e2e -m e2e
"""
import pytest

# `helpers` s'importe en ABSOLU : tests/e2e n'est pas un package (aucun __init__.py),
# pytest insère donc ce dossier dans sys.path et un import relatif échouerait.
from helpers import enter_admin

pytestmark = pytest.mark.e2e


def test_setup_create_publish_display(page, live_server):
    enter_admin(page, live_server)

    # Créer un groupe
    page.click("#add-block-btn")
    page.fill("#block-name", "Plateau")
    page.click("#block-form button[type=submit]")
    page.wait_for_selector("#blocks-container >> text=Plateau")

    # Créer un beltpack affecté au groupe
    page.click("#add-beltpack-pool")
    # Le dialogue doit être OUVERT avant qu'on écrive dedans : remplir un champ
    # non encore affiché part en silence et soumet un formulaire incomplet.
    page.wait_for_selector("#person-dialog[open]")
    page.fill("#person-beltpack", "42")
    page.fill("#person-role", "Régie")
    page.select_option("#person-assign", label="Plateau")
    page.click("#person-form button[type=submit]")
    page.wait_for_selector(".person .bp:has-text('42')")

    # Envoyer vers l'affichage. Le clic ARME le décompte de 5 s ; ⌘↵ pendant le décompte
    # envoie tout de suite (« envoyer maintenant ») — évite d'attendre 5 s dans le test.
    page.click("#publish-btn")
    page.keyboard.press("Control+Enter")
    page.wait_for_selector("#sync-label:has-text('À jour')")

    # L'écran TV affiche bien le beltpack publié
    display = page.context.new_page()
    display.goto(live_server + "/display")
    display.wait_for_selector("#display-grid .person")
    grid = display.inner_text("#display-grid")
    # La DA met les rôles en capitales (text-transform) → comparaison insensible à la casse.
    assert "42" in grid and "régie" in grid.lower()
