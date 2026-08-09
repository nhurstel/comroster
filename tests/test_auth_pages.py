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
