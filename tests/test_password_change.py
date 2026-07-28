"""Rotation du mot de passe admin, sans brûler le code de récupération.

Avant, seul `recover` changeait le mot de passe — et il CONSOMME le code. Un boîtier
prêté d'une production à l'autre n'avait donc aucun moyen de rotation (audit 2026-07-28).
"""
import json

from comroster.auth import MIN_PASSWORD_LENGTH
from comroster.services.secret import SecretStore


def _recovery_hash(app):
    with open(app.extensions["secret"].secret_path, encoding="utf-8") as fh:
        return json.load(fh)["recovery_hash"]


def test_le_service_change_le_mot_de_passe(tmp_path):
    store = SecretStore(str(tmp_path))
    store.setup("ancien")
    store.change_password("ancien", "nouveau")
    assert store.verify_password("nouveau")
    assert not store.verify_password("ancien")


def test_le_service_refuse_sans_le_mot_de_passe_actuel(tmp_path):
    store = SecretStore(str(tmp_path))
    store.setup("ancien")
    try:
        store.change_password("pas-le-bon", "nouveau")
        raise AssertionError("un mot de passe actuel faux doit être refusé")
    except ValueError:
        pass
    assert store.verify_password("ancien"), "l'ancien doit rester valable après un refus"


def test_le_code_de_recuperation_survit_au_changement(app, auth_client):
    """C'est TOUTE la différence avec `recover` : le code ne doit pas être consommé."""
    avant = _recovery_hash(app)
    r = auth_client.post("/admin/password",
                         json={"current": "motdepasse8", "new": "nouveau-mdp"})
    assert r.status_code == 200, r.get_json()
    assert _recovery_hash(app) == avant, (
        "changer le mot de passe a régénéré le code de récupération — "
        "l'équipe devrait le rediffuser à chaque rotation"
    )


def test_la_session_reste_ouverte_et_le_nouveau_mdp_fonctionne(app, auth_client):
    auth_client.post("/admin/password", json={"current": "motdepasse8", "new": "nouveau-mdp"})
    assert auth_client.get("/api/state").status_code == 200, "la session ne doit pas sauter"
    auth_client.post("/admin/logout")
    assert auth_client.post("/admin/login", data={"password": "motdepasse8"}).status_code == 401
    assert auth_client.post("/admin/login", data={"password": "nouveau-mdp"}).status_code == 302


def test_mauvais_mot_de_passe_actuel_403(auth_client):
    r = auth_client.post("/admin/password", json={"current": "faux", "new": "nouveau-mdp"})
    assert r.status_code == 403
    assert "actuel" in r.get_json()["error"].lower()


def test_la_longueur_minimale_vaut_aussi_ici(auth_client):
    """Leçon 2026-07-06 : une politique s'applique sur TOUS les chemins d'écriture."""
    court = "a" * (MIN_PASSWORD_LENGTH - 1)
    r = auth_client.post("/admin/password", json={"current": "motdepasse8", "new": court})
    assert r.status_code == 400
    assert str(MIN_PASSWORD_LENGTH) in r.get_json()["error"]


def test_un_mot_de_passe_identique_est_refuse(auth_client):
    r = auth_client.post("/admin/password",
                         json={"current": "motdepasse8", "new": "motdepasse8"})
    assert r.status_code == 400


def test_la_route_exige_une_session(client):
    client.post("/admin/setup", data={"password": "motdepasse8"})
    client.post("/admin/logout")
    r = client.post("/admin/password", json={"current": "motdepasse8", "new": "autre-mdp"})
    assert r.status_code in (401, 302)


def test_le_changement_est_journalise(app, auth_client):
    auth_client.post("/admin/password", json={"current": "motdepasse8", "new": "nouveau-mdp"})
    events = [e["event"] for e in app.extensions["journal"].entries()]
    assert "password_change" in events
