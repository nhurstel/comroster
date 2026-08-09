"""Géométrie de l'en-tête : ce que l'œil voit, pas ce que les boîtes disent.

Ce fichier existe à cause d'un défaut signalé à l'usage (« tout est trop éloigné du
bouton envoyer, il y a un creux moche »). Une mesure antérieure avait conclu que les
segments de l'en-tête étaient CONTIGUS — c'était vrai, et à côté de la question : les
boîtes se touchaient, mais deux d'entre elles portaient une largeur figée sur leur pire
cas et laissaient leur réserve en vide INTERNE. Entre le mot d'état et le mot
« Publier », l'utilisateur voyait 117 px de trou que la mesure des rectangles ne
montrait pas.

D'où la métrique retenue ici : la distance entre les GLYPHES, jamais entre les
conteneurs — même famille que la leçon du 2026-07-23 (aligner du texte se mesure à la
ligne de base, pas au centre des boîtes).

Le piège est structurel et reviendra : `lockHeaderWidths()` calcule ces largeurs à
partir d'une LISTE de libellés, et il suffit d'y ajouter un texte long pour rouvrir le
creux sans qu'aucune assertion existante ne bronche.
"""
import pytest

pytestmark = pytest.mark.e2e

# Vide toléré entre le mot d'état et le mot « Publier ». L'écart VOULU est de 56 px
# (réglage de Nathan, affiné en deux passes : 25 px trop serré, puis 40 px encore) ; le
# seuil est posé plus haut pour ne pas tomber au moindre décalage de police — une garde
# calée sur la valeur exacte de la cible se déclencherait pour un pixel, ce qui la rendrait
# inutile. Le défaut qu'elle attrape valait 117 px, elle garde sa marge de détection.
CREUX_MAX_PX = 70


def _enter_admin(page, base):
    page.goto(base + "/admin/setup")
    page.fill("input[name=password]", "motdepasse8")
    page.click("button[type=submit]")
    page.click("a.auth-go")
    page.wait_for_selector("#add-block-btn")


def test_le_mot_d_etat_ne_s_eloigne_pas_du_bouton_publier(page, live_server):
    """Aucune réserve de largeur ne doit s'ouvrir entre l'état et l'action.

    Mesure les bords des TEXTES (`#sync-label`, `#pub-label`), pas ceux de leurs
    conteneurs : c'est précisément l'écart entre les deux qui avait masqué le défaut.
    """
    _enter_admin(page, live_server)
    page.wait_for_selector("#sync-label:has-text('À jour')")
    page.wait_for_timeout(700)          # lockHeaderWidths() repasse une fois les polices prêtes

    creux = page.evaluate(
        """() => {
        const etat = document.getElementById('sync-label').getBoundingClientRect();
        const pub = document.getElementById('pub-label').getBoundingClientRect();
        return Math.round(pub.left - etat.right);
    }"""
    )
    assert 0 <= creux <= CREUX_MAX_PX, (
        f"{creux} px entre le mot d'état et « Publier » (toléré : {CREUX_MAX_PX}). "
        "Une largeur figée sur un libellé exceptionnel laisse sa réserve en vide interne — "
        "vérifier les listes passées à fixWidthToLongest()."
    )


def test_le_libelle_arme_ne_fixe_pas_la_largeur_du_bouton(page, live_server):
    """Le bouton se dimensionne sur ses états NOMINAUX, pas sur le décompte.

    Propriété distincte de la précédente et testée séparément : le creux pourrait être
    refermé par un autre moyen tout en payant encore la réserve du libellé armé. On
    compare donc la largeur au repos au contenu réellement affiché.
    """
    _enter_admin(page, live_server)
    page.wait_for_selector("#pub-label:has-text('Publier')")
    page.wait_for_timeout(700)

    mesures = page.evaluate(
        """() => {
        const btn = document.getElementById('publish-btn');
        const lab = document.getElementById('pub-label').getBoundingClientRect();
        const kbd = btn.querySelector('kbd').getBoundingClientRect();
        return {bouton: Math.round(btn.getBoundingClientRect().width),
                contenu: Math.round(kbd.right - lab.left)};
    }"""
    )
    # 16 px de padding de chaque côté + la gouttière libellé/raccourci : au-delà d'une
    # soixantaine de pixels de rab, c'est qu'une réserve dort dans le bouton.
    rab = mesures["bouton"] - mesures["contenu"]
    assert rab <= 60, (
        f"bouton {mesures['bouton']} px pour {mesures['contenu']} px de contenu "
        f"({rab} px de rab) : la largeur est figée sur un libellé qui ne s'affiche pas au repos."
    )
