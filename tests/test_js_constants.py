"""Garde : les allowlists du navigateur ne doivent pas diverger du modèle serveur.

`SKINS` et `TEXT_SCALES` ont vécu en TROIS exemplaires (model.py, admin.js, display.js),
tenus par des commentaires « miroir de… ». Rien n'empêchait d'en modifier un seul : une
apparence connue du serveur mais absente du navigateur produit un `data-skin` que personne
ne style, donc un écran NU en salle — et l'inverse laisse choisir une apparence que le
serveur refuse à l'enregistrement.

Le remède structurel est ailleurs (les copies ont été fusionnées dans static/js/board.js) ;
ce test garde la frontière qui RESTE, celle entre Python et JavaScript. On lit board.js
comme du texte : l'exécuter demanderait Node, que la CI Python n'a pas à connaître.
"""
import json
import os
import re

from comroster.services import model

BOARD_JS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "js", "board.js"
)


def _source():
    with open(BOARD_JS, encoding="utf-8") as fh:
        return fh.read()


def _js_array(name, src):
    """Valeurs d'un `const <name> = [...]` littéral de board.js."""
    match = re.search(rf"const {name} = (\[[^\]]*\]);", src)
    assert match, f"{name} introuvable dans board.js — le test ne prouverait plus rien"
    return tuple(json.loads(match.group(1)))


def _js_draft_fields(src):
    """Clés déclarées dans `const DRAFT_FIELDS = {...}`."""
    match = re.search(r"const DRAFT_FIELDS = \{(.*?)\n  \};", src, re.DOTALL)
    assert match, "DRAFT_FIELDS introuvable dans board.js"
    return set(re.findall(r"^\s{4}(\w+):", match.group(1), re.MULTILINE))


def test_les_apparences_sont_identiques_des_deux_cotes():
    assert _js_array("SKINS", _source()) == model.SKINS, (
        "board.js et model.py ne connaissent pas les mêmes apparences : "
        "l'écran de régie retomberait sur une feuille de style inexistante"
    )


def test_les_tailles_de_texte_sont_identiques_des_deux_cotes():
    assert _js_array("TEXT_SCALES", _source()) == model.TEXT_SCALES


def test_le_brouillon_du_navigateur_couvre_tous_les_champs_du_modele():
    """Tout champ de `empty_state()` doit être repris par DRAFT_FIELDS.

    C'est la garde de fond du bug d'import : `production_name` et `text_scale` avaient été
    ajoutés au modèle sans l'être au chemin de reconstruction du navigateur, qui les
    effaçait donc en silence. `version` et `updated_at` sont exclus : ils appartiennent au
    serveur, qui les repose à chaque écriture — le navigateur n'a pas à les transporter.
    """
    serveur = set(model.empty_state()) - {"version", "updated_at"}
    navigateur = _js_draft_fields(_source())
    manquants = serveur - navigateur
    assert not manquants, (
        f"champs du modèle absents de DRAFT_FIELDS : {sorted(manquants)} — ils seront "
        "silencieusement effacés à l'import d'un fichier"
    )
    inconnus = navigateur - serveur
    assert not inconnus, (
        f"champs déclarés côté navigateur mais absents du modèle : {sorted(inconnus)} — "
        "ils seront rejetés par build_draft()"
    )
