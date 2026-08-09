"""Sauvegarde et restauration complètes du boîtier.

L'export `.rost` ne couvrait que le roster : un boîtier mort emportait le réseau, les
identifiants de l'antenne, les configurations nommées et le mot de passe. Ce lot en fait
une archive unique, réinjectable sur un boîtier neuf (ajout n°1 de l'audit 2026-07-28).

Deux invariants gardés ici : l'archive est TOUJOURS chiffrée (elle porte le PSK Wi-Fi en
clair), et elle ne transporte PAS l'identité du boîtier physique (carnet de bord).
"""
import base64
import json

import pytest

from comroster.services import backup

PASS = "phrase-de-passe"

#: Nom de groupe VOLONTAIREMENT long. Ce test cherche les secrets en clair dans une
#: archive encodée en base64 : un marqueur court s'y retrouve par HASARD. « Son » (trois
#: caractères) apparaissait dans ~0,4 % des archives — mesuré, pas supposé — ce qui a fait
#: tomber la CI en affirmant que le chiffrement fuyait. Voir `_MARQUEUR_MINI`.
GROUPE = "Son-Retours-Loges"

#: Longueur en dessous de laquelle un marqueur n'est plus une preuve. Dans un alphabet
#: base64 (64 signes), la probabilité qu'une suite de n signes apparaisse par hasard dans
#: une archive de L caractères vaut ~L/64^n : négligeable dès 8 signes, sensible à 3.
_MARQUEUR_MINI = 8


def _b64(blob):
    return base64.b64encode(blob).decode()


@pytest.fixture
def garni(auth_client, app):
    """Un boîtier avec du contenu partout : roster, réseau, config nommée, antenne."""
    auth_client.post("/api/groups", json={"name": GROUPE, "color": "#3FA6B0"})
    auth_client.post("/api/people", json={"role": "HF", "beltpack": "12"})
    auth_client.post("/api/publish")
    auth_client.put("/api/network", json={"link": "ethernet", "mode": "static",
                                          "address": "192.168.1.50", "prefix": 24})
    auth_client.post("/api/configs", json={"name": "Jour 2"})
    client = app.extensions["antenna"]
    client._ip = "192.168.1.11"
    client._password = "secret-antenne"
    client._persist()
    return auth_client


# ---------- Le format lui-même ----------

def test_l_archive_est_chiffree(app, garni):
    """Elle porte le PSK Wi-Fi et l'empreinte du mot de passe : jamais en clair."""
    blob = backup.encrypt(backup.build_payload(app), PASS)
    enveloppe = json.loads(blob.decode())
    assert enveloppe["format"] == "comroster-backup"
    assert "salt" in enveloppe and enveloppe["kdf"]["iterations"] >= 100_000
    # Aucune donnée exploitable ne doit apparaître dans l'enveloppe.
    secrets = ("192.168.1.50", "secret-antenne", GROUPE)
    # Garde du test LUI-MÊME : un marqueur trop court se retrouve par hasard dans du
    # base64 et fait échouer la CI en accusant le chiffrement. Cette assertion empêche
    # d'en réintroduire un sans s'en apercevoir.
    for secret in secrets:
        assert len(secret) >= _MARQUEUR_MINI, (
            f"« {secret} » est trop court pour prouver quoi que ce soit : il peut "
            f"apparaître par hasard dans une archive base64"
        )
    for secret in secrets:
        assert secret not in blob.decode(), f"« {secret} » lisible dans l'archive"


def test_aller_retour_complet(app, garni):
    charge = backup.build_payload(app)
    assert backup.decrypt(backup.encrypt(charge, PASS), PASS) == charge


def test_une_phrase_de_passe_trop_courte_est_refusee(app):
    with pytest.raises(backup.BackupError, match="caractères minimum"):
        backup.encrypt({"draft": {}}, "court")


def test_mauvaise_phrase_de_passe_dit_laquelle_des_causes(app, garni):
    blob = backup.encrypt(backup.build_payload(app), PASS)
    with pytest.raises(backup.BackupError, match=r"[Pp]hrase de passe incorrecte"):
        backup.decrypt(blob, "pas-la-bonne")


def test_un_fichier_quelconque_est_refuse_clairement(app):
    with pytest.raises(backup.BackupError, match="n'est pas une sauvegarde"):
        backup.decrypt(b'{"hello": 1}', PASS)


def test_une_version_inconnue_est_refusee_au_lieu_d_etre_appliquee_au_mieux(app, garni):
    blob = backup.encrypt(backup.build_payload(app), PASS)
    enveloppe = json.loads(blob.decode())
    enveloppe["version"] = 99
    with pytest.raises(backup.BackupError, match="version"):
        backup.decrypt(json.dumps(enveloppe).encode(), PASS)


