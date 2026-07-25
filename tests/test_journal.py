"""Journal d'événements : le service (borné, fail-safe) et son exposition API."""
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
    assert "1 groupes" in entries[0]["detail"]


def test_reboot_simule_journalise(auth_client):
    assert auth_client.post("/api/reboot").get_json()["ok"] is True
    events = [e["event"] for e in auth_client.get("/api/journal").get_json()]
    assert "reboot" in events
