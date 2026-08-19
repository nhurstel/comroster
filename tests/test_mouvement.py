"""Garde : le mouvement réduit est respecté partout, et les entrées restent courtes.

Pourquoi ce fichier existe. Le 2026-08-19, `display.css` s'est révélée être la seule
feuille animée à ignorer `prefers-reduced-motion` — alors que c'est celle qui anime le
plus : cascade d'arrivée des blocs, fondu des textes, sur un écran regardé en continu
pendant un spectacle. Trois feuilles portaient la règle, une l'avait manquée, rien ne le
disait.

`prefers-reduced-motion` n'est pas une préférence esthétique. C'est une demande exprimée
par la personne qui regarde, dans son système, souvent parce que le mouvement lui coûte —
vertiges, migraines, troubles vestibulaires. Une application ne la renégocie pas.

Le second contrôle porte sur le BUDGET d'entrée. Une animation d'arrivée est gratuite tant
qu'elle reste sous le seuil où l'on commence à attendre. Passé ce seuil elle cesse d'être
un agrément pour devenir un péage — payé à chaque connexion, plusieurs fois par jour, par
quelqu'un qui monte un spectacle.

Deux erreurs de la première version de ce fichier, gardées en mémoire ici parce qu'elles
disent comment se tromper : il exigeait la règle FEUILLE par feuille (or `skins.css` est
chargée avec `display.css`, dont le sélecteur `*` la couvre déjà), et il mesurait la plus
longue animation de chaque feuille — donc `auth-respire`, une respiration en boucle de
2,6 s, prise pour une entrée. Un invariant mal formulé échoue sur son propre postulat.
"""
import os
import re

import pytest

STATIC_CSS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "css"
)

#: Feuilles chargées ENSEMBLE. La règle de mouvement réduit porte sur `*` : il suffit
#: qu'une feuille du groupe la déclare pour que tout le groupe soit couvert. Découpage
#: repris de tests/test_css_tokens.py — deux gardes qui divisent le même monde de deux
#: façons différentes finiraient par se contredire.
GROUPES = {
    "affichage": ["main.css", "display.css", "skins.css"],
    "administration": ["admin.css"],
    "connexion": ["auth.css"],
    "impression": ["print.css"],
}

#: L'animation d'ENTRÉE de chaque surface. Nommer plutôt que deviner : une feuille contient
#: aussi des animations en boucle (`auth-respire`, `conn-slide`) légitimement longues, que
#: mesurer comme des entrées n'aurait aucun sens.
ENTREES = {"admin.css": "admin-entree", "auth.css": "auth-arrivee"}

#: Budget d'entrée, retard le plus tardif COMPRIS. Large à dessein : les entrées réelles
#: tiennent en 310 ms (admin) et 400 ms (connexion). Le seuil empêche la dérive, il ne
#: borde pas au plus juste — un test qui colle à la valeur du jour se casse au premier
#: réglage fin et n'apprend rien.
BUDGET_ENTREE_MS = 500

REDUCED = "@media (prefers-reduced-motion: reduce)"
RETARD = re.compile(r"animation-delay:\s*(\d+(?:\.\d+)?)(ms|s)")
DUREE_QUELCONQUE = re.compile(r"animation:\s*[^;]*?(\d+(?:\.\d+)?)(ms|s)\b")


def _lire(nom):
    with open(os.path.join(STATIC_CSS, nom), encoding="utf-8") as fh:
        return fh.read()


def _ms(valeur, unite):
    return float(valeur) * (1000 if unite == "s" else 1)


@pytest.mark.parametrize("groupe", sorted(GROUPES))
def test_tout_groupe_qui_anime_respecte_le_mouvement_reduit(groupe):
    feuilles = {f: _lire(f) for f in GROUPES[groupe] if os.path.exists(os.path.join(STATIC_CSS, f))}
    assert feuilles, f"aucune feuille lue pour « {groupe} » — le test ne prouverait rien"
    anime = any(DUREE_QUELCONQUE.search(css) or "transition:" in css for css in feuilles.values())
    if not anime:
        pytest.skip(f"« {groupe} » n'anime rien — la règle n'aurait rien à couper")
    porteuses = [nom for nom, css in feuilles.items() if REDUCED in css]
    assert porteuses, (
        f"le groupe « {groupe} » ({', '.join(feuilles)}) anime, mais aucune de ses feuilles "
        f"ne porte « {REDUCED} ». Ce n'est pas une préférence esthétique : c'est une "
        "demande de la personne qui regarde, exprimée dans son système. Recopier le bloc "
        "d'un autre groupe — il n'a aucune raison de différer."
    )


@pytest.mark.parametrize("feuille", sorted(ENTREES))
def test_les_entrees_restent_sous_le_budget(feuille):
    """Le dernier élément d'une cascade doit être arrivé avant qu'on ne l'attende."""
    css = _lire(feuille)
    nom = ENTREES[feuille]
    durees = [
        _ms(v, u)
        for v, u in re.findall(rf"animation:\s*{nom}\s+(\d+(?:\.\d+)?)(ms|s)\b", css)
    ]
    assert durees, (
        f"{feuille} : aucune animation « {nom} » lue. Si l'entrée a été renommée, mettre "
        "ENTREES à jour ; sinon, elle a disparu et c'est le vrai sujet."
    )
    retards = [_ms(v, u) for v, u in RETARD.findall(css)]
    pire = max(retards or [0]) + max(durees)
    assert pire <= BUDGET_ENTREE_MS, (
        f"{feuille} : la plus longue entrée s'achève à {pire:.0f} ms, au-delà du budget de "
        f"{BUDGET_ENTREE_MS} ms. Une animation d'arrivée est gratuite tant qu'on ne "
        "l'attend pas ; passé ce seuil elle devient un péage, payé à chaque connexion."
    )


def test_l_entree_de_l_admin_ne_s_accroche_pas_aux_panneaux():
    """Un panneau est piloté par `hidden`, donc par `display` : l'y accrocher ferait
    rejouer l'entrée à CHAQUE changement d'onglet, dix fois par heure.

    Contrôle volontairement étroit : il vise la faute qu'on risque de commettre en
    étendant la cascade, pas toute mention de `.tab-panel`.
    """
    css = _lire("admin.css")
    fautives = [
        ligne.strip()
        for ligne in css.splitlines()
        if "animation:" in ligne and "admin-entree" in ligne and "tab-panel" in ligne
    ]
    assert not fautives, (
        "l'entrée de l'administration est posée sur un panneau : elle rejouera à chaque "
        f"changement d'onglet. L'ancrer sur les conteneurs stables. {fautives}"
    )