# ---------- Ce que l'archive contient, et ce qu'elle ne contient PAS ----------

def test_l_archive_porte_tout_ce_qu_il_faut_pour_repartir(app, garni):
    p = backup.build_payload(app)
    assert p["draft"]["groups"], "le roster"
    assert p["published"], "l'état publié"
    assert p["network"]["address"] == "192.168.1.50", "le réseau"
    assert p["admin_secret"]["password_hash"], "le mot de passe"
    assert p["antenna"]["ip"] == "192.168.1.11", "l'antenne"
    assert p["antenna"]["password"] == "secret-antenne"
    # Assertion FERME. Elle était écrite « si la clé existe » — donc vraie même quand la
    # clé manquait, ce qui était précisément le cas : `build_payload` collectait les
    # configurations nommées sans jamais les renvoyer. Une assertion conditionnelle ne
    # prouve rien (leçon 2026-07-23).
    assert p["configs"], "les configurations nommées doivent être dans l'archive"
    assert any(c.get("name") == "Jour 2" for c in p["configs"].values())


def test_le_carnet_de_bord_n_est_jamais_sauvegarde(app, garni):
    """Un boîtier neuf ne doit pas revendiquer les heures de vol du boîtier mort."""
    assert "lifetime" not in backup.build_payload(app)


def test_l_identifiant_antenne_est_rescelle_a_la_restauration(app, garni, tmp_path):
    """Au repos les identifiants sont chiffrés par la clé de session ; l'archive les
    transporte en clair (elle est elle-même chiffrée), ils doivent être re-scellés."""
    charge = backup.build_payload(app)
    app.extensions["antenna"].disconnect()
    backup.apply_payload(app, charge)
    with open(app.extensions["antenna"].path, encoding="utf-8") as fh:
        sur_disque = fh.read()
    assert "secret-antenne" not in sur_disque, "mot de passe antenne en clair sur disque"
    assert app.extensions["antenna"].ip == "192.168.1.11"


def test_un_nom_de_configuration_piege_n_ecrit_pas_hors_du_repertoire(app, auth_client):
    """Le nom vient de l'archive : jamais un chemin."""
    backup.apply_payload(app, {"configs": {"../../evasion.json": {"name": "x"}}})
    import os
    assert not os.path.exists(os.path.join(app.config["DATA_DIR"], "..", "..", "evasion.json"))


# ---------- Les routes ----------

def test_cycle_complet_par_l_api(app, garni, tmp_path):
    r = garni.post("/api/backup", json={"passphrase": PASS})
    assert r.status_code == 200
    archive = r.get_json()
    assert archive["filename"].endswith(".rostbak")

    # On casse tout, comme un boîtier neuf.
    app.extensions["storage"].save_draft({"version": 1, "groups": [], "people": [],
                                          "beltpack_roles": {}, "updated_at": "2020-01-01T00:00:00Z"})
    assert garni.get("/api/state").get_json()["groups"] == []

    r = garni.post("/api/backup/restore",
                   json={"passphrase": PASS, "content": archive["content"]})
    assert r.status_code == 200, r.get_json()
    assert "brouillon" in r.get_json()["restored"]
    assert garni.get("/api/state").get_json()["groups"][0]["name"] == GROUPE
    assert garni.get("/api/network").get_json()["address"] == "192.168.1.50"


def test_l_inspection_annonce_le_contenu_avant_d_ecraser(garni):
    archive = garni.post("/api/backup", json={"passphrase": PASS}).get_json()
    r = garni.post("/api/backup/inspect",
                   json={"passphrase": PASS, "content": archive["content"]})
    assert r.status_code == 200
    resume = r.get_json()
    assert resume["groups"] == 1 and resume["people"] == 1
    assert resume["has_network"] and resume["has_antenna"] and resume["has_password"]


def test_l_inspection_n_ecrit_rien(app, garni):
    """Sinon « regarder » vaudrait « appliquer »."""
    archive = garni.post("/api/backup", json={"passphrase": PASS}).get_json()
    avant = garni.get("/api/state").get_json()
    garni.post("/api/backup/restore", json={"passphrase": "faux", "content": archive["content"]})
    garni.post("/api/backup/inspect", json={"passphrase": PASS, "content": archive["content"]})
    assert garni.get("/api/state").get_json() == avant


def test_mauvaise_phrase_de_passe_400_et_rien_ne_bouge(app, garni):
    archive = garni.post("/api/backup", json={"passphrase": PASS}).get_json()
    avant = garni.get("/api/state").get_json()
    r = garni.post("/api/backup/restore",
                   json={"passphrase": "pas-la-bonne", "content": archive["content"]})
    assert r.status_code == 400
    assert "hrase de passe" in r.get_json()["error"]
    assert garni.get("/api/state").get_json() == avant


