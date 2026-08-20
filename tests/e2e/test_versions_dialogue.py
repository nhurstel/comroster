"""Le dialogue « Historique et presets » parle la langue du plateau.

Nathan, 2026-08-20 : « ce menu est très loin du design de l'interface principale ».
En le rapprochant, deux défauts se sont révélés qui n'étaient pas des questions de goût —
ce sont eux que ces tests gardent, pas l'apparence.

1. LE SEGMENTÉ NE DISAIT PAS QUEL VOLET ÉTAIT OUVERT. `.tb-seg .seg-btn` ne pose pas de
   fond ; sur cette seule propriété, `.admin-dialog button` l'emportait et peignait les
   trois onglets en `--surface-3` — la teinte réservée à l'onglet ACTIF. Trois onglets
   actifs, donc aucun. Une perte d'information, invisible tant qu'on ne compare pas le
   dialogue à la barre d'outils du plateau, où le même composant fonctionne.

2. LE CADRE SAUTAIT DE 55 %. Mesuré avant : 502 / 400 / 224 px selon le volet. La boîte
   s'effondrait sous le curseur en changeant d'onglet.

Ces tests MESURENT, ils ne regardent pas : une capture ne dit pas si deux teintes sont
égales, et l'œil ne compte pas les pixels.
"""
import pytest
from helpers import ajouter_beltpack, enter_admin

pytestmark = pytest.mark.e2e

VOLETS = ("historique", "presets", "fichier")


def _ouvrir(page, base):
    enter_admin(page, base)
    page.click("#versions-btn")
    page.wait_for_selector("#versions-dialog[open]")


def _fond(page, volet):
    return page.eval_on_selector(
        f'#versions-dialog [data-vers="{volet}"]',
        "el => getComputedStyle(el).backgroundColor",
    )


def _fonds_stables(page):
    """Les trois fonds, une fois la transition FINIE.

    `.admin-dialog button` transite son fond sur 0,12 s. Échantillonner avant la fin
    renvoie une teinte intermédiaire — au premier essai : `rgba(223, 228, 238, 0.004)`,
    un fond en train d'apparaître, que la comparaison a pris pour une couleur distincte.

    Un `wait_for_timeout` généreux ferait passer le test sans rien garantir : c'est
    précisément l'attente-qui-ne-prouve-rien de la leçon du 2026-08-20. On attend donc
    que les valeurs CESSENT DE BOUGER, ce qui est le vrai signal, et qui rend la main dès
    que c'est vrai.
    """
    precedent, stables = None, 0
    for _ in range(40):                       # 40 × 25 ms = 1 s de patience maximale
        actuel = tuple(_fond(page, v) for v in VOLETS)
        stables = stables + 1 if actuel == precedent else 0
        if stables >= 2:                      # deux relevés identiques d'affilée
            return dict(zip(VOLETS, actuel, strict=True))
        precedent = actuel
        page.wait_for_timeout(25)
    raise AssertionError(f"les fonds du segmenté n'ont jamais cessé de changer : {precedent}")


def test_le_segmente_distingue_le_volet_ouvert(page, live_server):
    """L'onglet actif doit avoir un fond que les deux autres n'ont pas.

    On compare les trois fonds ENTRE EUX plutôt que d'attendre une couleur nommée : la
    valeur exacte appartient au thème, la DIFFÉRENCE appartient au produit. Une garde qui
    coderait `--surface-3` en dur tomberait au prochain réglage de palette sans qu'aucune
    information n'ait été perdue.
    """
    _ouvrir(page, live_server)
    for actif in VOLETS:
        page.click(f'#versions-dialog [data-vers="{actif}"]')
        fonds = _fonds_stables(page)
        autres = {v: f for v, f in fonds.items() if v != actif}
        assert len(set(autres.values())) == 1, (
            f"les onglets inactifs ne se ressemblent pas : {autres}"
        )
        assert fonds[actif] not in autres.values(), (
            f"« {actif} » est ouvert mais son fond ({fonds[actif]}) est celui des "
            "inactifs : le segmenté ne dit pas quel volet on regarde"
        )


