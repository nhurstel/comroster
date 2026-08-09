"""Les trois apparences de l'écran de régie : `basique`, `lineaire`, `grille`.

Ce que ces tests gardent : les bornes d'ajustement du texte (non-régression du lot
2026-07-15), l'encre calculée au rendu selon la luminance du groupe, et l'alignement du
numéro sur le rôle — mesuré à la LIGNE DE BASE, jamais au centre des boîtes.

Exclus par défaut (marqueur `e2e`). Lancer :
    .venv/bin/pytest tests/e2e -m e2e
"""
import pytest

# `helpers` s'importe en ABSOLU : tests/e2e n'est pas un package (aucun __init__.py),
# pytest insère donc ce dossier dans sys.path et un import relatif échouerait.
from helpers import enter_admin, open_board_tab, open_screen_tab, wait_saved

pytestmark = pytest.mark.e2e


# Écart des LIGNES DE BASE entre le numéro et le rôle. On ne compare pas les centres de
# boîtes : le chiffre est en line-height 1 et le rôle en 1.15, donc des rectangles centrés
# laissent les glyphes décalés. La sonde est un inline-block de hauteur nulle, dont la
# ligne de base est son bord inférieur — son rect.top donne donc celle du texte qui l'héberge.
_NUMBER_ROLE_OFFSET = """() => {
    const baseline = (el) => {
        const probe = document.createElement('span');
        probe.style.display = 'inline-block';
        probe.style.width = '0'; probe.style.height = '0';
        el.appendChild(probe);
        const y = probe.getBoundingClientRect().top;
        probe.remove();
        return y;
    };
    const p = document.querySelector('#display-grid .person');
    return baseline(p.querySelector('.bp-n')) - baseline(p.querySelector('.role'));
}"""


def _publish_one_group(page, base, name="Plateau", beltpack="42", role="Régie", skin=None):
    """Crée un groupe + un beltpack affecté, puis publie.

    Retourne `(page_display, erreurs_console)`. La collecte console est branchée AVANT
    le chargement : une violation CSP ou une exception JS y apparaît, là où un test de
    contenu DOM ne verrait rien (cf. leçon 2026-07-07).
    """
    enter_admin(page, base)
    if skin:
        open_screen_tab(page)
        page.select_option("#skin-select", skin)
        wait_saved(page)                                  # brouillon écrit
        open_board_tab(page)                              # « + Groupe » vit dans Affectations
    page.click("#add-block-btn")
    page.fill("#block-name", name)
    page.click("#block-form button[type=submit]")
    page.wait_for_selector(f"#blocks-container >> text={name}")
    page.click("#add-beltpack-pool")
    # Le dialogue doit être OUVERT avant qu'on écrive dedans : remplir un champ
    # non encore affiché part en silence et soumet un formulaire incomplet.
    page.wait_for_selector("#person-dialog[open]")
    page.fill("#person-beltpack", beltpack)
    page.fill("#person-role", role)
    page.select_option("#person-assign", label=name)
    page.click("#person-form button[type=submit]")
    page.click("#publish-btn")               # arme le décompte
    page.keyboard.press("Control+Enter")     # envoyer maintenant (court-circuite le garde-fou 5 s)
    page.wait_for_selector("#sync-label:has-text('À jour')")
    display = page.context.new_page()
    errors = []
    display.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
    display.on("pageerror", lambda exc: errors.append(str(exc)))
    display.goto(base + "/display")
    display.wait_for_selector("#display-grid .person")
    return display, errors


