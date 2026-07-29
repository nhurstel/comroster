"""Journal d'événements : le service (borné, fail-safe) et son exposition API."""
import os

import pytest

from comroster.services.journal import Journal

# ---------- Service ----------

def test_record_et_entries_plus_recent_d_abord(tmp_path):
    j = Journal(str(tmp_path))
    j.record("publish", "6 groupes · 18 beltpacks")
    j.record("reboot")
    entries = j.entries()
    assert [e["event"] for e in entries] == ["reboot", "publish"]
    assert entries[1]["detail"] == "6 groupes · 18 beltpacks"
    assert entries[0]["ts"].endswith("Z")


def test_journal_borne_a_max_events(tmp_path):
    j = Journal(str(tmp_path))
    for i in range(Journal.MAX_EVENTS + 25):
        j.record("publish", str(i))
    entries = j.entries()
    assert len(entries) == Journal.MAX_EVENTS
    # Ce sont bien les PLUS RÉCENTS qui survivent à la troncature.
    assert entries[0]["detail"] == str(Journal.MAX_EVENTS + 24)


def test_ligne_corrompue_ignoree_sans_erreur(tmp_path):
    j = Journal(str(tmp_path))
    j.record("publish")
    with open(j.path, "a", encoding="utf-8") as f:
        f.write("{pas du json\n")
    j.record("reboot")   # l'append relit le fichier : ne doit pas lever
    assert [e["event"] for e in j.entries()] == ["reboot", "publish"]


def test_journal_absent_donne_liste_vide(tmp_path):
    assert Journal(str(tmp_path)).entries() == []


def test_ecriture_impossible_ne_leve_pas(tmp_path):
    """Carte SD passée en lecture seule, disque plein… : `record()` est désormais
    appelé au démarrage de l'application (événement `startup`, comroster/__init__.py) —
    une exception ici empêcherait le boîtier de démarrer, bien pire que perdre une
    ligne de journal.

    `chmod` ne protège rien pour root (les permissions Unix ne s'appliquent pas à
    lui) : dans ce cas on simule l'échec autrement, avec un répertoire jamais créé
    plutôt qu'avec des droits retirés."""
    root = os.geteuid() == 0
    if root:
        dossier = str(tmp_path / "inexistant" / "profond")   # jamais créé : l'ouverture échoue
    else:
        dossier = str(tmp_path)
        os.chmod(dossier, 0o500)                              # lecture seule : écriture refusée

    j = Journal(dossier)
    try:
        entry = j.record("startup", "v1.4.0+7")
    finally:
        if not root:
            os.chmod(dossier, 0o700)      # restaure les droits : le nettoyage de tmp_path en dépend

    # L'appelant reçoit toujours l'entrée construite, même si elle n'a pas pu être
    # persistée : Lifetime._write suit le même contrat côté carnet de bord.
    assert entry["event"] == "startup"
    assert entry["detail"] == "v1.4.0+7"


def test_create_app_demarre_meme_si_le_journal_ne_peut_pas_ecrire(tmp_path):
    """La garantie qui compte vraiment : le boîtier DÉMARRE quoi qu'il arrive, même si
    l'écriture de l'événement `startup` échoue. Le test précédent isole le service ;
    celui-ci prouve la chaîne complète — c'est `create_app()` que le brief a rendu
    vulnérable, pas seulement `Journal.record()`.

    Un `DATA_DIR` entièrement en lecture seule casserait aussi `History`, qui crée son
    propre sous-répertoire au démarrage (constaté à l'essai : `chmod 0o500` sur tout
    `DATA_DIR` fait échouer `History.__init__`, avant même d'atteindre le journal — un
    défaut différent, hors du périmètre de cette tâche). Pour isoler UNIQUEMENT
    l'écriture du journal, un DOSSIER posé exactement là où `Journal.record()` attend
    d'ouvrir son fichier temporaire fait échouer `open(..., "w")` avec
    `IsADirectoryError` — quels que soient les droits, y compris pour root, qu'aucun
    `chmod` n'aurait arrêté. Le reste de `DATA_DIR` reste pleinement inscriptible :
    c'est bien l'écriture du journal, et elle seule, qui est mise en défaut ici."""
    from comroster import create_app

    (tmp_path / "journal.jsonl.tmp").mkdir()

    app = create_app({"TESTING": True, "DATA_DIR": str(tmp_path), "SECRET_KEY": "test-secret"})
    assert app is not None


