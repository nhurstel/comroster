"""Feuille d'affectation imprimable (ajout n°4, audit 2026-07-28).

Les régies travaillent sur papier, et une conduite imprimée survit à une panne du boîtier.
Comme `/admin/preview`, la feuille rend l'état PUBLIÉ par défaut — ce que la salle voit —
et `?draft=1` la version en préparation.
"""
import pytest

from comroster.api import _beltpack_sort_key


@pytest.fixture
def plateau(auth_client):
    r = auth_client.post("/api/groups", json={"name": "Son", "color": "#3FA6B0"})
    gid = r.get_json()["id"]
    for num, role in (("10", "HF"), ("2", "Régie"), ("1", "Plateau")):
        auth_client.post("/api/people", json={"role": role, "beltpack": num, "group_id": gid})
    auth_client.post("/api/people", json={"role": "Renfort", "beltpack": "42"})
    auth_client.post("/api/publish")
    return auth_client


def test_la_feuille_montre_l_etat_publie_par_defaut(plateau):
    html = plateau.get("/admin/print").get_data(as_text=True)
    assert "Son" in html and "HF" in html and "Régie" in html
    assert "Non affectés" in html and "Renfort" in html
    assert "État publié" in html


def test_le_brouillon_est_accessible_explicitement(plateau):
    plateau.post("/api/groups", json={"name": "Lumière", "color": "#E4B93C"})
    assert "Lumière" not in plateau.get("/admin/print").get_data(as_text=True)
    assert "Lumière" in plateau.get("/admin/print?draft=1").get_data(as_text=True)


def test_les_beltpacks_sont_tries_numeriquement(plateau):
    """En tri texte, « 10 » se glisse entre « 1 » et « 2 » : une feuille papier
    devient alors pénible à parcourir."""
    html = plateau.get("/admin/print").get_data(as_text=True)
    positions = [html.index(f'class="c-bp">{n}<') for n in ("1", "2", "10")]
    assert positions == sorted(positions), "ordre des numéros incorrect sur la feuille"


def test_cle_de_tri_numerique():
    nums = ["10", "2", "1", "abc", "7"]
    assert sorted(nums, key=_beltpack_sort_key) == ["1", "2", "7", "10", "abc"]
    assert _beltpack_sort_key(None) == (1, 0, "")


def test_la_feuille_n_a_ni_script_inline_ni_style_inline(plateau):
    """CSP stricte : le moindre style inline casserait la page (leçon 2026-07-07)."""
    html = plateau.get("/admin/print").get_data(as_text=True)
    assert "<style" not in html
    assert "onclick" not in html
    assert 'style="' not in html


def test_la_couleur_de_groupe_passe_par_un_attribut_de_donnees(plateau):
    """Elle est appliquée en CSSOM par print.js — jamais en attribut style."""
    html = plateau.get("/admin/print").get_data(as_text=True)
    assert 'data-color="#3FA6B0"' in html


def test_un_plateau_vide_le_dit_au_lieu_d_imprimer_une_page_blanche(auth_client):
    html = auth_client.get("/admin/print").get_data(as_text=True)
    assert "Aucune affectation à imprimer" in html


def test_la_feuille_exige_une_session(client):
    client.post("/admin/setup", data={"password": "motdepasse8"})
    client.post("/admin/logout")
    assert client.get("/admin/print").status_code in (302, 401)


def test_le_pluriel_des_beltpacks_est_accorde(auth_client):
    """« 1 beltpacks » trahit la machine (leçon 2026-07-28)."""
    auth_client.post("/api/people", json={"role": "HF", "beltpack": "12"})
    auth_client.post("/api/publish")
    html = auth_client.get("/admin/print").get_data(as_text=True)
    assert "1 beltpack" in html and "1 beltpacks" not in html