def test_base_skin_keeps_historic_fit_bounds(page, live_server):
    """Non-régression du contrat d'ajustement (lot 2026-07-15) après le passage des
    bornes de fitDisplayText en variables CSS : `base` doit rester identique."""
    display, errors = _publish_one_group(page, live_server)
    assert errors == [], f"erreurs console sur /display : {errors}"
    assert display.get_attribute("body", "data-skin") == "basique"
    sizes = display.evaluate(
        """() => {
            const g = document.getElementById('display-grid').style;
            return ['--title-fs', '--role-fs', '--bpn-fs'].map(n => parseFloat(g.getPropertyValue(n)));
        }"""
    )
    title_fs, role_fs, bpn_fs = sizes
    assert 13 <= title_fs <= 24, f"titre hors bornes historiques : {title_fs}"
    assert 12 <= role_fs <= 19, f"rôle hors bornes historiques : {role_fs}"
    assert 16 <= bpn_fs <= 22, f"n° beltpack hors bornes historiques : {bpn_fs}"
    # Le cœur du contrat : titres et rôles tiennent sur UNE ligne, sans troncature.
    overflow = display.evaluate(
        """() => [...document.querySelectorAll('.block-header h3, .person .role')]
                 .filter(e => e.scrollWidth > e.clientWidth + 1).length"""
    )
    assert overflow == 0


def test_block_carries_computed_ink(page, live_server):
    """L'encre lisible sur aplat est calculée au rendu (requise par l'apparence `grille`)."""
    display, errors = _publish_one_group(page, live_server)
    assert errors == [], f"erreurs console sur /display : {errors}"
    # Couleur de groupe par défaut #3AAFA9 → luminance ≈ 0.34 > 0.179 → encre sombre.
    assert display.get_attribute("#display-grid .block", "data-ink") == "dark"


def test_lineaire_skin_from_admin_reaches_display(page, live_server):
    """Parcours complet : sélection dans l'admin → publication → DA appliquée à l'écran."""
    display, errors = _publish_one_group(page, live_server, skin="lineaire")
    assert errors == [], f"erreurs console sur /display : {errors}"
    assert display.get_attribute("body", "data-skin") == "lineaire"
    applied = display.evaluate(
        """() => {
            const block = document.querySelector('#display-grid .block');
            const head = block.querySelector('.block-header');
            return {
                radius: getComputedStyle(block).borderRadius,
                headBg: getComputedStyle(head).backgroundColor,
                veil: getComputedStyle(document.body, '::before').content,
            };
        }"""
    )
    assert applied["radius"] == "0px"                      # angles vifs, plus de carte
    assert applied["headBg"] == "rgb(58, 175, 169)"        # bandeau = couleur du groupe (#3AAFA9)
    assert applied["veil"] == "none"                       # voile d'ambiance de main.css neutralisé
    # Numéro et rôle doivent partager la même ligne de base (le voyant temps réel, s'il
    # revenait dans le flux, décalerait le chiffre de ~5,6 px vers le haut).
    offset = display.evaluate(_NUMBER_ROLE_OFFSET)
    assert abs(offset) <= 1, f"numéro désaligné du rôle de {offset:.1f} px"


def test_grille_skin_fills_block_with_group_colour(page, live_server):
    """`grille` pose du texte SUR la couleur du groupe : le bloc devient la surface,
    et l'encre est choisie au rendu selon la luminance (voir inkFor, display.js)."""
    display, errors = _publish_one_group(page, live_server, skin="grille")
    assert errors == [], f"erreurs console sur /display : {errors}"
    assert display.get_attribute("body", "data-skin") == "grille"
    applied = display.evaluate(
        """() => {
            const block = document.querySelector('#display-grid .block');
            const cs = getComputedStyle(block);
            return { ink: block.dataset.ink, bg: cs.backgroundColor,
                     fg: cs.color, radius: cs.borderRadius };
        }"""
    )
    # #3AAFA9 → luminance ≈ 0.34, au-dessus du seuil 0.179 → encre sombre.
    assert applied["bg"] == "rgb(58, 175, 169)"    # le bloc EST la couleur du groupe
    assert applied["ink"] == "dark"
    assert applied["fg"] == "rgb(11, 13, 18)"
    assert applied["radius"] == "0px"
    offset = display.evaluate(_NUMBER_ROLE_OFFSET)
    assert abs(offset) <= 1, f"numéro désaligné du rôle de {offset:.1f} px"
