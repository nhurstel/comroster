"""Le cahier des charges dit-il encore la vérité ?

Ce document a passé DEUX MOIS à décrire un logiciel que ComRoster n'était plus : champ
`nom` disparu du modèle, minimum de mot de passe faux, bibliothèque de glisser-déposer
jamais utilisée, six routes annoncées contre soixante-trois servies. Rien ne l'a signalé,
parce que personne ne relit un document de référence à côté du code.

D'où ces gardes. Elles ne jugent pas la prose : elles confrontent les quelques CHIFFRES
que le document affirme à ce que le code répond. Quand l'un bouge, le test tombe et
nomme la phrase à corriger — c'est le seul mécanisme qui empêche la dérive de recommencer.

Le coût est assumé : ajouter une route oblige à mettre à jour un nombre dans le document.
C'est exactement ce qu'on veut. Un document qu'on n'a jamais à toucher est un document
qui ment déjà.
"""
import pathlib
import re

import pytest

from comroster import create_app

RACINE = pathlib.Path(__file__).resolve().parent.parent
CAHIER = RACINE / "comroster-cahier-des-charges.md"


@pytest.fixture(scope="module")
def texte():
    return CAHIER.read_text(encoding="utf-8")


def _entier_avant(texte, motif):
    """Le nombre écrit juste avant `motif` dans le document.

    On lit le document plutôt que de coder la valeur en dur ici : sinon la valeur
    attendue vivrait à DEUX endroits, et c'est précisément le motif qui produit les
    divergences que ces tests surveillent.
    """
    trouve = re.search(r"\*\*(\d+)[^*]*\*\*\s*" + motif, texte) or re.search(
        r"(\d+)\s+" + motif, texte)
    assert trouve, f"le document n'annonce plus de nombre pour « {motif} »"
    return int(trouve.group(1))


def test_le_minimum_de_mot_de_passe_annonce_est_celui_du_code(texte):
    """Le document a annoncé 8 caractères pendant deux mois ; le code en impose 4."""
    from comroster.auth import MIN_PASSWORD_LENGTH
    assert f"**{MIN_PASSWORD_LENGTH} caractères minimum**" in texte, (
        f"le cahier des charges n'annonce pas « {MIN_PASSWORD_LENGTH} caractères "
        "minimum » alors que c'est ce que le code impose"
    )


def test_le_nombre_de_routes_annonce_est_celui_servi(texte):
    app = create_app({"DATA_DIR": "/tmp/cdc-test", "SECRET_KEY": "x"})
    reelles = len(list(app.url_map.iter_rules()))
    annonce = _entier_avant(texte, "routes")
    assert annonce == reelles, (
        f"le cahier des charges annonce {annonce} routes, le produit en sert {reelles}"
    )


def test_le_nombre_de_services_annonce_est_celui_du_paquet(texte):
    reels = len([p for p in (RACINE / "comroster" / "services").glob("*.py")
                 if p.name != "__init__.py"])
    # Le document écrit ce nombre en toutes lettres : on cherche donc la phrase, pas un
    # nombre isolé.
    assert re.search(r"\*\*vingt-trois services\*\*", texte), (
        "la phrase qui annonce le nombre de services a changé de forme"
    )
    assert reels == 23, f"{reels} services dans le paquet, le document en annonce vingt-trois"


def test_la_palette_annoncee_est_celle_de_l_admin(texte):
    source = (RACINE / "static" / "js" / "admin.js").read_text(encoding="utf-8")
    bloc = re.search(r"GROUP_PALETTE = \[(.*?)\]", source, re.DOTALL)
    assert bloc, "GROUP_PALETTE introuvable dans admin.js"
    reelles = len(re.findall(r"#[0-9A-Fa-f]{6}", bloc.group(1)))
    annonce = _entier_avant(texte, "teintes")
    assert annonce == reelles, (
        f"le cahier des charges annonce {annonce} teintes, la palette en compte {reelles}"
    )


def test_le_champ_nom_reste_absent_du_modele(texte):
    """Le document affirme qu'il n'y a pas de champ `nom`. Qu'il le reste.

    C'est l'affirmation la plus coûteuse à laisser dériver : elle décrit une DÉCISION
    (on cherche une fonction, pas une personne), et un champ réintroduit sans la rouvrir
    passerait inaperçu.
    """
    from comroster.services.model import build_draft
    assert "**Il n'y a pas de champ `nom`" in texte
    etat = build_draft({"groups": [], "people": [{"beltpack": "10", "role": "Régie"}]})
    assert set(etat["people"][0]) == {"id", "role", "beltpack", "group_id"}, (
        f"la forme d'un beltpack a changé : {sorted(etat['people'][0])}"
    )
