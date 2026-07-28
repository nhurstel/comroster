"""Marque client : le logo d'un client à la place de celui de ComRoster.

La marque est une propriété du BOÎTIER, pas une donnée d'application : elle vit dans un
dossier système que l'application lit et n'écrit jamais. Le verrou tient à l'absence de
tout chemin d'écriture — pas à un contrôle d'accès qu'on pourrait contourner.

D'où le cœur de ce fichier : les cas de REPLI. Un pack mal posé doit dégrader l'apparence
et rien d'autre. Un boîtier qui refuserait de démarrer une heure avant un show à cause
d'un logo mal nommé serait un défaut bien pire que l'absence de logo.
"""
import json

import pytest

from comroster.services.branding import Branding

SVG = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"></svg>'


def _pack(tmp_path, manifeste, fichiers=("logo.svg",)):
    """Fabrique un pack de marque sur disque et renvoie son chemin."""
    d = tmp_path / "branding"
    d.mkdir(exist_ok=True)
    for nom in fichiers:
        (d / nom).write_bytes(SVG)
    (d / "brand.json").write_text(json.dumps(manifeste), encoding="utf-8")
    return str(d)


def test_sans_dossier_la_marque_est_inactive():
    b = Branding("")
    assert b.active is False
    assert b.name == ""


def test_un_pack_valide_est_charge(tmp_path):
    b = Branding(_pack(tmp_path, {"name": "Acme Live", "logo": "logo.svg"}))
    assert b.active is True
    assert b.name == "Acme Live"
    assert b.logo_path.endswith("logo.svg")
    assert b.mono is False
    assert b.version > 0


def test_sans_logo_print_la_variante_papier_reprend_le_logo_ecran(tmp_path):
    b = Branding(_pack(tmp_path, {"name": "Acme Live", "logo": "logo.svg"}))
    assert b.print_logo_path == b.logo_path


def test_le_logo_print_est_pris_en_compte_quand_il_existe(tmp_path):
    chemin = _pack(
        tmp_path,
        {"name": "Acme Live", "logo": "logo.svg", "logo_print": "noir.svg"},
        fichiers=("logo.svg", "noir.svg"),
    )
    b = Branding(chemin)
    assert b.print_logo_path.endswith("noir.svg")
    assert b.logo_path.endswith("logo.svg")


def test_le_drapeau_mono_est_lu(tmp_path):
    b = Branding(_pack(tmp_path, {"name": "Acme", "logo": "logo.svg", "mono": True}))
    assert b.mono is True


@pytest.mark.parametrize(
    "manifeste,fichiers",
    [
        ({"logo": "logo.svg"}, ("logo.svg",)),                       # name absent
        ({"name": "  ", "logo": "logo.svg"}, ("logo.svg",)),         # name vide
        # name d'un mauvais type (int) : JSON valide, faute de fabrication plausible —
        # doit retomber sur ComRoster comme les autres fautes, jamais planter en AttributeError.
        ({"name": 123, "logo": "logo.svg"}, ("logo.svg",)),          # name mal typé
        ({"name": "Acme"}, ("logo.svg",)),                           # logo absent
        ({"name": "Acme", "logo": "absent.svg"}, ("logo.svg",)),     # fichier introuvable
        ({"name": "Acme", "logo": "logo.jpg"}, ("logo.jpg",)),       # extension interdite
        ({"name": "Acme", "logo": "../logo.svg"}, ("logo.svg",)),    # échappement de dossier
        ({"name": "Acme", "logo": "sous/logo.svg"}, ("logo.svg",)),  # chemin, pas un nom
    ],
)
def test_un_pack_invalide_retombe_sur_comroster(tmp_path, manifeste, fichiers):
    """Chaque faute doit produire le MÊME résultat : marque inactive, aucune exception."""
    b = Branding(_pack(tmp_path, manifeste, fichiers))
    assert b.active is False


def test_un_manifeste_illisible_retombe_sur_comroster(tmp_path):
    d = tmp_path / "branding"
    d.mkdir()
    (d / "brand.json").write_text("{ceci n'est pas du json", encoding="utf-8")
    assert Branding(str(d)).active is False


def test_un_manifeste_non_objet_retombe_sur_comroster(tmp_path):
    d = tmp_path / "branding"
    d.mkdir()
    (d / "brand.json").write_text('["Acme"]', encoding="utf-8")
    assert Branding(str(d)).active is False


def test_un_dossier_inexistant_retombe_sur_comroster(tmp_path):
    assert Branding(str(tmp_path / "nulle-part")).active is False
