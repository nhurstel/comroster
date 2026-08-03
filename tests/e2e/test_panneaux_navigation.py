"""Journal, Santé et Impression sont des PANNEAUX : on ne quitte plus l'administration.

La demande de Nathan tient en une phrase — « que le header reste en place ». Ce fichier
la prend au mot : à chaque bascule, on vérifie que l'en-tête est toujours là, que c'est
LE MÊME document (aucune navigation), et que l'administration reste vivante derrière.
Rien de tout cela ne se prouve en DOM seul (leçon 2026-07-07).
"""
import pytest

# `helpers` s'importe en ABSOLU : tests/e2e n'est pas un package (aucun __init__.py),
# pytest insère donc ce dossier dans sys.path et un import relatif échouerait.
from helpers import open_reglages

pytestmark = pytest.mark.e2e


def _enter_admin(page, base):
    page.goto(base + "/admin/setup")
    page.fill("input[name=password]", "motdepasse8")
    page.click("button[type=submit]")
    page.click("a.auth-submit")
    page.wait_for_selector("#add-block-btn")


def _marquer_le_document(page):
    """Pose un témoin sur le document courant.

    S'il survit à la bascule, c'est qu'aucune navigation n'a eu lieu — la seule preuve
    qui distingue « panneau affiché » de « page rechargée qui lui ressemble ».
    """
    page.evaluate("window.__temoinDocument = 'intact'")


def _document_intact(page):
    return page.evaluate("window.__temoinDocument") == "intact"


@pytest.mark.parametrize("panneau,ancre", [
    ("journal", "#events-list"),
    ("health", "#health-report"),
    ("print", "#print-frame"),
])
def test_le_panneau_souvre_sans_quitter_l_administration(page, live_server, panneau, ancre):
    _enter_admin(page, live_server)
    _marquer_le_document(page)

    if panneau == "print":
        page.click('[data-tab="print"]')          # rangée « Impression » de la latérale
    else:
        open_reglages(page)
        page.click(f'[data-tab="{panneau}"]')     # items « Santé » / « Journal » du menu

    page.wait_for_selector(f'.tab-panel[data-panel="{panneau}"]:not([hidden])')
    page.wait_for_selector(ancre)
    assert _document_intact(page), "la page a été rechargée : ce n'est pas un panneau"
    # L'en-tête et la latérale sont TOUJOURS là — c'est la demande, mot pour mot.
    assert page.is_visible(".admin-top")
    assert page.is_visible("#publish-btn")
    assert page.is_visible(".admin-side")
    # …et l'administration reste vivante derrière : le plateau répond encore.
    page.click('[data-tab="board"]')
    page.wait_for_selector('.tab-panel[data-panel="board"]:not([hidden])')
    assert page.is_visible("#add-block-btn")


def test_l_entree_du_menu_allume_l_onglet_qui_la_porte(page, live_server):
    """Sur Journal, quelque chose dans l'en-tête doit dire où l'on est.

    Sans ce repère, le panneau s'ouvrirait sans qu'aucun onglet ne soit marqué : on
    saurait ce qu'on regarde, jamais comment y revenir ni d'où l'on vient.
    """
    _enter_admin(page, live_server)
    assert page.get_attribute("#settings-btn", "data-active") is None
    open_reglages(page)
    page.click('[data-tab="journal"]')
    page.wait_for_selector('.tab-panel[data-panel="journal"]:not([hidden])')
    assert page.get_attribute("#settings-btn", "data-active") is not None
    # Et l'onglet « Affectations » a rendu la main.
    assert page.get_attribute('[data-tab="board"]', "aria-selected") == "false"

    page.click('[data-tab="board"]')
    page.wait_for_selector('.tab-panel[data-panel="board"]:not([hidden])')
    assert page.get_attribute("#settings-btn", "data-active") is None


def test_le_volet_technique_du_journal_ne_touche_pas_au_plateau(page, live_server):
    """Le journal porte des `.tb-seg .seg-btn`, comme la barre du plateau.

    Liée à portée document, la bascule Blocs/Table les aurait attrapés : cliquer
    « Technique » aurait appelé setViewMode(undefined) et fait disparaître LES DEUX vues
    du plateau, depuis un autre panneau. Vérifié par mutation — rendre le sélecteur
    d'admin.js à nouveau global fait bien tomber ce test.
    """
    _enter_admin(page, live_server)
    page.click("#add-block-btn")
    page.fill("#block-name", "Lumière")
    page.click("#block-form button[type=submit]")
    page.wait_for_selector("#blocks-container >> text=Lumière")

    open_reglages(page)
    page.click('[data-tab="journal"]')
    page.wait_for_selector('.tab-panel[data-panel="journal"]:not([hidden])')
    page.click('[data-jtab="logs"]')
    page.wait_for_selector("#log-list:not([hidden])")

    page.click('[data-tab="board"]')
    page.wait_for_selector('.tab-panel[data-panel="board"]:not([hidden])')
    assert page.is_visible("#blocks-container"), "la vue Blocs du plateau a disparu"
    assert "lumière" in page.inner_text("#blocks-container").lower()


