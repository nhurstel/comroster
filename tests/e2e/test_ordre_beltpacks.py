"""Ordre des beltpacks dans un groupe : tri automatique, puis manuel dès qu'on y touche.

Règle tranchée par Nathan (2026-08-03) : tri par numéro par défaut ; ranger un membre à la
main fait basculer CE groupe en manuel et gèle l'ordre posé ; « Trier par n° » y ramène,
groupe par groupe.

Ces gestes ne se valident que dans un vrai navigateur : le glisser-déposer HTML5 n'existe
pas dans le DOM seul, et c'est précisément la partie que personne n'avait exercée — aucun
e2e du dépôt ne faisait de drag avant celui-ci.
"""
import pytest

pytestmark = pytest.mark.e2e


def _enter_admin(page, base):
    page.goto(base + "/admin/setup")
    page.fill("input[name=password]", "motdepasse8")
    page.click("button[type=submit]")
    page.click("a.auth-go")
    page.wait_for_selector("#add-block-btn")


def _plateau(page):
    """Un groupe et trois beltpacks SAISIS DANS LE DÉSORDRE (30, 10, 20).

    L'ordre de saisie doit être contraire au tri : sinon le tri automatique serait
    indiscernable de « l'ordre dans lequel je les ai tapés », et le test ne prouverait rien.
    """
    page.click("#add-block-btn")
    page.fill("#block-name", "Son")
    page.click("#block-form button[type=submit]")
    for numero in ("30", "10", "20"):
        page.click(".block-items .drop-tile")
        page.fill("#person-beltpack", numero)
        page.fill("#person-role", f"Rôle {numero}")
        page.click("#person-form button[type=submit]")
        page.wait_for_selector(f".admin-block .person .bp:text-is('{numero}')")


def _numeros(page):
    return page.eval_on_selector_all(
        ".admin-block .person .bp", "els => els.map(e => e.textContent.trim())")


def _premier_est(numero):
    return ("() => [...document.querySelectorAll('.admin-block .person .bp')]"
            f"        .map(e => e.textContent.trim())[0] === '{numero}'")


def _monter_le_dernier_en_tete(page):
    source = page.locator(".admin-block .person").nth(2)
    cible = page.locator(".admin-block .person").nth(0)
    boite = cible.bounding_box()
    # Moitié HAUTE de la première carte : l'insertion se fait avant elle.
    source.drag_to(cible, target_position={"x": boite["width"] / 2, "y": 3})


def test_les_membres_sont_tries_par_numero_sans_intervention(page, live_server):
    _enter_admin(page, live_server)
    _plateau(page)
    assert _numeros(page) == ["10", "20", "30"]


def test_ranger_a_la_main_fige_l_ordre_puis_trier_le_rend(page, live_server):
    _enter_admin(page, live_server)
    _plateau(page)

    _monter_le_dernier_en_tete(page)
    page.wait_for_function(_premier_est("30"))
    assert _numeros(page) == ["30", "10", "20"]

    # Le groupe est passé en manuel : l'action de retri APPARAÎT — elle n'existe que là,
    # ailleurs elle ne ferait rien qu'on puisse constater.
    page.hover(".admin-block .block-header")
    trier = page.locator(".admin-block .block-actions button:has-text('Trier par n°')")
    assert trier.count() == 1

    trier.click()
    page.wait_for_function(_premier_est("10"))
    assert _numeros(page) == ["10", "20", "30"]
    # …et l'action disparaît, le groupe étant redevenu trié.
    page.hover(".admin-block .block-header")
    assert page.locator(
        ".admin-block .block-actions button:has-text('Trier par n°')").count() == 0


def test_l_ecran_de_regie_montre_le_meme_ordre_que_l_administration(page, live_server):
    """La salle et le régisseur doivent lire le MÊME plateau.

    Défaut trouvé en écrivant ce lot : le tri par numéro ne vivait que dans admin.js.
    L'écran, lui, affichait l'ordre brut du fichier — deux vérités pour un seul plateau,
    et celle qui compte devant public était la mauvaise. La règle est passée dans board.js,
    que les deux pages chargent ; ce test est ce qui l'y maintient.
    """
    _enter_admin(page, live_server)
    _plateau(page)
    _monter_le_dernier_en_tete(page)
    page.wait_for_function(_premier_est("30"))
    page.wait_for_selector("#sync-status[data-state='syncing']")
    page.wait_for_selector("#sync-status:not([data-state='syncing'])")
    # Le clic ARME un décompte de 5 s ; ⌘↵ pendant celui-ci envoie tout de suite.
    page.click("#publish-btn")
    page.keyboard.press("Control+Enter")
    page.wait_for_selector("#sync-label:has-text('À jour')")

    ecran = page.context.new_page()
    ecran.goto(live_server + "/display")
    ecran.wait_for_selector("#display-grid .person")
    ordre = ecran.eval_on_selector_all(
        "#display-grid .person .bp-n", "els => els.map(e => e.textContent.trim())")
    assert ordre == ["30", "10", "20"], "l'écran de régie a retrié un groupe rangé à la main"


def test_l_ordre_manuel_survit_a_un_rechargement(page, live_server):
    """Sans persistance, le rangement ne tiendrait pas jusqu'au show — donc ne servirait
    à rien. On attend la FIN du cycle d'enregistrement, jamais la seule mise à jour du
    DOM, qui est toujours en avance sur le disque (leçon 2026-07-31)."""
    _enter_admin(page, live_server)
    _plateau(page)
    _monter_le_dernier_en_tete(page)
    page.wait_for_function(_premier_est("30"))

    page.wait_for_selector("#sync-status[data-state='syncing']")
    page.wait_for_selector("#sync-status:not([data-state='syncing'])")
    page.reload()
    page.wait_for_selector(".admin-block .person")
    assert _numeros(page) == ["30", "10", "20"]
