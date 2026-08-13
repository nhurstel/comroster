"""Le sélecteur d'apparence de l'administration, éprouvé au navigateur.

L'attribut seul ne prouve rien : il faut vérifier que la PALETTE s'applique,
c'est-à-dire que le fond calculé change réellement. Et « auto » ne se teste
qu'en simulant la préférence système, ce que seul un vrai navigateur permet.

Exclus par défaut (marqueur `e2e`). Lancer :
    .venv/bin/pytest tests/e2e -m e2e
"""
import pytest

from helpers import enter_admin

pytestmark = pytest.mark.e2e


def _fond(page):
    return page.evaluate("getComputedStyle(document.body).backgroundColor")


def test_les_trois_modes_changent_reellement_la_palette(page, live_server):
    enter_admin(page, live_server)
    page.click('[data-theme-choice="night"]')
    sombre = _fond(page)

    page.click('[data-theme-choice="day"]')
    clair = _fond(page)
    assert clair != sombre, "le mode clair ne change pas le fond réel"
    assert page.get_attribute('[data-theme-choice="day"]', "aria-pressed") == "true"
    assert page.get_attribute('[data-theme-choice="night"]', "aria-pressed") == "false"

    # Le choix survit au rechargement — c'est le cookie, rendu par le serveur.
    page.reload()
    page.wait_for_selector("#add-block-btn")
    assert _fond(page) == clair, "le choix n'a pas survécu au rechargement"
    assert page.evaluate("document.body.dataset.theme") == "day"


def test_le_mode_auto_suit_la_preference_du_systeme(page, live_server):
    """« auto » est du CSS pur : c'est la media query qui tranche, sans JS."""
    enter_admin(page, live_server)
    page.click('[data-theme-choice="auto"]')

    page.emulate_media(color_scheme="dark")
    sombre = _fond(page)
    page.emulate_media(color_scheme="light")
    clair = _fond(page)
    assert clair != sombre, "en mode auto, la préférence système ne change rien"

    # Forcer « Sombre » doit IGNORER un système réglé en clair.
    page.click('[data-theme-choice="night"]')
    assert _fond(page) == sombre, "le mode forcé se laisse dicter par le système"
