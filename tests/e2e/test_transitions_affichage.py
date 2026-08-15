"""La transition d'arrivée de l'écran de régie : quand elle joue, et quand elle NE doit pas.

Trois cas : une vraie publication l'anime, le mode performance la supprime, et un
`snapshot` (réémis à chaque reconnexion) ne l'anime jamais — sans quoi l'écran rejouerait
la transition toutes les 4 s quand le réseau tousse, en plein show.

Exclus par défaut (marqueur `e2e`). Lancer :
    .venv/bin/pytest tests/e2e -m e2e
"""
import pytest

# `helpers` s'importe en ABSOLU : tests/e2e n'est pas un package (aucun __init__.py),
# pytest insère donc ce dossier dans sys.path et un import relatif échouerait.
from helpers import (
    enter_admin,
    open_board_tab,
    open_screen_tab,
    ouvrir_ajout_beltpack,
    wait_saved,
)

pytestmark = pytest.mark.e2e


# Enregistreur de la transition d'arrivée. Installé AVANT tout script de la page
# (add_init_script) : une transition déclenchée par le tout premier évènement du flux
# serait sinon manquée, et le test passerait pour de mauvaises raisons. On observe le
# document entier parce que #display-grid n'existe pas encore à cet instant.
_ANIM_RECORDER = """
window.__anim = [];
window.__sse = [];

// Journal des évènements SSE REÇUS. Il sert de signal d'attente fiable (« le flux est
// établi et le premier message est arrivé ») et permet d'attribuer chaque transition à
// l'évènement qui l'a déclenchée — c'est toute la question ici, `snapshot` étant réémis
// à chaque reconnexion. Posé AVANT tout le reste : display.js ne doit jamais voir
// l'EventSource d'origine.
const OrigES = window.EventSource;
window.EventSource = function (url) {
  const es = new OrigES(url);
  const add = es.addEventListener.bind(es);
  es.addEventListener = (type, fn) => add(type, (e) => { window.__sse.push(type); fn(e); });
  return es;
};

// On observe `document` et non `document.documentElement` : à l'instant où ce script
// s'exécute, l'élément racine peut ne pas exister encore — l'observer levait alors une
// exception qui emportait silencieusement tout le reste de l'instrumentation.
new MutationObserver(() => {
  const g = document.getElementById('display-grid');
  if (g) window.__anim.push(g.dataset.anim ?? null);
}).observe(document, { attributes: true, subtree: true, attributeFilter: ['data-anim'] });
"""


def _open_display_recording(context, base):
    """Ouvre /display avec l'enregistreur armé et attend le premier message du flux."""
    display = context.new_page()
    display.add_init_script(_ANIM_RECORDER)
    display.goto(base + "/display")
    display.wait_for_function("() => window.__sse.includes('snapshot')")
    return display


def _add_group_and_publish(page, name="Plateau", beltpack="42", role="Régie"):
    page.click("#add-block-btn")
    page.fill("#block-name", name)
    page.click("#block-form button[type=submit]")
    page.wait_for_selector(f"#blocks-container >> text={name}")
    ouvrir_ajout_beltpack(page)
    # Le dialogue doit être OUVERT avant qu'on écrive dedans : remplir un champ
    # non encore affiché part en silence et soumet un formulaire incomplet.
    page.wait_for_selector("#person-dialog[open]")
    page.fill("#person-beltpack", beltpack)
    page.fill("#person-role", role)
    page.select_option("#person-assign", label=name)
    page.click("#person-form button[type=submit]")
    page.click("#publish-btn")
    page.keyboard.press("Control+Enter")
    page.wait_for_selector("#sync-label:has-text('À jour')")


def test_publication_joue_la_transition_darrivee(page, live_server):
    """L'écran doit passer par le cycle sortie → arrivée → repos, pas remplacer d'un coup.

    L'écran est ouvert AVANT la publication : c'est la seule façon de recevoir un vrai
    `published`. Les autres e2e l'ouvrent après et ne reçoivent qu'un `snapshot`.
    """
    enter_admin(page, live_server)
    display = _open_display_recording(page.context, live_server)

    _add_group_and_publish(page)

    display.wait_for_function("() => window.__anim.length >= 3")
    # `attached` et non `visible` : pendant la sortie la grille est à opacité nulle
    # (leçon 2026-07-23, re-commise le 2026-07-27).
    display.wait_for_selector("#display-grid .person", state="attached")
    assert display.evaluate("() => window.__anim") == ["out", "in", None]
    # Le rang est bien posé : c'est lui qui décale la cascade.
    assert display.evaluate(
        "() => document.querySelector('#display-grid .block').style.getPropertyValue('--anim-i')"
    ) == "0"


def test_mode_performance_supprime_la_transition(page, live_server):
    """Mode performance : aucun état d'animation, donc aucun délai avant le tableau."""
    enter_admin(page, live_server)
    open_screen_tab(page)
    page.check("#meta-perf")
    wait_saved(page)
    open_board_tab(page)

    display = _open_display_recording(page.context, live_server)
    _add_group_and_publish(page)

    display.wait_for_selector("#display-grid .person", state="attached")
    assert display.get_attribute("body", "data-perf") == "on"
    assert display.evaluate("() => window.__anim") == []


def test_snapshot_nanime_pas(page, live_server):
    """Le `snapshot` est réémis à CHAQUE ouverture de flux, donc à chaque reconnexion.

    L'animer rejouerait la transition toutes les 4 s quand le réseau tousse, en plein
    show, sans rien de nouveau à montrer.
    """
    enter_admin(page, live_server)
    _add_group_and_publish(page)

    display = _open_display_recording(page.context, live_server)
    display.wait_for_selector("#display-grid .person", state="attached")
    assert display.evaluate("() => window.__sse") == ["snapshot"]
    assert display.evaluate("() => window.__anim") == []
