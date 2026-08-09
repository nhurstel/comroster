"""Parcours bout-en-bout via navigateur (Playwright headless).

Exclus par défaut (marqueur `e2e`). Lancer :
    .venv/bin/pytest tests/e2e -m e2e
"""
import pytest

# `helpers` s'importe en ABSOLU : tests/e2e n'est pas un package (aucun __init__.py),
# pytest insère donc ce dossier dans sys.path et un import relatif échouerait.
from helpers import enter_admin, open_reglages, wait_saved

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


def _open_screen_tab(page):
    """Les réglages écran (apparence, luminosité, colonnes, indicateurs) vivent dans
    l'onglet « Écran » depuis la refonte admin : il faut l'activer avant d'agir sur eux,
    sinon Playwright refuse d'interagir avec des champs masqués."""
    page.click('.admin-tabs .tab[data-tab="screen"]')
    page.wait_for_selector("#skin-select", state="visible")


def _wait_frame(page, name, timeout_ms=6000):
    """Attend l'iframe portant ce `name`. Deux aperçus coexistent (le témoin de la barre
    latérale et le grand), donc on ne peut plus les distinguer par leur URL."""
    for _ in range(timeout_ms // 100):
        frame = next((f for f in page.frames if f.name == name), None)
        if frame and "/admin/preview" in frame.url:
            return frame
        page.wait_for_timeout(100)
    raise AssertionError(f"iframe « {name} » absente ou non chargée")


def _publish_one_group(page, base, name="Plateau", beltpack="42", role="Régie", skin=None):
    """Crée un groupe + un beltpack affecté, puis publie.

    Retourne `(page_display, erreurs_console)`. La collecte console est branchée AVANT
    le chargement : une violation CSP ou une exception JS y apparaît, là où un test de
    contenu DOM ne verrait rien (cf. leçon 2026-07-07).
    """
    enter_admin(page, base)
    if skin:
        _open_screen_tab(page)
        page.select_option("#skin-select", skin)
        wait_saved(page)                                  # brouillon écrit
        # Retour à l'onglet Affectations : le bouton « + Groupe » y vit.
        page.click('.admin-tabs .tab[data-tab="board"]')
        page.wait_for_selector("#add-block-btn", state="visible")
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
    page.click("#add-beltpack-pool")
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
    _open_screen_tab(page)
    page.check("#meta-perf")
    wait_saved(page)
    page.click('.admin-tabs .tab[data-tab="board"]')
    page.wait_for_selector("#add-block-btn", state="visible")

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


def test_preview_tracks_published_and_opens_no_sse(page, live_server):
    """Le témoin reporte l'écran de régie : il suit le PUBLIÉ, pas le brouillon en cours.
    Et il n'ouvre AUCUN flux SSE — monté en permanence dans l'admin, il en consommerait
    un par onglet ouvert (SSE_MAX_CLIENTS + un thread par flux, leçon 2026-07-06)."""
    # Compteur de constructions d'EventSource, posé par frame avant tout chargement.
    page.context.add_init_script(
        """
        window.__es = 0;
        const Orig = window.EventSource;
        if (Orig) {
            const Wrapped = function (...args) { window.__es++; return new Orig(...args); };
            Wrapped.prototype = Orig.prototype;
            window.EventSource = Wrapped;
        }
        """
    )
    enter_admin(page, live_server)
    _open_screen_tab(page)
    page.select_option("#skin-select", "grille")
    page.click('.admin-tabs .tab[data-tab="board"]')     # « + Groupe » vit dans l'onglet Affectations
    page.wait_for_selector("#add-block-btn", state="visible")
    page.click("#add-block-btn")
    page.fill("#block-name", "Régie")
    page.click("#block-form button[type=submit]")
    wait_saved(page)                                     # brouillon écrit, jamais publié

    # Le témoin est chargé sans qu'on ait rien ouvert, et reste VIDE : rien n'est publié.
    mini = _wait_frame(page, "preview-mini")
    mini.wait_for_selector("#display-grid", state="attached")
    assert mini.evaluate("document.body.dataset.preview") == "on"
    assert mini.evaluate("document.querySelectorAll('#display-grid .block').length") == 0
    assert mini.evaluate("document.body.dataset.skin") == "basique"      # ni l'apparence du brouillon

    # Après publication, il rattrape l'écran de régie.
    page.click("#publish-btn")               # arme le décompte
    page.keyboard.press("Control+Enter")     # envoyer maintenant (court-circuite le garde-fou 5 s)
    page.wait_for_selector("#sync-label:has-text('À jour')")
    mini = _wait_frame(page, "preview-mini")
    mini.wait_for_selector("#display-grid .block")
    assert mini.evaluate("document.body.dataset.skin") == "grille"
    assert mini.evaluate("window.__es") == 0, "le témoin a ouvert un flux SSE"

    # Cliquer N'IMPORTE OÙ sur la vignette agrandit. On vise volontairement un coin :
    # cliquer `#preview-btn` passerait par son centre et ne dirait rien de sa couverture
    # réelle — c'est ce qui a laissé passer un bouton réduit à une pilule de 2rem en haut.
    box = page.locator(".preview-tile-frame").bounding_box()
    page.mouse.click(box["x"] + box["width"] - 6, box["y"] + box["height"] - 6)
    page.wait_for_selector("#preview-dialog[open]")
    frame = _wait_frame(page, "preview-full")
    frame.wait_for_selector("#display-grid .block")
    assert frame.evaluate("document.querySelectorAll('#display-grid .block').length") == 1
    assert frame.evaluate("window.__es") == 0, "le grand aperçu a ouvert un flux SSE"
    # Le grand aperçu rend le défilement (le témoin permanent, lui, reste immobile) :
    # sans lui il mentirait sur la seule question qui compte, « est-ce que tout tient ? ».
    assert frame.evaluate("document.body.dataset.previewScroll") == "on"
    assert mini.evaluate("document.body.dataset.previewScroll") is None

    # Un clic dans le vide ferme le grand aperçu. On vise un point hors du rectangle du
    # dialog (coin haut-gauche de la fenêtre), pas un `<button>` : c'est la géométrie du
    # backdrop qu'on teste, et elle ne se déduit d'aucun sélecteur.
    page.mouse.click(4, 4)
    # `state="attached"` : un dialog fermé n'est jamais « visible » (leçon 2026-07-23).
    page.wait_for_selector("#preview-dialog:not([open])", state="attached")

    # Le témoin se replie, et son repli survit au rechargement de l'admin.
    page.click("#preview-dock-toggle")
    assert page.get_attribute("#preview-dock", "data-open") == "0"
    page.reload()
    page.wait_for_selector("#preview-dock[data-open='0']")
    assert not page.is_visible(".preview-tile-frame")


def test_fresh_box_shows_onboarding(page, live_server):
    # Box neuve (aucun mot de passe défini) → l'écran TV affiche le guide + QR.
    page.goto(live_server + "/display")
    page.wait_for_selector("#onboarding:not([hidden])")
    assert page.is_visible("#ob-qr-img")
    assert page.inner_text("#ob-url").strip() != ""
    # Le QR est bien servi (image chargée)
    loaded = page.eval_on_selector("#ob-qr-img", "img => img.complete && img.naturalWidth > 0")
    assert loaded is True


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
    _open_screen_tab(page)
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
        page.click("#add-beltpack-pool")
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

    _open_screen_tab(page)
    page.click("#meta-title")
    page.keyboard.press("Control+z")
    page.wait_for_timeout(300)
    page.click('.admin-tabs .tab[data-tab="board"]')
    assert page.locator("#blocks-container .admin-block").count() == 1   # le groupe est là


def test_display_requests_screen_wake_lock(page, live_server):
    # Anti-veille : /display doit demander un Screen Wake Lock au chargement.
    # On instrumente l'API AVANT le chargement pour capturer l'appel (le vrai
    # verrou peut être refusé en headless, peu importe : on teste l'intention).
    page.add_init_script(
        """
        window.__wakeLockType = null;
        const fake = { addEventListener() {}, release() { return Promise.resolve(); } };
        const spy = (type) => { window.__wakeLockType = type; return Promise.resolve(fake); };
        if (navigator.wakeLock) { navigator.wakeLock.request = spy; }
        else { Object.defineProperty(navigator, 'wakeLock', { value: { request: spy }, configurable: true }); }
        """
    )
    page.goto(live_server + "/display")
    page.wait_for_timeout(400)
    assert page.evaluate("window.__wakeLockType") == "screen"
