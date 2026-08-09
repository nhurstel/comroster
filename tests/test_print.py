"""Feuille d'affectation imprimable (ajout n°4, audit 2026-07-28).

Les régies travaillent sur papier, et une conduite imprimée survit à une panne du boîtier.
Comme `/admin/preview`, la feuille rend l'état PUBLIÉ par défaut — ce que la salle voit —
et `?draft=1` la version en préparation.
"""
import re

import pytest

from comroster.api import SEUIL_GROUPE_LONG, _beltpack_sort_key, _date_fr
from comroster.services import model


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


def test_le_lien_vers_le_brouillon_n_apparait_que_s_il_y_a_un_brouillon(plateau):
    """Demande de Nathan. Juste après une publication, brouillon et publié sont le MÊME
    plateau : proposer « Imprimer le brouillon » offrirait deux liens pour un seul
    document, et le doute d'avoir la mauvaise feuille en main au pire moment.

    La comparaison ignore `updated_at`, ré-horodaté à chaque frappe — s'y fier annoncerait
    un écart là où l'on a seulement retapé le même mot.
    """
    assert "Imprimer le brouillon" not in plateau.get("/admin/print").get_data(as_text=True)

    plateau.post("/api/groups", json={"name": "Lumière", "color": "#E4B93C"})
    assert "Imprimer le brouillon" in plateau.get("/admin/print").get_data(as_text=True)

    plateau.post("/api/publish")
    assert "Imprimer le brouillon" not in plateau.get("/admin/print").get_data(as_text=True)


def test_reenregistrer_le_brouillon_sans_le_changer_ne_cree_pas_un_faux_brouillon(
        plateau, monkeypatch):
    """Réenregistrer le brouillon tel quel le ré-horodate sans rien changer d'autre.

    C'est le cas courant, pas un cas tordu : l'administration enregistre le brouillon à
    chaque frappe, et `build_draft` repose `updated_at` à chaque fois. Une comparaison
    brute des deux états annoncerait donc « brouillon à imprimer » après un simple
    passage dans un champ, alors qu'il n'y a rien de plus à sortir que la version déjà à
    l'antenne. C'est ce test qui justifie d'écarter `updated_at`.

    L'horodatage est FORCÉ plutôt qu'attendu : `now_iso()` a une granularité d'une
    seconde, et un test qui s'exécute en millisecondes réécrit la même valeur — la
    mutation de contrôle passait au vert pour cette seule raison, sans rien prouver.
    """
    avant = plateau.get("/api/state").get_json()
    monkeypatch.setattr(model, "now_iso", lambda: "2030-01-01T00:00:00Z")
    assert plateau.put("/api/draft", json=avant).status_code == 200

    apres = plateau.get("/api/state").get_json()
    # Témoin positif : sans écart d'horodatage réel, l'assertion suivante ne prouverait
    # rien (leçon 2026-07-23 sur les assertions négatives creuses).
    assert apres["updated_at"] != avant["updated_at"]
    assert {k: v for k, v in apres.items() if k != "updated_at"} == \
           {k: v for k, v in avant.items() if k != "updated_at"}

    html = plateau.get("/admin/print").get_data(as_text=True)
    assert "Imprimer le brouillon" not in html, (
        "un simple réenregistrement a été pris pour un brouillon à imprimer"
    )


def test_un_plateau_jamais_publie_propose_quand_meme_son_brouillon(auth_client):
    """Sans publication, la feuille « publiée » est vide : c'est le seul cas où le lien
    doit s'afficher alors qu'il n'y a rien à comparer."""
    auth_client.post("/api/groups", json={"name": "Son", "color": "#3FA6B0"})
    assert "Imprimer le brouillon" in auth_client.get("/admin/print").get_data(as_text=True)


def test_un_groupe_range_a_la_main_garde_son_ordre_sur_le_papier(plateau):
    """La feuille est le TROISIÈME lecteur de l'ordre, après l'admin et l'écran.

    Un régisseur qui range ses beltpacks dans un ordre à lui — l'ordre d'appel, celui du
    plan de feu — le fait pour s'y retrouver ; une conduite papier qui le retrie derrière
    lui contredit l'écran au moment précis où le boîtier n'est plus là pour arbitrer.
    """
    etat = plateau.get("/api/state").get_json()
    etat["groups"][0]["manual_order"] = True
    # Ordre délibérément CONTRAIRE au tri numérique : sans la garde, il serait effacé.
    membres = [p for p in etat["people"] if p["group_id"]]
    reste = [p for p in etat["people"] if not p["group_id"]]
    etat["people"] = reste + sorted(membres, key=lambda p: -int(p["beltpack"]))
    assert plateau.put("/api/draft", json=etat).status_code == 200

    html = plateau.get("/admin/print?draft=1").get_data(as_text=True)
    positions = [html.index(f'class="c-bp">{n}<') for n in ("10", "2", "1")]
    assert positions == sorted(positions), "la feuille a retrié un groupe rangé à la main"


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


def test_la_feuille_ne_parle_jamais_d_un_nom_qui_n_existe_pas(plateau):
    """Une personne, c'est {id, role, beltpack, group_id} : le champ nom n'existe plus.

    L'en-tête de colonne disait « NOM » et affichait le RÔLE (leçon 2026-07-23 n°32).
    Cet en-tête a été supprimé le 2026-08-05 avec la refonte « le numéro d'abord » — la
    garde reste, car ce qu'elle protège n'est pas l'en-tête mais le VOCABULAIRE : la
    feuille ne doit jamais promettre un nom qu'elle est incapable d'imprimer. Elle porte
    donc désormais sur le contenu RENDU, seule preuve que la feuille dit vrai.
    """
    html = plateau.get("/admin/print").get_data(as_text=True)
    assert ">Nom<" not in html
    assert "Régie" in html          # le plateau de test est bien imprimé


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
