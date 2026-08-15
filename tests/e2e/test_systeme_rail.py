"""Navigation dans l'onglet « Système » : le rail, et l'onglet qui reste allumé.

Remplace `test_reglages_menu.py`, qui éprouvait le comportement clavier et souris d'un
menu déroulant supprimé le 2026-08-14. Ce menu mélangeait deux panneaux et trois
dialogues sous un nom — « Réglages » — qui ne contenait aucun des deux réglages les plus
manipulés du produit. Le fichier n'est pas mort avec lui : ce qu'il gardait vraiment,
c'est qu'on puisse atteindre les fonctions du boîtier et savoir où l'on est. Ces deux
garanties se testent ici, sur ce qui les porte désormais.

Le gain de la refonte est justement qu'il n'y a plus de comportement d'ouverture à
éprouver : sept rangées, sept panneaux, un seul mécanisme — celui des onglets.
"""
import pytest
from helpers import enter_admin, open_systeme

pytestmark = pytest.mark.e2e

SECTIONS = [
    ("health", ".health-report"),
    ("journal", "#events-list"),
    ("network", "#net-link"),
    ("intercom", "#antenna-wizard, #antenna-dashboard"),
    ("backup", "#bk-pass"),
    ("password", "#pw-current"),
    ("reboot", "#reboot-btn"),
]


@pytest.mark.parametrize("section,ancre", SECTIONS)
def test_chaque_section_du_rail_ouvre_son_panneau(page, live_server, section, ancre):
    """Les sept fonctions du boîtier sont atteignables, et aucune n'ouvre de fenêtre.

    Réseau, intercom, sauvegarde et mot de passe vivaient dans des <dialog> modaux : on
    configurait la machine dans une fenêtre posée par-dessus le plateau. L'assertion sur
    `dialog[open]` est le cœur du test — elle échoue si l'un d'eux revenait à ses
    habitudes.
    """
    enter_admin(page, live_server)
    open_systeme(page, section)
    page.wait_for_selector(ancre, state="visible")
    assert page.locator("dialog[open]").count() == 0, (
        f"la section « {section} » ouvre encore un dialogue par-dessus le plateau"
    )
    # Le rail dit où l'on est, et l'onglet d'en-tête dit à quelle famille on appartient.
    assert page.get_attribute(f'.sys-rail [data-tab="{section}"]', "aria-current") == "page"
    assert page.get_attribute('.tab[data-famille="systeme"]', "data-active") is not None


def test_l_onglet_systeme_reste_allume_sur_les_sept_sections(page, live_server):
    """C'est le défaut réparé : l'indicateur « vous êtes ici » sautait d'une surface à
    l'autre selon la destination — aucun onglet actif sur Impression, et « Réglages »
    souligné sur Santé sans dire où l'on était.

    On parcourt les sept d'affilée plutôt qu'une seule : le défaut ne se voyait qu'à
    partir de la DEUXIÈME, l'onglet étant naturellement allumé sur celle qu'il pointe.
    """
    enter_admin(page, live_server)
    for section, ancre in SECTIONS:
        open_systeme(page, section)
        page.wait_for_selector(ancre, state="visible")
        assert page.get_attribute('.tab[data-famille="systeme"]', "data-active") is not None, (
            f"l'onglet « Système » s'est éteint sur la section « {section} »"
        )
        assert page.get_attribute('[data-tab="board"]', "aria-selected") == "false"


def test_le_voyant_intercom_mene_a_sa_section_sans_ouvrir_de_fenetre(page, live_server):
    """Le voyant portait l'état ET ouvrait un assistant modal. Il garde l'état — c'est sa
    raison d'être — mais il ne fait plus que MENER : un témoin peut être une porte sans
    être un onglet, et sans poser de fenêtre sur le travail en cours.
    """
    enter_admin(page, live_server)
    page.click("#antenna-btn")
    page.wait_for_selector('.tab-panel[data-panel="intercom"]:not([hidden])')
    assert page.locator("dialog[open]").count() == 0
    assert page.is_visible("#antenna-wizard"), "l'assistant de première connexion manque"
    # Le voyant reste un témoin : il n'a pris ni `aria-selected`, ni la place d'un onglet.
    assert page.get_attribute("#antenna-btn", "aria-selected") is None


def test_une_adresse_panneau_ouvre_directement_une_section(page, live_server):
    """`?panneau=` visait déjà Journal et Santé ; les quatre sections neuves en héritent
    sans une ligne de code, puisqu'elles sont de vrais panneaux. C'est la raison d'être
    du choix : réutiliser le mécanisme au lieu d'en écrire un second.
    """
    enter_admin(page, live_server)
    page.goto(f"{live_server}/admin?panneau=backup")
    page.wait_for_selector("#bk-pass", state="visible")
    assert page.get_attribute('.sys-rail [data-tab="backup"]', "aria-current") == "page"
    # L'adresse est nettoyée aussitôt appliquée, sinon elle mentirait au clic suivant.
    assert "panneau=" not in page.url
