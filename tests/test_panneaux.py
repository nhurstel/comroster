"""Gardes structurelles des panneaux de l'administration.

Journal, Santé et Impression étaient trois DOCUMENTS séparés ; ils sont devenus des
panneaux d'`admin.html`. Fusionner des documents crée une famille de défauts que ni
l'œil ni un test de rendu ne rattrapent : un identifiant qui existait dans deux pages
et se retrouve en double, une entrée qui bascule un panneau absent, un script qui
cherche un élément resté dans la page supprimée. Ce fichier garde exactement cela.
"""
import os
import re

import pytest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _lire(*chemin):
    with open(os.path.join(RACINE, *chemin), encoding="utf-8") as f:
        return f.read()


@pytest.fixture(scope="module")
def admin_html():
    return _lire("templates", "admin.html")


def test_chaque_entree_a_son_panneau(admin_html):
    """Une entrée `data-tab` sans panneau `data-panel` serait cliquable et sans effet.

    C'est le défaut silencieux par excellence : rien ne casse, rien ne s'ouvre. La
    réciproque compte tout autant — un panneau qu'aucune entrée n'atteint est du code
    mort qu'on croit livré.
    """
    entrees = set(re.findall(r'data-tab="([a-z]+)"', admin_html))
    panneaux = set(re.findall(r'data-panel="([a-z]+)"', admin_html))
    assert entrees == panneaux, (
        f"entrées sans panneau : {sorted(entrees - panneaux)} · "
        f"panneaux inatteignables : {sorted(panneaux - entrees)}"
    )


def test_les_cinq_sections_sont_des_panneaux(admin_html):
    """Ce que Nathan a demandé : Journal, Santé et Impression ne quittent plus l'admin."""
    panneaux = set(re.findall(r'data-panel="([a-z]+)"', admin_html))
    assert panneaux == {"board", "screen", "journal", "health", "print"}


def test_aucun_identifiant_en_double(admin_html):
    """Deux documents fusionnés, ce sont deux jeux d'identifiants qui se rencontrent.

    `status-info` vivait à la fois dans journal.html et health.html ; réunis tels quels
    dans admin.html, le second aurait été introuvable et son panneau serait resté muet
    sur « serveur injoignable » — précisément le message qu'on veut voir.
    """
    ids = re.findall(r'\bid="([^"]+)"', admin_html)
    doublons = sorted({i for i in ids if ids.count(i) > 1})
    assert doublons == [], f"identifiants présents plusieurs fois : {doublons}"


# La garde « chaque getElementById a sa cible » vivait ici, pour journal.js et health.js
# seulement. Elle vaut pour TOUS les couples script/page : faute de l'avoir généralisée le
# jour où on l'a écrite, `display.js` a écrit trois semaines durant dans deux éléments
# retirés de son template sans que rien ne le signale. Elle est désormais dans
# tests/test_pages_et_scripts.py, qui découvre les scripts de chaque page rendue.


@pytest.mark.parametrize("script", ["journal.js", "health.js"])
def test_les_panneaux_ne_sondent_que_lorsquon_les_regarde(script):
    """Journal (5 s) et Santé (4 s) tournaient parce que leur page ne montrait qu'eux.

    Devenus panneaux, ils battraient en permanence pendant qu'on travaille sur le
    plateau — jusqu'à trois requêtes toutes les quelques secondes, sur un Raspberry Pi,
    pour des vues que personne ne regarde. La condition d'arrêt est le panneau caché.
    """
    js = _lire("static", "js", script)
    assert "!panneau.hidden" in js, f"{script} sonde sans vérifier que son panneau est visible"
    assert 'addEventListener("panneau-affiche"' in js, (
        f"{script} ne se relève pas à l'ouverture du panneau : on lirait des mesures "
        f"vieilles du dernier passage"
    )


def test_la_bascule_du_plateau_ne_vise_que_la_barre_du_plateau():
    """Le panneau Journal porte lui aussi des `.tb-seg .seg-btn` (Événements/Technique).

    À portée document, la bascule Blocs/Table les lierait et un clic sur « Technique »
    appellerait `setViewMode(undefined)` — les deux vues du plateau disparaîtraient
    d'un coup, depuis un autre panneau. Le comportement est gardé en e2e ; ici on
    verrouille la CAUSE, qui est le sélecteur.
    """
    js = _lire("static", "js", "admin.js")
    assert ".board-toolbar .tb-seg .seg-btn" in js
    assert 'querySelectorAll(".tb-seg .seg-btn")' not in js


def test_le_panneau_impression_charge_la_feuille_a_la_demande(auth_client):
    """`data-src` et non `src` : la trame est (re)chargée à chaque affichage.

    La feuille est rendue par le serveur, donc figée à l'instant de son chargement. Un
    `src` posé dans le HTML la figerait à l'ouverture de l'admin, et l'on imprimerait
    une conduite périmée — l'accident exact contre lequel cette feuille existe.

    Lu sur la page RENDUE et non sur le template : c'est l'adresse résolue par `url_for`
    qu'admin.js concatène, et un `{{ … }}` mal nommé ne se verrait pas dans la source.
    """
    html = auth_client.get("/admin").get_data(as_text=True)
    trame = re.search(r"<iframe[^>]*id=\"print-frame\"[^>]*>", html, re.DOTALL)
    assert trame, "la trame d'impression a disparu du panneau"
    assert 'data-src="/admin/print"' in trame.group(0)
    assert 'src="about:blank"' in trame.group(0)


def test_la_feuille_en_trame_perd_son_lien_de_retour(auth_client):
    """Dans la trame, « ← Administration » pointerait sur la page qui la contient.

    Le lien reste en revanche sur /admin/print ouverte directement — adresse encore
    diffusée par l'aide-mémoire terrain, où il est le seul chemin de retour.
    """
    assert "← Administration" in auth_client.get("/admin/print").get_data(as_text=True)
    embarquee = auth_client.get("/admin/print?embed=1").get_data(as_text=True)
    assert "← Administration" not in embarquee
    # La bascule publié/brouillon REPORTE le drapeau : sans ça, changer de source à
    # l'intérieur du panneau y ferait réapparaître le lien de retour.
    assert "draft=1&amp;embed=1" in embarquee or "embed=1&amp;draft=1" in embarquee
