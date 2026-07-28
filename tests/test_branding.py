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


# ---------------------------------------------------------------------------
# Routes de service des logos
# ---------------------------------------------------------------------------

from comroster import create_app  # noqa: E402


def _client_avec_pack(tmp_path, manifeste=None, fichiers=("logo.svg",)):
    chemin = _pack(tmp_path, manifeste or {"name": "Acme Live", "logo": "logo.svg"}, fichiers)
    app = create_app({
        "TESTING": True,
        "DATA_DIR": str(tmp_path),
        "SECRET_KEY": "test-secret",
        "BRAND_DIR": chemin,
    })
    return app.test_client()


def test_sans_pack_la_route_du_logo_repond_404(client):
    assert client.get("/branding/logo").status_code == 404
    assert client.get("/branding/logo-print").status_code == 404


def test_avec_pack_la_route_sert_le_logo(tmp_path):
    r = _client_avec_pack(tmp_path).get("/branding/logo")
    assert r.status_code == 200
    assert r.mimetype == "image/svg+xml"


def test_le_logo_papier_est_servi_sur_sa_propre_route(tmp_path):
    r = _client_avec_pack(tmp_path).get("/branding/logo-print")
    assert r.status_code == 200


def test_le_logo_est_mis_en_cache(tmp_path):
    """Un écran de régie tourne des jours d'affilée : retélécharger le logo à chaque
    rechargement de page serait du gaspillage. L'invalidation passe par `?v=`."""
    r = _client_avec_pack(tmp_path).get("/branding/logo")
    assert "max-age" in r.headers["Cache-Control"]


def test_la_marque_est_disponible_dans_les_templates(tmp_path):
    """`brand` est injecté globalement : les templates n'ont pas à se le faire passer."""
    chemin = _pack(tmp_path, {"name": "Acme Live", "logo": "logo.svg"})
    app = create_app({
        "TESTING": True,
        "DATA_DIR": str(tmp_path),
        "SECRET_KEY": "test-secret",
        "BRAND_DIR": chemin,
    })
    with app.test_request_context():
        from flask import render_template_string
        assert render_template_string("{{ brand.name }}") == "Acme Live"


# ---------------------------------------------------------------------------
# Rendu du tableau de régie
# ---------------------------------------------------------------------------


def test_sans_pack_le_display_garde_le_glyphe_comroster(client):
    """Non-régression : le comportement par défaut ne bouge pas d'un octet."""
    html = client.get("/display").get_data(as_text=True)
    assert "comroster-glyph.svg" in html
    assert "COMROSTER par Nathan Hurstel" in html
    assert "/branding/logo" not in html


def test_avec_pack_le_display_affiche_le_logo_client(tmp_path):
    html = _client_avec_pack(tmp_path).get("/display").get_data(as_text=True)
    assert "/branding/logo" in html
    assert 'alt="Acme Live"' in html
    assert "comroster-glyph.svg" not in html


def test_avec_pack_le_credit_comroster_devient_discret(tmp_path):
    """Co-branding : la signature reste, elle cède la place d'honneur."""
    html = _client_avec_pack(tmp_path).get("/display").get_data(as_text=True)
    assert "Propulsé par ComRoster" in html
    assert "COMROSTER par Nathan Hurstel" not in html


def test_un_logo_couleur_est_protege_de_l_inversion_du_theme_jour(tmp_path):
    """Le thème jour inverse le glyphe monochrome de ComRoster ; appliqué à un logo
    couleur, ce filtre le rendrait en négatif."""
    html = _client_avec_pack(tmp_path).get("/display").get_data(as_text=True)
    assert "brand-mark-color" in html


def test_un_logo_monochrome_reste_inverse_en_theme_jour(tmp_path):
    html = _client_avec_pack(
        tmp_path, {"name": "Acme", "logo": "logo.svg", "mono": True}
    ).get("/display").get_data(as_text=True)
    assert "brand-mark-color" not in html
