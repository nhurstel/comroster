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


# Géométrie des zones de droite du bandeau : leur ordre VISUEL (trié par abscisse, donc
# après application des `order` CSS) et leur écart au centre vertical du bandeau.
_ZONES_DU_BANDEAU = """() => {
    const header = document.querySelector('header');
    const hr = header.getBoundingClientRect();
    return [...document.querySelector('.header-actions').children]
        .filter((el) => el.getBoundingClientRect().width > 0)
        .map((el) => {
            const r = el.getBoundingClientRect();
            return {
                nom: el.className,
                x: r.x,
                ecart: (r.top + r.bottom) / 2 - (hr.top + hr.bottom) / 2,
            };
        })
        .sort((a, b) => a.x - b.x);
}"""


# L'ordre attendu est celui du DOM. Il est écrit en toutes lettres, et non déduit d'une
# apparence de référence : une constante se lit, une comparaison croisée passerait au vert
# le jour où LES TROIS dérivent ensemble.
_ORDRE_DU_BANDEAU = ["board-clock", "status-badge", "brand-mark"]


@pytest.mark.parametrize("skin", ["basique", "lineaire", "grille"])
def test_le_bandeau_est_range_pareil_dans_les_trois_apparences(page, live_server, skin):
    """Ordre des zones de droite, et logo centré — sur chacune des trois apparences.

    `lineaire` sortait des deux : elle donnait un `order` à la pastille et à l'horloge
    mais pas au LOGO, resté à la valeur par défaut 0, qui passait donc devant les deux ;
    et son `align-items: stretch` ne recentre pas un élément de hauteur DÉFINIE, qui se
    pose alors au début de l'axe — le logo restait collé en haut. Deux défauts visibles
    à l'œil, invisibles à toute assertion de contenu.

    On mesure l'ordre VISUEL (trié par abscisse) et non celui du DOM : sans cela le test
    passerait quels que soient les `order`, c'est-à-dire précisément ce qu'il surveille.

    Le test est paramétré plutôt que bouclé sur les trois apparences dans un seul corps :
    chaque cas a besoin d'un boîtier NEUF, `enter_admin` passant par /admin/setup, qui ne
    se rejoue pas une fois le mot de passe défini.
    """
    display, _ = _publish_one_group(page, live_server, skin=skin)
    zones = display.evaluate(_ZONES_DU_BANDEAU)

    # `basique` est la seule à montrer les compteurs (skins.css masque .stats-container
    # ailleurs) : on compare la queue commune aux trois.
    ordre = [z["nom"] for z in zones if "stats-container" not in z["nom"]]
    assert ordre == _ORDRE_DU_BANDEAU, f"{skin} range le bandeau autrement : {ordre}"

    ecart = next(z["ecart"] for z in zones if z["nom"] == "brand-mark")
    # 1,5 px de tolérance : un bandeau de hauteur impaire ne centre exactement aucun de
    # ses enfants — ses voisines ne le sont pas davantage.
    assert abs(ecart) <= 1.5, f"{skin} : logo décentré de {ecart:.1f} px"


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