def test_contenu_non_base64_400(garni):
    r = garni.post("/api/backup/restore", json={"passphrase": PASS, "content": "pas du base64 !!"})
    assert r.status_code == 400


def test_les_routes_exigent_une_session(client):
    client.post("/admin/setup", data={"password": "motdepasse8"})
    client.post("/admin/logout")
    for route in ("/api/backup", "/api/backup/inspect", "/api/backup/restore"):
        assert client.post(route, json={"passphrase": PASS}).status_code in (401, 302)


def test_la_restauration_est_journalisee(app, garni):
    archive = garni.post("/api/backup", json={"passphrase": PASS}).get_json()
    garni.post("/api/backup/restore", json={"passphrase": PASS, "content": archive["content"]})
    events = [e["event"] for e in app.extensions["journal"].entries()]
    # `backup_create` est journalisé APRÈS la lecture du journal qui part dans l'archive :
    # il ne s'y trouve donc pas, mais la fusion doit le préserver côté boîtier.
    assert "backup_restore" in events and "backup_create" in events


def test_le_mot_de_passe_restaure_est_signale(app, garni):
    archive = garni.post("/api/backup", json={"passphrase": PASS}).get_json()
    r = garni.post("/api/backup/restore", json={"passphrase": PASS, "content": archive["content"]})
    assert r.get_json()["password_changed"] is True


def test_une_archive_partielle_n_efface_pas_ce_qui_n_y_est_pas(app, garni):
    """Restaurer une archive faite avant la config réseau ne doit pas l'effacer."""
    charge = backup.build_payload(app)
    charge["network"] = None
    backup.apply_payload(app, charge)
    assert garni.get("/api/network").get_json()["address"] == "192.168.1.50"


def test_la_restauration_fusionne_le_journal_au_lieu_de_l_ecraser(app, garni):
    """Un journal répond à « que s'est-il passé ? » : le remplacer efface des preuves,
    à commencer par celles de la restauration en cours."""
    archive = garni.post("/api/backup", json={"passphrase": PASS}).get_json()
    # Un évènement postérieur à l'archive : il ne doit pas disparaître.
    app.extensions["journal"].record("evenement_posterieur", "à conserver")
    garni.post("/api/backup/restore", json={"passphrase": PASS, "content": archive["content"]})

    events = [e["event"] for e in app.extensions["journal"].entries()]
    assert "evenement_posterieur" in events, "la restauration a effacé le journal local"
    assert "publish" in events, "les évènements de l'archive doivent être repris"
    assert "backup_restore" in events


def test_la_fusion_ne_recopie_pas_les_evenements_de_l_archive(app, garni):
    """Restaurer deux fois ne doit pas empiler deux fois le passé de l'archive.

    Portée précise : c'est la FUSION qui dédoublonne. Deux restaurations réelles restent,
    elles, deux évènements distincts — même si elles tombent dans la même seconde avec le
    même détail. Les confondre ferait disparaître une action de l'opérateur.
    """
    archive = garni.post("/api/backup", json={"passphrase": PASS}).get_json()
    garni.post("/api/backup/restore", json={"passphrase": PASS, "content": archive["content"]})
    garni.post("/api/backup/restore", json={"passphrase": PASS, "content": archive["content"]})

    events = [e["event"] for e in app.extensions["journal"].entries()]
    assert events.count("publish") == 1, "l'évènement de l'archive a été recopié"
    assert events.count("network_save") == 1
    assert events.count("backup_restore") == 2, "deux restaurations = deux évènements"


def test_les_configurations_nommees_font_l_aller_retour(app, garni):
    """Régression : elles étaient collectées mais jamais placées dans l'archive — donc
    perdues, sans que rien ne le signale."""
    charge = backup.build_payload(app)
    assert charge["configs"], "collectées mais absentes de la charge"

    # On efface les configurations du boîtier, puis on restaure.
    import os
    for f in os.listdir(app.extensions["configs"].dir):
        os.unlink(os.path.join(app.extensions["configs"].dir, f))
    assert garni.get("/api/configs").get_json() == []

    backup.apply_payload(app, charge)
    noms = [c["name"] for c in garni.get("/api/configs").get_json()]
    assert "Jour 2" in noms


def test_le_resume_annonce_le_nombre_de_configurations(garni):
    archive = garni.post("/api/backup", json={"passphrase": PASS}).get_json()
    resume = garni.post("/api/backup/inspect",
                        json={"passphrase": PASS, "content": archive["content"]}).get_json()
    assert resume["configs"] == 1
