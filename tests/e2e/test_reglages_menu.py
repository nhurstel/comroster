"""Comportement clavier et souris du menu « Réglages ».

Ces gestes vivent dans le navigateur : les valider en DOM seul ne prouverait rien
(leçon 2026-07-07). Le menu entre en collision avec trois raccourcis déjà en place
(Échap, ⌘Z, ⌘A) — c'est ce que ce fichier garde.
"""
import pytest

# `helpers` s'importe en ABSOLU : tests/e2e n'est pas un package (aucun __init__.py),
# pytest insère donc ce dossier dans sys.path et un import relatif échouerait.
from helpers import enter_admin, open_reglages

pytestmark = pytest.mark.e2e


def test_menu_souvre_et_se_ferme(page, live_server):
    enter_admin(page, live_server)
    open_reglages(page)
    assert page.get_attribute("#settings-btn", "aria-expanded") == "true"

    # Clic extérieur : sur le titre du fil d'Ariane, hors de .tab-menu.
    page.click("#board-title")
    page.wait_for_selector("#settings-menu", state="hidden")
    assert page.get_attribute("#settings-btn", "aria-expanded") == "false"


def test_echap_ferme_le_menu_et_rend_le_focus(page, live_server):
    enter_admin(page, live_server)
    open_reglages(page)
    page.keyboard.press("Escape")
    page.wait_for_selector("#settings-menu", state="hidden")
    # Sans le retour de focus, la navigation clavier repartirait du début du document.
    assert page.evaluate("document.activeElement.id") == "settings-btn"


def test_echap_annule_la_publication_avant_de_fermer_le_menu(page, live_server):
    """Le décompte de publication PRIME sur la fermeture du menu.

    C'est le seul rang d'Échap qui compte réellement : `publishTimer` ne dépend pas
    d'`onBoard`, donc si la branche du menu passait devant, un Échap frappé pendant
    le décompte fermerait le menu et LAISSERAIT PARTIR la publication — l'inverse de
    ce que l'utilisateur demande. Vérifié par mutation : déplacer la branche du menu
    devant celle du décompte fait bien tomber ce test.
    """
    enter_admin(page, live_server)
    page.click("#publish-btn")                                  # arme le décompte de 5 s
    page.wait_for_selector("#pub-label:has-text('Annuler')")     # « Annuler · N » (décompte)
    open_reglages(page)
    page.keyboard.press("Escape")
    # La publication est annulée…
    page.wait_for_selector("#pub-label:has-text('Publier')")
    # …et le menu, lui, est TOUJOURS ouvert : ce premier Échap ne lui était pas destiné.
    assert page.get_attribute("#settings-btn", "aria-expanded") == "true"


def test_echap_ferme_le_menu_et_la_selection_survit(page, live_server):
    """Un menu ouvert est ce que l'utilisateur VOIT : il part en premier.

    La sélection multiple, elle, doit survivre à ce premier Échap — sinon on perd
    d'un coup un état qu'on avait mis plusieurs clics à construire. Ce que ce test
    garde est le COMPORTEMENT, pas l'ordre des deux branches : la sélection est
    protégée par `onBoard`, qui exclut le menu ouvert.
    """
    enter_admin(page, live_server)
    # ⌘A ne sélectionne QUE ce qui existe : sans beltpack, la barre ne s'active jamais et
    # le test échouerait avant d'atteindre son sujet.
    page.click("#add-beltpack-pool")
    # Le dialogue doit être OUVERT avant qu'on écrive dedans : remplir un champ
    # non encore affiché part en silence et soumet un formulaire incomplet.
    page.wait_for_selector("#person-dialog[open]")
    page.fill("#person-beltpack", "42")
    page.click("#person-form button[type=submit]")
    page.wait_for_selector(".person .bp:has-text('42')")
    # Sortir le focus du formulaire : ⌘A garde son sens NATIF dans un champ de saisie.
    page.click("#board-title")

    page.keyboard.press("Meta+a")               # ⌘A = tout sélectionner (vue active)
    page.wait_for_selector("#selection-bar.active")
    open_reglages(page)
    page.keyboard.press("Escape")
    page.wait_for_selector("#settings-menu", state="hidden")
    # La sélection est INTACTE : la barre est toujours active.
    assert "active" in (page.get_attribute("#selection-bar", "class") or "")
    # Le second Échap, lui, la quitte.
    page.keyboard.press("Escape")
    page.wait_for_selector("#selection-bar:not(.active)", state="attached")


def test_cmd_z_est_neutralise_menu_ouvert(page, live_server):
    """Menu ouvert, ⌘Z ne doit pas annuler la dernière modification du plateau.

    Sans cette garde, on croit corriger une frappe et on efface un groupe — le défaut
    exact relevé le 2026-07-27 pour les champs de saisie, dont le menu est le nouveau cas.
    """
    enter_admin(page, live_server)
    page.click("#add-block-btn")
    page.fill("#block-name", "Lumière")
    page.click("#block-form button[type=submit]")
    page.wait_for_selector("#blocks-container >> text=Lumière")

    open_reglages(page)
    page.keyboard.press("Meta+z")
    page.wait_for_timeout(200)
    # Comparaison insensible à la casse : le CSS affiche les noms de groupe en capitales,
    # donc `inner_text` renvoie « LUMIÈRE » — un `in` sensible à la casse échouerait ici
    # pour une raison qui n'a rien à voir avec ⌘Z.
    assert "lumière" in page.inner_text("#blocks-container").lower(), (
        "⌘Z a mordu alors que le menu était ouvert"
    )

    # Témoin POSITIF : hors du menu, le même ⌘Z annule bien — sans quoi l'assertion
    # ci-dessus passerait même si ⌘Z ne faisait jamais rien (leçon 2026-07-23).
    page.keyboard.press("Escape")
    page.wait_for_selector("#settings-menu", state="hidden")
    page.keyboard.press("Meta+z")
    page.wait_for_selector("#blocks-container >> text=Lumière", state="detached")


def test_les_fleches_parcourent_les_items(page, live_server):
    enter_admin(page, live_server)
    page.click("#settings-btn")
    page.wait_for_selector("#settings-menu:not([hidden])", state="visible")
    page.keyboard.press("ArrowDown")
    assert page.evaluate("document.activeElement.textContent.trim()") == "Santé"
    page.keyboard.press("ArrowDown")
    assert page.evaluate("document.activeElement.textContent.trim()") == "Journal"
    # Le parcours boucle : ↑ depuis le premier item ramène au dernier (Mot de passe —
    # Redémarrer vit au pied de la latérale, pas dans le menu).
    page.keyboard.press("ArrowUp")
    page.keyboard.press("ArrowUp")
    assert page.evaluate("document.activeElement.id") == "password-btn"
