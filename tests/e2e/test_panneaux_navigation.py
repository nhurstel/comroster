"""Journal, Santé et Impression sont des PANNEAUX : on ne quitte plus l'administration.

La demande de Nathan tient en une phrase — « que le header reste en place ». Ce fichier
la prend au mot : à chaque bascule, on vérifie que l'en-tête est toujours là, que c'est
LE MÊME document (aucune navigation), et que l'administration reste vivante derrière.
Rien de tout cela ne se prouve en DOM seul (leçon 2026-07-07).
"""
import pytest

# `helpers` s'importe en ABSOLU : tests/e2e n'est pas un package (aucun __init__.py),
# pytest insère donc ce dossier dans sys.path et un import relatif échouerait.
from helpers import enter_admin, open_systeme, ouvrir_ajout_beltpack

pytestmark = pytest.mark.e2e


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
    enter_admin(page, live_server)
    _marquer_le_document(page)

    if panneau == "print":
        page.click('[data-tab="print"]')          # onglet « Impression » de l'en-tête
    else:
        open_systeme(page)
        page.click(f'.sys-rail [data-tab="{panneau}"]')     # rangée du rail du Système

    page.wait_for_selector(f'.tab-panel[data-panel="{panneau}"]:not([hidden])')
    page.wait_for_selector(ancre)
    assert _document_intact(page), "la page a été rechargée : ce n'est pas un panneau"
    # L'en-tête est TOUJOURS là — c'est la demande, mot pour mot : on ne quitte pas
    # l'administration. La LATÉRALE, elle, appartient au plateau depuis la refonte du
    # 2026-08-14 : son inventaire de groupes n'a rien à faire sur Journal ou Diagnostic,
    # et la masquer rend 204 px au panneau.
    assert page.is_visible(".admin-top")
    assert page.is_visible("#publish-btn")
    assert page.is_hidden(".admin-side"), "la latérale du plateau suit encore les autres panneaux"
    # …et l'administration reste vivante derrière : le plateau répond encore.
    page.click('[data-tab="board"]')
    page.wait_for_selector('.tab-panel[data-panel="board"]:not([hidden])')
    assert page.is_visible("#add-block-btn")
    assert page.is_visible(".admin-side"), "la latérale n'est pas revenue avec le plateau"


def test_l_entree_du_menu_allume_l_onglet_qui_la_porte(page, live_server):
    """Sur Journal, quelque chose dans l'en-tête doit dire où l'on est.

    Sans ce repère, le panneau s'ouvrirait sans qu'aucun onglet ne soit marqué : on
    saurait ce qu'on regarde, jamais comment y revenir ni d'où l'on vient.
    """
    enter_admin(page, live_server)
    assert page.get_attribute('.tab[data-famille="systeme"]', "data-active") is None
    open_systeme(page)
    page.click('.sys-rail [data-tab="journal"]')
    page.wait_for_selector('.tab-panel[data-panel="journal"]:not([hidden])')
    assert page.get_attribute('.tab[data-famille="systeme"]', "data-active") is not None
    # Et l'onglet « Affectations » a rendu la main.
    assert page.get_attribute('[data-tab="board"]', "aria-selected") == "false"

    page.click('[data-tab="board"]')
    page.wait_for_selector('.tab-panel[data-panel="board"]:not([hidden])')
    assert page.get_attribute('.tab[data-famille="systeme"]', "data-active") is None


