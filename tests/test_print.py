"""Feuille d'affectation imprimable (ajout n°4, audit 2026-07-28).

Les régies travaillent sur papier, et une conduite imprimée survit à une panne du boîtier.
Comme `/admin/preview`, la feuille rend l'état PUBLIÉ par défaut — ce que la salle voit —
et `?draft=1` la version en préparation.
"""
import re

import pytest

from comroster.api import SEUIL_GROUPE_LONG, _beltpack_sort_key, _date_fr


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
    # La réserve ne s'imprime plus : une conduite liste ce qui est AFFECTÉ.
    assert "Non affectés" not in html and "Renfort" not in html
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


def test_l_admin_nomme_la_fonction_impression(auth_client):
    """« Feuille imprimable » décrivait l'objet produit ; « Impression » décrit ce que
    l'utilisateur vient faire. Nommer par la fonction, pas par l'artefact (leçon 37)."""
    html = auth_client.get("/admin").get_data(as_text=True)
    # L'entrée est devenue un <button> qui bascule un panneau (elle n'ouvre plus de page) :
    # c'est le LIBELLÉ que cette garde protège, pas la balise qui le porte.
    assert ">Impression</button>" in html
    assert "Feuille imprimable" not in html


def test_le_titre_de_la_page_porte_le_nouveau_nom(plateau):
    html = plateau.get("/admin/print").get_data(as_text=True)
    titre = html.split("<title>", 1)[1].split("</title>", 1)[0]
    assert titre.startswith("Impression")
    assert "Feuille d'affectation" not in titre


def test_la_colonne_annonce_le_role_et_non_le_nom(plateau):
    """Une personne, c'est {id, role, beltpack, group_id} : le champ nom n'existe plus.
    L'en-tête « NOM » affichait donc le rôle — récidive de la leçon 2026-07-23 n°32."""
    html = plateau.get("/admin/print").get_data(as_text=True)
    assert ">Rôle<" in html
    assert ">Nom<" not in html


def test_le_pied_date_en_francais_et_jamais_en_iso(plateau):
    """« 2026-07-30T13:13:59Z » dans une interface francophone (leçon n°56).

    On cherche le MOTIF ISO, pas la lettre « Z » : un nom de production ou de marque
    peut légitimement en contenir une, et le test se mettrait à mentir au premier
    client dont le nom porte un Z."""
    html = plateau.get("/admin/print").get_data(as_text=True)
    pied = html.split('class="sheet-foot"', 1)[1].split("</footer>", 1)[0]
    assert not re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", pied), "horodatage ISO au pied"
    assert re.search(r"\d{2}/\d{2}/\d{4} à \d{2}:\d{2}", pied), "date française attendue"


def test_date_fr_convertit_l_horodatage_du_modele():
    assert _date_fr("2026-07-30T13:13:59Z").startswith("30/07/2026 à ")


@pytest.mark.parametrize("valeur", [None, 123, "", "pas une date", {"a": 1}])
def test_date_fr_ne_leve_jamais_sur_une_donnee_externe(valeur):
    """`updated_at` vient d'un fichier d'état : une valeur absente ou mal typée ne doit
    pas empêcher d'imprimer la conduite. Le `or ""` protège du None, pas du int
    (leçon 2026-07-29 n°68)."""
    assert _date_fr(valeur) == ""


def test_un_groupe_long_devient_coupable_et_un_groupe_court_non(auth_client):
    """`break-inside: avoid` sur TOUS les groupes est ce qui creuse une demi-colonne
    de vide. Le CSS ne sait pas compter des lignes : le seuil vit côté serveur."""
    court = auth_client.post("/api/groups", json={"name": "Court"}).get_json()["id"]
    long_ = auth_client.post("/api/groups", json={"name": "Long"}).get_json()["id"]
    for i in range(SEUIL_GROUPE_LONG):
        auth_client.post("/api/people", json={"beltpack": f"1{i:02d}", "group_id": court})
    for i in range(SEUIL_GROUPE_LONG + 1):
        auth_client.post("/api/people", json={"beltpack": f"2{i:02d}", "group_id": long_})
    auth_client.post("/api/publish")

    html = auth_client.get("/admin/print").get_data(as_text=True)
    bloc_court = html.split("Court", 1)[0].rsplit("<section", 1)[1]
    bloc_long = html.split("Long", 1)[0].rsplit("<section", 1)[1]
    assert "sheet-group-long" not in bloc_court, "un groupe au seuil reste insécable"
    assert "sheet-group-long" in bloc_long, "au-delà du seuil, le groupe doit pouvoir se couper"