# ---------- API ----------

@pytest.fixture
def auth_client(client):
    client.post("/admin/setup", data={"password": "motdepasse8"})
    return client


def test_api_journal_requiert_session(client):
    r = client.get("/api/journal")
    assert r.status_code in (302, 401, 403)


def test_publish_ecrit_un_evenement_au_journal(auth_client):
    auth_client.post("/api/groups", json={"name": "Régie"})
    assert auth_client.post("/api/publish").status_code == 200
    entries = auth_client.get("/api/journal").get_json()
    assert entries[0]["event"] == "publish"
    # Le détail accorde le pluriel : « 1 groupes » dans une conduite de régie fait
    # négligé, et c'est le cas le plus fréquent au démarrage d'une production.
    assert entries[0]["detail"] == "1 groupe · 0 beltpack"

    auth_client.post("/api/groups", json={"name": "Plateau"})
    assert auth_client.post("/api/publish").status_code == 200
    assert auth_client.get("/api/journal").get_json()[0]["detail"] == "2 groupes · 0 beltpack"


def test_reboot_simule_journalise(auth_client):
    assert auth_client.post("/api/reboot").get_json()["ok"] is True
    events = [e["event"] for e in auth_client.get("/api/journal").get_json()]
    assert "reboot" in events


# ---------- Page Journal + logs techniques ----------

def test_journal_page_requiert_session(client):
    r = client.get("/admin/journal")
    assert r.status_code in (302, 401, 403)


def test_journal_page_rendue(auth_client):
    html = auth_client.get("/admin/journal").get_data(as_text=True)
    assert "journal.js" in html
    assert "Technique" in html          # volet logs présent


def test_api_logs_requiert_session(client):
    assert client.get("/api/logs").status_code in (302, 401, 403)


def test_api_logs_capte_un_warning(app, auth_client):
    app.logger.warning("sentinelle-logbuffer %s", 42)
    entries = auth_client.get("/api/logs").get_json()
    assert any("sentinelle-logbuffer 42" in e["message"] for e in entries)
    assert entries[0]["level"] in ("INFO", "WARNING", "ERROR")


def test_logbuffer_ecarte_les_acces_http_mais_garde_leurs_erreurs():
    """Le tampon sert à diagnostiquer le boîtier, pas à compter les requêtes.

    Un seul chargement de page produit des dizaines de lignes d'accès (fichiers
    statiques compris) : gardées, elles chassaient du tampon les lignes utiles. Une
    vraie erreur du serveur HTTP, elle, doit rester lisible sans SSH.
    """
    import logging

    from comroster.services.logbuffer import LogBuffer
    buf = LogBuffer()
    access = logging.getLogger("werkzeug")
    access.addHandler(buf)
    access.setLevel(logging.INFO)
    access.info('127.0.0.1 - - "GET /static/css/admin.css HTTP/1.1" 200 -')
    access.error("Error on request: connexion perdue")
    access.removeHandler(buf)

    messages = [e["message"] for e in buf.entries()]
    assert not any("GET /static" in m for m in messages)      # le bruit est écarté
    assert any("connexion perdue" in m for m in messages)     # l'erreur, jamais


def test_logbuffer_borne_et_ordre(tmp_path):
    import logging

    from comroster.services.logbuffer import LogBuffer
    buf = LogBuffer()
    logger = logging.getLogger("test-borne")
    logger.addHandler(buf)
    logger.setLevel(logging.INFO)
    for i in range(LogBuffer.CAPACITY + 30):
        logger.info("msg %d", i)
    logger.removeHandler(buf)
    entries = buf.entries()
    assert len(entries) == LogBuffer.CAPACITY
    assert entries[0]["message"] == f"msg {LogBuffer.CAPACITY + 29}"   # plus récent d'abord