def test_le_volet_technique_du_journal_ne_touche_pas_au_plateau(page, live_server):
    """Le journal porte des `.tb-seg .seg-btn`, comme la barre du plateau.

    Liée à portée document, la bascule Blocs/Table les aurait attrapés : cliquer
    « Technique » aurait appelé setViewMode(undefined) et fait disparaître LES DEUX vues
    du plateau, depuis un autre panneau. Vérifié par mutation — rendre le sélecteur
    d'admin.js à nouveau global fait bien tomber ce test.
    """
    enter_admin(page, live_server)
    page.click("#add-block-btn")
    page.fill("#block-name", "Lumière")
    page.click("#block-form button[type=submit]")
    page.wait_for_selector("#blocks-container >> text=Lumière")

    open_systeme(page)
    page.click('.sys-rail [data-tab="journal"]')
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
    enter_admin(page, live_server)
    ouvrir_ajout_beltpack(page)
    # Le dialogue doit être OUVERT avant qu'on écrive dedans : remplir un champ
    # non encore affiché part en silence et soumet un formulaire incomplet.
    page.wait_for_selector("#person-dialog[open]")
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
    enter_admin(page, live_server)
    page.click('[data-tab="print"]')
    page.wait_for_selector('.tab-panel[data-panel="print"]:not([hidden])')
    page.frame_locator("#print-frame").locator("#print-now").wait_for()

    page.click('[data-tab="board"]')
    page.wait_for_selector('.tab-panel[data-panel="board"]:not([hidden])')
    page.click("#add-block-btn")
    page.fill("#block-name", "Plateau")
    page.click("#block-form button[type=submit]")
    page.wait_for_selector("#blocks-container >> text=Plateau")
    ouvrir_ajout_beltpack(page)
    # Le dialogue doit être OUVERT avant qu'on écrive dedans : remplir un champ
    # non encore affiché part en silence et soumet un formulaire incomplet.
    page.wait_for_selector("#person-dialog[open]")
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

    enter_admin(page, live_server)
    sondes.clear()
    page.wait_for_timeout(6000)          # > un battement de chacun des deux panneaux
    assert sondes == [], f"panneaux fermés, et pourtant {len(sondes)} requêtes : {sondes[:5]}"

    # Ouvert, le panneau se relève IMMÉDIATEMENT — sans attendre son prochain battement,
    # sinon on lirait pendant 4 s des mesures vieilles du dernier passage.
    open_systeme(page)
    page.click('.sys-rail [data-tab="health"]')
    page.wait_for_selector('.tab-panel[data-panel="health"]:not([hidden])')
    page.wait_for_selector(".verdict")
    assert any("/api/health" in u for u in sondes)
    assert not any("/api/journal" in u for u in sondes), (
        "le panneau Journal sonde alors qu'on regarde Santé"
    )


def test_l_onglet_ecran_replie_le_temoin_sans_effacer_la_preference(page, live_server):
    """Demande de Nathan : arriver sur « Écran » replie « Affichage en cours ».

    Le panneau montre déjà le brouillon en grand ; le témoin, lui, montre ce qui est à
    l'antenne. Deux aperçus côte à côte, dont un minuscule.

    Le point qui compte est la SECONDE assertion : le repli ne doit pas être mémorisé.
    Sans ça, un simple passage par Écran effacerait un réglage posé exprès et le témoin ne
    reviendrait jamais — un panneau n'a pas à décider des préférences des autres.
    """
    enter_admin(page, live_server)
    page.wait_for_selector('#preview-dock[data-open="1"]')

    page.click('[data-tab="screen"]')
    # `state="attached"` et non le `visible` implicite : depuis que la latérale appartient
    # au plateau (refonte 2026-08-14), le témoin n'est plus AFFICHÉ hors des Affectations.
    # Ce que ce test garde n'a jamais été sa visibilité, mais son ÉTAT — et un `visible`
    # implicite sur un conteneur masqué expire sans rien prouver (leçon 2026-07-23).
    page.wait_for_selector('#preview-dock[data-open="0"]', state="attached")
    assert page.evaluate("localStorage.getItem('comroster.preview-dock')") != "0", (
        "le repli contextuel a écrasé la préférence de l'utilisateur"
    )

    page.click('[data-tab="board"]')
    page.wait_for_selector('#preview-dock[data-open="1"]')


def test_l_ancienne_adresse_du_journal_ouvre_le_panneau(page, live_server):
    """Les signets et l'aide-mémoire terrain citent encore /admin/journal.

    Elle mène désormais au panneau — et l'URL ne garde pas `?panneau=`, qui mentirait
    dès le clic suivant.
    """
    enter_admin(page, live_server)
    page.goto(live_server + "/admin/journal")
    page.wait_for_selector('.tab-panel[data-panel="journal"]:not([hidden])')
    assert page.is_visible(".admin-top")
    assert "panneau=" not in page.url


def test_la_marque_ramene_au_plateau_depuis_impression(page, live_server):
    """Le logo ComRoster ramène aux affectations, y compris depuis Impression.

    Défaut né de la RENCONTRE de deux comportements justes : la marque est un lien
    (`href="/admin"`), et l'onglet actif est restauré depuis localStorage au chargement
    (lot « A bis », 2026-07-27). Suivre le lien rechargeait donc la page… qui restaurait
    Impression. Le témoin qui compte est la MÉMOIRE : sans elle, un simple rechargement
    aurait suffi et le test passerait même si le correctif était retiré.
    """
    enter_admin(page, live_server)
    page.click('[data-tab="print"]')
    page.wait_for_selector('.tab-panel[data-panel="print"]:not([hidden])')
    # L'onglet est bien mémorisé : c'est ce qui rendait le retour impossible.
    assert page.evaluate("localStorage.getItem('comroster.admin.tab')") == "print"

    page.click(".brand")
    page.wait_for_selector('.tab-panel[data-panel="board"]:not([hidden])')
    assert page.is_visible(".admin-top"), "l'en-tête doit rester en place"
