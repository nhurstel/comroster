"""Les pages d'authentification, dans leurs CINQ états.

Ces deux pages ont été les dernières du produit à charger `main.css`, donc les dernières
à porter la DA abandonnée en juillet — voile turquoise, boutons en pilule, échelle de
tailles globale. Le découplage du 2026-08-04 le corrige ; ce fichier l'empêche de
revenir, sur le modèle de la garde qui protège déjà l'admin (test_ui.py).

Cinq états, pas un : deux ne s'obtiennent qu'en SORTIE d'un POST (le code de récupération
n'est affiché qu'une fois et n'est jamais restitué), et le diagnostic initial n'en avait
regardé qu'un seul. Un état oublié ici, c'est un état qui peut retomber sur main.css sans
que rien ne bronche.
"""
import re
from pathlib import Path

import pytest

CSS = Path(__file__).resolve().parent.parent / "static" / "css"

MDP = "motdepasse8"
MDP_NOUVEAU = "nouveau12"

#: Le code est rendu dans un bloc dédié — on le relit sur la page plutôt que de le
#: reconstruire, pour vérifier au passage qu'il est bien AFFICHÉ.
CODE = re.compile(r'class="auth-code"[^>]*>([^<]+)<')


def _texte(reponse):
    return reponse.get_data(as_text=True)


def _configurer(client):
    """Pose un administrateur et rend le code de récupération affiché."""
    html = _texte(client.post("/admin/setup", data={"password": MDP}))
    trouve = CODE.search(html)
    assert trouve, "le code de récupération n'est pas affiché après la création du compte"
    return html, trouve.group(1).strip()


def _cinq_etats(client):
    """Rend les cinq états dans le seul ordre qui les produit tous."""
    etats = {}

    # 4. Configuration initiale — n'existe que sur un boîtier vierge.
    etats["setup"] = _texte(client.get("/admin/setup"))
    # 5. Code de récupération après création.
    etats["setup-code"], code = _configurer(client)
    # 1. Connexion.
    etats["login"] = _texte(client.get("/admin/login"))
    # 2. Réinitialisation.
    etats["recover"] = _texte(client.get("/admin/recover"))
    # 3. Code de récupération après réinitialisation — consomme le code précédent.
    etats["login-code"] = _texte(client.post(
        "/admin/recover",
        data={"recovery_code": code, "password": MDP_NOUVEAU},
    ))
    return etats


@pytest.fixture
def etats(client):
    return _cinq_etats(client)


def test_les_cinq_etats_sont_bien_atteints(etats):
    """Témoin positif : sans lui, les assertions négatives ci-dessous ne prouveraient rien.

    Une page d'erreur ou une redirection ne contient pas non plus `main.css` — elle
    passerait donc le test de découplage en beauté. On vérifie donc d'abord que chaque
    état est bien CELUI qu'on croit tenir.
    """
    attendu = {
        "setup": "Configuration initiale",
        "setup-code": "Compte créé",
        "login": "Administration",
        "recover": "Réinitialisation",
        "login-code": "Mot de passe réinitialisé",
    }
    for nom, titre in attendu.items():
        assert titre in etats[nom], f"l'état « {nom} » n'a pas été atteint"


@pytest.mark.parametrize("etat", ["setup", "setup-code", "login", "recover", "login-code"])
def test_aucun_etat_ne_charge_main_css(etats, etat):
    """auth.css est AUTONOME : recharger main.css ramènerait l'héritage global."""
    html = etats[etat]
    assert "css/main.css" not in html, (
        f"l'état « {etat} » recharge main.css — l'héritage global est de retour"
    )
    assert "css/auth.css" in html


@pytest.mark.parametrize("etat", ["setup-code", "login-code"])
def test_le_code_de_recuperation_est_dans_son_bloc(etats, etat):
    assert CODE.search(etats[etat]), "le code n'est pas dans un bloc .auth-code"


def test_la_feuille_interdit_la_coupure_du_code():
    """Le seul texte du produit qu'un humain doit RECOPIER à la main.

    L'ancienne feuille le cassait au milieu d'un segment (`word-break: break-all` dans
    une carte de 420 px) : « LCJQ-6JYS-Z393-S » puis « 8ZH ». Un code recopié faux, c'est
    un boîtier qu'on ne rouvre plus. La règle se lit ici dans la feuille, faute de moteur
    de rendu ; l'e2e, lui, mesure la géométrie réelle.
    """
    feuille = (CSS / "auth.css").read_text(encoding="utf-8")
    regle = re.search(r"\.auth-code\s*\{([^}]*)\}", feuille)
    assert regle, "le bloc .auth-code a disparu de la feuille"
    corps = regle.group(1)
    assert "white-space: nowrap" in corps, (
        "le code de récupération doit tenir sur une ligne, sans exception"
    )
    assert "break-all" not in corps


# --------------------------------------------------------------------------
# Jetons : le focus et l'erreur ne doivent PAS porter le même signal, et le
# thème clair ne doit pas être livré à moitié.
# --------------------------------------------------------------------------
FEUILLE = (CSS / "auth.css").read_text(encoding="utf-8")


def _bloc_sombre():
    """Le :root de base, hors media query."""
    debut = FEUILLE.index(":root {")
    return FEUILLE[debut:FEUILLE.index("\n}", debut)]