def test_la_feuille_a_imprimer_sait_quelle_est_en_trame(page, live_server):
    """La trame porte la VRAIE feuille — celle que les tests papier verrouillent.

    On y vérifie deux choses : la feuille est bien rendue à l'intérieur, et le lien
    « ← Administration » n'y est pas — dans une trame, il pointerait sur la page qui
    la contient.
    """
    _enter_admin(page, live_server)
    page.click("#add-beltpack-pool")
    page.fill("#person-beltpack", "42")
    page.click("#person-form button[type=submit]")
    page.wait_for_selector(".person .bp:has-text('42')")

    page.click('[data-tab="print"]')
    page.wait_for_selector('.tab-panel[data-panel="print"]:not([hidden])')
    trame = page.frame_locator("#print-frame")
    trame.locator("#print-now").wait_for()
    assert trame.locator(".print-back").count() == 0
    assert trame.locator(".sheet-head h1").count() == 1


def test_la_feuille_est_refaite_a_chaque_passage(page, live_server):
    """Rendue par le serveur, elle serait sinon figée à son premier chargement.

    On imprimerait alors une conduite d'où manque le beltpack ajouté entre-temps :
    l'accident exact contre lequel la feuille papier existe.
    """
    _enter_admin(page, live_server)
    page.click('[data-tab="print"]')
    page.wait_for_selector('.tab-panel[data-panel="print"]:not([hidden])')
    page.frame_locator("#print-frame").locator("#print-now").wait_for()

    page.click('[data-tab="board"]')
    page.wait_for_selector('.tab-panel[data-panel="board"]:not([hidden])')
    page.click("#add-block-btn")
    page.fill("#block-name", "Plateau")
    page.click("#block-form button[type=submit]")
    page.wait_for_selector("#blocks-container >> text=Plateau")
    page.click("#add-beltpack-pool")
    page.fill("#person-beltpack", "77")
    page.select_option("#person-assign", label="Plateau")
    page.click("#person-form button[type=submit]")
    page.wait_for_selector(".person .bp:has-text('77')")
    # La feuille rend l'état PUBLIÉ par défaut : on publie, sinon le beltpack ajouté
    # n'aurait aucune raison d'y apparaître et le test ne prouverait rien.
    page.click("#publish-btn")
    page.wait_for_selector("#pub-label:has-text('Publier')", timeout=15000)

    page.click('[data-tab="print"]')
    page.frame_locator("#print-frame").locator("td.c-bp:has-text('77')").wait_for()


def test_un_panneau_ferme_n_interroge_pas_le_boitier(page, live_server):
    """Le sondage suit le REGARD, pas le chargement de la page.

    Sur leur page dédiée, Journal (5 s) et Santé (4 s) pouvaient battre en continu : cette
    page ne montrait qu'eux. Devenus panneaux du même document, ils battraient pendant
    qu'on travaille sur le plateau — trois requêtes toutes les quelques secondes, sur un
    Raspberry Pi, pour des vues que personne ne regarde.

    On compte les requêtes RÉELLES plutôt que de lire la condition dans le code : c'est
    le trafic qui coûte, et c'est donc lui qu'il faut mesurer.
    """
    sondes = []
    page.on("request", lambda r: sondes.append(r.url)
            if any(p in r.url for p in ("/api/journal", "/api/logs", "/api/health")) else None)

    _enter_admin(page, live_server)
    sondes.clear()
    page.wait_for_timeout(6000)          # > un battement de chacun des deux panneaux
    assert sondes == [], f"panneaux fermés, et pourtant {len(sondes)} requêtes : {sondes[:5]}"

    # Ouvert, le panneau se relève IMMÉDIATEMENT — sans attendre son prochain battement,
    # sinon on lirait pendant 4 s des mesures vieilles du dernier passage.
    open_reglages(page)
    page.click('[data-tab="health"]')
    page.wait_for_selector('.tab-panel[data-panel="health"]:not([hidden])')
    page.wait_for_selector(".verdict")
    assert any("/api/health" in u for u in sondes)
    assert not any("/api/journal" in u for u in sondes), (
        "le panneau Journal sonde alors qu'on regarde Santé"
    )


def test_l_ancienne_adresse_du_journal_ouvre_le_panneau(page, live_server):
    """Les signets et l'aide-mémoire terrain citent encore /admin/journal.

    Elle mène désormais au panneau — et l'URL ne garde pas `?panneau=`, qui mentirait
    dès le clic suivant.
    """
    _enter_admin(page, live_server)
    page.goto(live_server + "/admin/journal")
    page.wait_for_selector('.tab-panel[data-panel="journal"]:not([hidden])')
    assert page.is_visible(".admin-top")
    assert "panneau=" not in page.url
