"""Pagination de la feuille imprimée, et les trois titres de son en-tête.

Arbitrages de Nathan (2026-08-05) : au plus 40 beltpacks par page — « c'est souvent
moins », donc un PLAFOND et non une cible —, jusqu'à 4 colonnes, et les trois titres
présents ensemble dans l'en-tête.

Le découpage vit côté serveur : une règle exprimée en NOMBRE DE LIGNES ne s'exprime pas
en hauteur de boîte, et un saut de page à l'intérieur d'un conteneur multi-colonnes est
mal supporté. Il est donc testable ici, sans navigateur — les tests e2e, eux, continuent
de lire un vrai PDF.
"""
import html
import re

import pytest

from comroster.api import MAX_BELTPACKS_PAR_PAGE, _paginer


def _plateau(*effectifs):
    groupes, par_groupe = [], {}
    numero = 1
    for rang, effectif in enumerate(effectifs):
        gid = f"g{rang}"
        groupes.append({"id": gid, "name": f"Groupe {rang}", "order": rang})
        par_groupe[gid] = []
        for _ in range(effectif):
            par_groupe[gid].append({"beltpack": str(numero), "role": f"Poste {numero}"})
            numero += 1
    return groupes, par_groupe


def _occupation(pages):
    return [sum(len(membres) for _, membres in page) for page in pages]


def test_aucune_page_ne_depasse_le_plafond():
    """La seule propriété que Nathan a fixée en chiffre."""
    pages = _paginer(*_plateau(6, 14, 9, 7, 5, 8, 4, 6, 3))   # le plateau réel : 62
    assert _occupation(pages) == [36, 26]
    assert all(n <= MAX_BELTPACKS_PAR_PAGE for n in _occupation(pages))


def test_exactement_le_plafond_tient_sur_une_page():
    """40 est un maximum ATTEINT, pas dépassé : la borne se teste sur sa valeur exacte."""
    assert _occupation(_paginer(*_plateau(MAX_BELTPACKS_PAR_PAGE))) == [40]
    assert _occupation(_paginer(*_plateau(MAX_BELTPACKS_PAR_PAGE + 1))) == [40, 1]


def test_un_groupe_plus_grand_que_la_page_est_coupe():
    """Il n'y a pas d'autre issue : on ne peut pas poser 95 lignes sur une page de 40."""
    assert _occupation(_paginer(*_plateau(95))) == [40, 40, 15]


def test_un_groupe_qui_tiendrait_entier_ailleurs_n_est_pas_coupe():
    """35 + 30 : le second ne rentre pas dans les 5 places restantes.

    Le couper y logerait 5 lignes et renverrait les 25 autres au verso — or lire la
    moitié d'un groupe au verso est exactement ce qui fait rater une affectation
    (leçon 2026-07-30). On ouvre donc une page, quitte à laisser du blanc.
    """
    assert _occupation(_paginer(*_plateau(35, 30))) == [35, 30]


def test_les_groupes_vides_ne_consomment_pas_de_quota():
    """Un groupe sans personne s'affiche (il dit « personne ici ») mais ne pèse rien."""
    pages = _paginer(*_plateau(0, 40, 0))
    assert _occupation(pages) == [40]
    assert len(pages) == 1


def test_aucun_groupe_ne_produit_aucune_page():
    """Pas de page blanche pour un plateau vide."""
    assert _paginer([], {}) == []


def test_toutes_les_personnes_sont_reparties_une_fois_et_une_seule():
    """Garde de conservation : une pagination qui PERD une ligne est le pire des défauts.

    Aucune assertion sur les tailles de page ne l'attraperait — [40, 40, 15] reste
    plausible même si trois beltpacks ont disparu en route.
    """
    groupes, par_groupe = _plateau(6, 14, 9, 7, 5, 8, 4, 6, 3)
    attendus = [p["beltpack"] for membres in par_groupe.values() for p in membres]
    obtenus = [p["beltpack"] for page in _paginer(groupes, par_groupe)
               for _, membres in page for p in membres]
    assert sorted(obtenus, key=int) == sorted(attendus, key=int)
    assert len(obtenus) == len(set(obtenus)), "un beltpack imprimé deux fois"


@pytest.fixture
def feuille(auth_client, app):
    """Rend /admin/print avec les champs de titre voulus."""
    def _rendre(**champs):
        storage = app.extensions["storage"]
        etat = storage.load_draft()
        etat.update(champs)
        storage.save_draft(etat)
        auth_client.post("/api/publish", json={})
        return html.unescape(auth_client.get("/admin/print").get_data(as_text=True))
    return _rendre


def test_les_trois_titres_coexistent_dans_l_entete(feuille):
    """`production_name or title` était un OU EXCLUSIF.

    Dès qu'un nom de production existait, le titre du plateau disparaissait du papier —
    silencieusement, puisque la feuille restait parfaitement bien formée.
    """
    page = feuille(production_name="Festival Avignon 2026", title="Le Roi Lear",
                   subtitle="Generale salle Vedene")
    entete = re.search(r'<div class="sheet-title">(.*?)</div>', page, re.DOTALL).group(1)
    assert "Festival Avignon 2026" in entete
    assert "Le Roi Lear" in entete
    assert "Generale salle Vedene" in entete


def test_le_titre_seul_ne_fabrique_pas_de_sur_titre_vide(feuille):
    """Sans nom de production, aucun bloc ne doit être posé — pas même vide."""
    page = feuille(production_name="", title="Le Roi Lear", subtitle="")
    assert "sheet-prod" not in page
    assert "Le Roi Lear" in page


def test_le_nom_de_production_seul_sert_de_titre(feuille):
    """Repli : le titre principal est le seul champ qui ne peut pas rester vide."""
    page = feuille(production_name="Festival Avignon 2026", title="", subtitle="")
    entete = re.search(r'<div class="sheet-title">(.*?)</div>', page, re.DOTALL).group(1)
    assert "Festival Avignon 2026" in entete
    # Il monte en h1 plutôt que de laisser un sur-titre orphelin au-dessus du repli.
    assert "sheet-prod" not in entete
