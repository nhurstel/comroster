"""Sélectionner plusieurs beltpacks : MAJ+clic, réaffectation en lot, ⌘A et le filtre.

Le décor commun mélange affectés et réserve : c'est ce mélange qui faisait exister une
même personne à DEUX endroits du document (carte masquée + rangée visible) et faisait
« sauter » la sélection.

Exclus par défaut (marqueur `e2e`). Lancer :
    .venv/bin/pytest tests/e2e -m e2e
"""
import pytest

# `helpers` s'importe en ABSOLU : tests/e2e n'est pas un package (aucun __init__.py),
# pytest insère donc ce dossier dans sys.path et un import relatif échouerait.
from helpers import enter_admin, ouvrir_ajout_beltpack

pytestmark = pytest.mark.e2e


def _seed_table(page, live_server):
    """Un groupe « Plateau » (10, 20) et deux beltpacks en réserve (30, 40), vue Tableau.

    Le mélange affecté / non affecté est nécessaire pour reproduire le défaut : c'est
    lui qui faisait exister une même personne à DEUX endroits du document.
    """
    enter_admin(page, live_server)
    page.click("#add-block-btn")
    page.fill("#block-name", "Plateau")
    page.click("#block-form button[type=submit]")
    page.wait_for_selector("#blocks-container >> text=Plateau")
    for num, grp in (("10", "Plateau"), ("20", "Plateau"), ("30", None), ("40", None)):
        ouvrir_ajout_beltpack(page)
        # Le dialogue doit être OUVERT avant qu'on écrive dedans : remplir un champ
        # non encore affiché part en silence et soumet un formulaire incomplet.
        page.wait_for_selector("#person-dialog[open]")
        page.fill("#person-beltpack", num)
        if grp:
            page.select_option("#person-assign", label=grp)
        page.click("#person-form button[type=submit]")
        page.wait_for_selector(f".person .bp:has-text('{num}')")
    page.click('.tb-seg .seg-btn[data-view-mode="table"]')
    page.click('.bt-head .bt-sort:has-text("BP")')      # 2e clic sur BP → ordre décroissant
    rows = page.locator("#blocks-table .bt-row")
    assert [rows.nth(i).locator(".bt-bp").inner_text() for i in range(4)] == ["40", "30", "20", "10"]
    return rows


def test_table_shift_select_follows_visible_order(page, live_server):
    """MAJ+clic dans la vue Tableau balaie ce qui est À L'ÉCRAN, dans l'ordre affiché.

    Régression corrigée : passer en Tableau ne démonte pas la vue Blocs, seulement
    masquée. Le balayage interrogeait tout le document, donc chaque personne DEUX fois
    — carte cachée puis rangée visible — et `indexOf` trouvait d'abord la carte. La
    plage n'avait plus de rapport avec les rangées visées (« ça saute »).
    """
    rows = _seed_table(page, live_server)
    # On clique la cellule BP, jamais le centre de la rangée : il tombe sur le sélecteur
    # de groupe, qui arrête la propagation (cf. leçon du 2026-07-23 sur click au centre).
    rows.nth(0).locator(".bt-bp").click()
    rows.nth(2).locator(".bt-bp").click(modifiers=["Shift"])
    sel = page.locator("#blocks-table .bt-row.selected")
    assert [sel.nth(i).locator(".bt-bp").inner_text() for i in range(sel.count())] == ["40", "30", "20"]


def test_table_bulk_assign_moves_whole_selection(page, live_server):
    """La barre de sélection réaffecte TOUTE la sélection d'un coup.

    Le sélecteur d'une rangée ne pilote que sa rangée : déplacer dix beltpacks
    demandait dix manipulations.
    """
    rows = _seed_table(page, live_server)
    rows.nth(0).locator(".bt-bp").click()
    rows.nth(1).locator(".bt-bp").click()
    page.wait_for_selector("#selection-bar.active")
    page.select_option("#selection-group", label="Plateau")
    # `state="attached"` : sans .active la barre est masquée, or wait_for_selector attend
    # « visible » par défaut — il patienterait pour toujours (leçon 2026-07-23).
    page.wait_for_selector("#selection-bar:not(.active)", state="attached")
    groupes = page.eval_on_selector_all(
        "#blocks-table .bt-assign", "els => els.map((e) => e.selectedOptions[0].textContent)")
    assert groupes == ["Plateau"] * 4                        # 30 et 40 ont rejoint le groupe


def test_select_all_covers_both_views_and_respects_the_filter(page, live_server):
    """⌘A sélectionne tous les beltpacks de la vue active — y compris la réserve.

    Et un filtre en cours restreint la portée : ce qui est estompé n'est pas cliquable,
    le balayer sélectionnerait de l'invisible.
    """
    _seed_table(page, live_server)
    page.keyboard.press("Control+a")
    page.wait_for_selector("#selection-bar.active")
    assert page.locator("#blocks-table .bt-row.selected").count() == 4
    # Échap quitte la sélection (le bouton « Annuler » n'est plus le seul moyen).
    page.keyboard.press("Escape")
    page.wait_for_selector("#selection-bar:not(.active)", state="attached")
    assert page.locator("#blocks-table .bt-row.selected").count() == 0

    # Retour en vue Blocs : les affectés (2) ET la réserve (2) sont concernés.
    page.click('.tb-seg .seg-btn[data-view-mode="blocs"]')
    page.keyboard.press("Control+a")
    page.wait_for_selector("#selection-bar.active")
    assert "4 sélectionné(s)" in page.inner_text("#selection-count")
    page.click("#selection-cancel")

    # Avec un filtre, seuls les beltpacks correspondants sont pris. On quitte le champ
    # de filtre avant : dedans, ⌘A reste le « tout sélectionner » du navigateur.
    page.fill("#board-filter", "10")
    page.wait_for_selector(".person.view-dim")
    page.evaluate("document.activeElement.blur()")
    page.keyboard.press("Control+a")
    assert "1 sélectionné(s)" in page.inner_text("#selection-count")