def test_le_cadre_ne_saute_plus_en_changeant_de_volet(page, live_server):
    """Trois volets, trois hauteurs — leur écart doit rester petit.

    Le seuil est à 60 px : assez large pour que les notices des trois volets diffèrent
    d'une ligne, assez serré pour que l'effondrement d'avant (278 px d'écart) ne repasse
    jamais. Un seuil qui tolère le défaut qu'il vise ne sert à rien.

    LE DÉCOR EST LE TEST. Écrite d'abord sur un boîtier neuf, cette garde était CREUSE :
    listes vides, trois volets naturellement courts, et retirer `min-height` ne la faisait
    pas tomber. Elle passait sans rien démontrer. Il faut du contenu pour que l'écart
    existe — c'est peuplé qu'un dialogue saute, jamais à vide.
    """
    enter_admin(page, live_server)
    ajouter_beltpack(page, "11", "Regie")
    for _ in range(3):                       # trois repères : le volet Historique s'allonge
        page.click("#publish-btn")
        page.wait_for_timeout(1100)          # l'horodatage est la clé : une seconde d'écart
    page.click("#versions-btn")
    page.wait_for_selector("#versions-dialog[open]")
    page.click('#versions-dialog [data-vers="presets"]')
    for nom in ("Jour 2", "Générale", "Première"):
        page.fill("#config-name", nom)
        page.click("#config-save-btn")
        page.wait_for_selector(f"#configs-list [data-load='{nom}']")

    hauteurs = {}
    for volet in VOLETS:
        page.click(f'#versions-dialog [data-vers="{volet}"]')
        page.wait_for_timeout(200)
        hauteurs[volet] = page.locator("#versions-dialog").bounding_box()["height"]

    ecart = max(hauteurs.values()) - min(hauteurs.values())
    releve = {v: round(h) for v, h in hauteurs.items()}
    assert ecart <= 60, (
        f"le dialogue change de hauteur de {round(ecart)} px selon le volet "
        f"({releve}) : la boîte saute sous le curseur"
    )


def test_un_preset_montre_sa_date_d_enregistrement(page, live_server):
    """`updated_at` était renvoyé par l'API et JETÉ par l'interface.

    Défaut d'information, pas de mise en page : `Configs.list()` compose
    `{name, updated_at}` depuis toujours, et `refreshConfigs` n'affichait que le nom. Une
    rangée réduite à un mot ne fait pas objet — c'est ce que Nathan a vu (« on ne
    distingue pas bien »), et c'est pourquoi ajouter une bordure n'aurait pas suffi.

    La garde porte sur la PRÉSENCE d'une date propre à la rangée, jamais sur son
    formatage : `toLocaleString` dépend de la locale du navigateur, et figer « 20 août »
    ici ferait tomber le test sur une machine en anglais sans qu'aucune information soit
    perdue.
    """
    _ouvrir(page, live_server)
    page.click('#versions-dialog [data-vers="presets"]')
    page.fill("#config-name", "Jour 2")
    page.click("#config-save-btn")
    page.wait_for_selector("#configs-list [data-load='Jour 2']")

    assert page.inner_text("#configs-list .cfg-name").strip() == "Jour 2"
    quand = page.inner_text("#configs-list .cfg-when").strip()
    assert quand, "la rangée n'affiche aucune date : `updated_at` est de nouveau ignoré"
    assert any(c.isdigit() for c in quand), (
        f"« {quand} » ne contient aucun chiffre : ce n'est pas une date"
    )


def test_les_actions_d_une_rangee_restent_atteignables(page, live_server):
    """Masquées au repos, révélées au survol ET au focus.

    Le second point n'est pas décoratif : `.vers-actions` à `opacity: 0` sans règle
    `:focus-within` rendrait la liste inutilisable au clavier — défaut déjà payé une fois
    sur la carte beltpack. On vérifie donc le chemin CLAVIER, celui qu'aucune capture ne
    montre et que le survol masque.
    """
    _ouvrir(page, live_server)
    page.click('#versions-dialog [data-vers="presets"]')
    page.fill("#config-name", "Jour 2")
    page.click("#config-save-btn")
    page.wait_for_selector("#configs-list [data-load='Jour 2']")

    opacite = page.eval_on_selector(
        "#configs-list .vers-actions", "el => getComputedStyle(el).opacity")
    assert opacite == "0", f"les actions sont visibles au repos (opacité {opacite})"

    page.focus("#configs-list [data-load='Jour 2']")
    page.wait_for_timeout(250)
    opacite = page.eval_on_selector(
        "#configs-list .vers-actions", "el => getComputedStyle(el).opacity")
    assert opacite == "1", (
        f"les actions restent masquées au focus clavier (opacité {opacite}) : "
        "la liste est inutilisable sans souris"
    )
