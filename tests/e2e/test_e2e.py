"""Parcours bout-en-bout via navigateur (Playwright headless).

Exclus par défaut (marqueur `e2e`). Lancer :
    .venv/bin/pytest tests/e2e -m e2e
"""
import pytest

pytestmark = pytest.mark.e2e


def _enter_admin(page, base):
    """Configuration initiale → connexion automatique → page d'administration."""
    page.goto(base + "/admin/setup")
    page.fill("input[name=password]", "motdepasse8")
    page.click("button[type=submit]")
    page.click("a.auth-submit")                 # « Accéder à l'administration »
    page.wait_for_selector("#add-block-btn")


def test_setup_create_publish_display(page, live_server):
    _enter_admin(page, live_server)

    # Créer un groupe
    page.click("#add-block-btn")
    page.fill("#block-name", "Plateau")
    page.click("#block-form button[type=submit]")
    page.wait_for_selector("#blocks-container >> text=Plateau")

    # Créer un beltpack affecté au groupe
    page.click("#available-users .person-add")
    page.fill("#person-beltpack", "42")
    page.fill("#person-role", "Régie")
    page.select_option("#person-assign", label="Plateau")
    page.click("#person-form button[type=submit]")
    page.wait_for_selector(".person .bp:has-text('42')")

    # Envoyer vers l'affichage
    page.click("#publish-btn")
    page.wait_for_selector("text=Envoyé à l'affichage")

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
    _enter_admin(page, base)
    if skin:
        _open_screen_tab(page)
        page.select_option("#skin-select", skin)
        page.wait_for_selector("#sync-label:has-text('enregistré')")   # brouillon écrit
        # Retour à l'onglet Affectations : le bouton « + Groupe » y vit.
        page.click('.admin-tabs .tab[data-tab="board"]')
        page.wait_for_selector("#add-block-btn", state="visible")
    page.click("#add-block-btn")
    page.fill("#block-name", name)
    page.click("#block-form button[type=submit]")
    page.wait_for_selector(f"#blocks-container >> text={name}")
    page.click("#available-users .person-add")
    page.fill("#person-beltpack", beltpack)
    page.fill("#person-role", role)
    page.select_option("#person-assign", label=name)
    page.click("#person-form button[type=submit]")
    page.click("#publish-btn")
    page.wait_for_selector("text=Envoyé à l'affichage")
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
    _enter_admin(page, live_server)
    _open_screen_tab(page)
    page.select_option("#skin-select", "grille")
    page.click('.admin-tabs .tab[data-tab="board"]')     # « + Groupe » vit dans l'onglet Affectations
    page.wait_for_selector("#add-block-btn", state="visible")
    page.click("#add-block-btn")
    page.fill("#block-name", "Régie")
    page.click("#block-form button[type=submit]")
    page.wait_for_selector("#sync-label:has-text('enregistré')")      # brouillon écrit, jamais publié

    # Le témoin est chargé sans qu'on ait rien ouvert, et reste VIDE : rien n'est publié.
    mini = _wait_frame(page, "preview-mini")
    mini.wait_for_selector("#display-grid", state="attached")
    assert mini.evaluate("document.body.dataset.preview") == "on"
    assert mini.evaluate("document.querySelectorAll('#display-grid .block').length") == 0
    assert mini.evaluate("document.body.dataset.skin") == "basique"      # ni l'apparence du brouillon

    # Après publication, il rattrape l'écran de régie.
    page.click("#publish-btn")
    page.wait_for_selector("text=Envoyé à l'affichage")
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
    _enter_admin(page, live_server)
    for num, role in [("11", "Regie"), ("22", "Lumiere")]:
        page.click("#available-users .person-add")
        page.fill("#person-beltpack", num)
        page.fill("#person-role", role)
        page.click("#person-form button[type=submit]")
        page.wait_for_selector(f"#available-users .person .bp:has-text('{num}')")
    page.fill("#available-filter", "Lumiere")
    page.wait_for_selector("#available-users .person .bp:has-text('22')")
    assert page.locator("#available-users .person").count() == 1


def test_indicator_toggles_persist(page, live_server):
    _enter_admin(page, live_server)
    # Réglages dans l'onglet « Écran » (plus de dialog) : décocher enregistre en direct.
    _open_screen_tab(page)
    page.uncheck("#ind-battery")
    page.wait_for_selector("#sync-label:has-text('enregistré')")   # brouillon sauvegardé
    page.reload()
    page.wait_for_selector("#add-block-btn")
    _open_screen_tab(page)
    assert page.is_checked("#ind-battery") is False        # préférence persistée
    assert page.is_checked("#ind-online") is True


def test_network_dialog_sets_static_ip(page, live_server):
    _enter_admin(page, live_server)
    page.click("#network-btn")
    page.wait_for_selector("#network-dialog[open]")
    page.select_option("#net-mode", "static")
    page.wait_for_selector("#net-static-fields:not([hidden])")
    page.fill("#net-address", "192.168.1.50")
    page.click("#network-form button[type=submit]")
    page.wait_for_selector("#net-result:not([hidden])")
    assert "192.168.1.50" in page.inner_text("#net-result")


def test_antenna_dialog_opens_wizard_when_unconfigured(page, live_server):
    _enter_admin(page, live_server)
    page.click("#antenna-btn")
    # Antenne non configurée → l'assistant s'affiche, le tableau de bord reste masqué.
    page.wait_for_selector("#antenna-wizard:not([hidden])")
    assert page.is_hidden("#antenna-dashboard")
    assert page.is_visible("#wiz-ip")


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