def _bloc_clair():
    """Le bloc complet du thème clair, accolade fermante en colonne 0."""
    debut = FEUILLE.index("@media (prefers-color-scheme: light)")
    return FEUILLE[debut:FEUILLE.index("\n}", debut)]


def _jetons_couleur(bloc):
    """Les seuls jetons dont la valeur est une couleur — les mesures (--gut,
    --col…) n'ont aucune raison d'être redéfinies par un thème."""
    return {
        nom for nom, valeur in re.findall(r"(--[a-z0-9-]+)\s*:\s*([^;]+);", bloc)
        if valeur.strip().startswith("#")
    }


def _valeur(bloc, jeton):
    trouve = re.search(rf"{jeton}\s*:\s*([^;]+);", bloc)
    assert trouve, f"{jeton} n'est pas défini dans ce bloc"
    return trouve.group(1).strip().lower()


def test_le_theme_clair_redefinit_toutes_les_couleurs_du_sombre():
    """Un thème à moitié fait est le mode de panne le plus probable : un jeton
    oublié laisse un aplat sombre au milieu d'une page claire, sans un bruit."""
    manquants = _jetons_couleur(_bloc_sombre()) - _jetons_couleur(_bloc_clair())
    assert not manquants, f"jetons non redéfinis en thème clair : {sorted(manquants)}"


@pytest.mark.parametrize("nom", ["sombre", "clair"])
def test_le_focus_ne_porte_ni_la_couleur_de_l_erreur_ni_celle_de_l_accent(nom):
    """Le défaut corrigé ici : l'accent était rouge, donc un champ en autofocus
    annonçait une erreur inexistante. Sans cette garde, un futur ajustement de
    palette les rapprocherait de nouveau en silence."""
    bloc = _bloc_sombre() if nom == "sombre" else _bloc_clair()
    focus = _valeur(bloc, "--focus")
    assert focus != _valeur(bloc, "--error")
    assert focus != _valeur(bloc, "--accent")


def test_la_feuille_n_accentue_plus_le_champ_au_focus():
    """Garde de mise en œuvre : le focus doit passer par --focus, pas --accent."""
    assert "input:focus { border-color: var(--focus)" in FEUILLE


# --------------------------------------------------------------------------
# Composition : les témoins d'état forment UNE plaque, et rien n'est dupliqué.
# --------------------------------------------------------------------------
TEMOINS = ("auth-led", "auth-state", "auth-ver", "auth-clock")


def test_la_plaque_regroupe_les_quatre_temoins_dans_le_pied(etats):
    """Voyant, état, version et horloge forment UNE plaque d'appareil. Groupés
    dans le pied, ils tiennent dans la même zone de grille aux deux mises en
    page — c'est ce qui évite de les dupliquer pour le flanc d'identité."""
    for nom, html in etats.items():
        pied = html[html.index('<footer class="auth-foot"'):html.index("</footer>")]
        for identifiant in TEMOINS:
            assert f'id="{identifiant}"' in pied, f"{identifiant} hors du pied sur {nom}"


def test_aucun_identifiant_de_temoin_n_est_duplique(etats):
    """Un doublon rendrait le pilotage par auth.js silencieusement partiel :
    getElementById ne rend que le premier."""
    for nom, html in etats.items():
        for identifiant in TEMOINS:
            assert html.count(f'id="{identifiant}"') == 1, f"{identifiant} en double sur {nom}"


def test_l_attribut_de_theme_mort_a_disparu(etats):
    """data-theme="night" n'était lu par aucune règle de la feuille, et il
    contredit désormais le thème clair automatique."""
    for nom, html in etats.items():
        assert 'data-theme="night"' not in html, f"attribut mort encore présent sur {nom}"


def test_la_feuille_compose_deux_flancs_au_dela_de_900px():
    assert "@media (min-width: 900px)" in FEUILLE
    assert "grid-template-areas" in FEUILLE


def test_le_logo_client_garde_un_fond_sombre_dans_les_deux_themes():
    """Les logos clients sont presque toujours des PNG BLANCS, dessinés pour un
    fond sombre. Sans plaque, le thème clair les rend invisibles — et c'est un
    défaut qui n'apparaît QUE chez un client ayant téléversé son logo, jamais
    en développement. Le jeton vaut donc la même valeur dans les deux thèmes."""
    assert "background: var(--plaque);" in FEUILLE
    assert _valeur(_bloc_sombre(), "--plaque") == _valeur(_bloc_clair(), "--plaque")


def test_les_cibles_tactiles_atteignent_44px_au_pointeur_grossier():
    """Champ à 38 px et bouton à 34 px : sous la barre des 44 px, sur une page
    ouverte au téléphone. C'est le POINTEUR qui décide, pas la largeur — une
    fenêtre étroite pilotée à la souris garde la densité du bureau."""
    assert "@media (pointer: coarse)" in FEUILLE
    debut = FEUILLE.index("@media (pointer: coarse)")
    bloc = FEUILLE[debut:FEUILLE.index("\n}", debut)]
    hauteurs = [int(v) for v in re.findall(r"height:\s*(\d+)px", bloc)]
    assert hauteurs, "le bloc tactile ne fixe aucune hauteur"
    assert min(hauteurs) >= 44, f"cible sous 44 px : {min(hauteurs)}px"
