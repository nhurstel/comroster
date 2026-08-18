"""Points de repère nommés et épinglés dans l'historique (ajout n°3, audit 2026-07-28).

Une production ne pense pas ses publications en horodatages mais en « Filage »,
« Générale », « Première ». Et le repère qui compte doit survivre à trente jours de
filages, donc échapper à la purge.
"""
import datetime
import os

import pytest

from comroster.services.history import History


@pytest.fixture
def history(app):
    return app.extensions["history"]


def _vieillir(history, ts, jours):
    """Ré-horodate un instantané dans le passé, nom de fichier compris."""
    ancien = os.path.join(history.dir, f"{ts}.json")
    vieux_dt = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=jours)
    neuf_ts = vieux_dt.strftime("%Y%m%dT%H%M%S%fZ")
    os.rename(ancien, os.path.join(history.dir, f"{neuf_ts}.json"))
    index = history._index()
    if ts in index:
        index[neuf_ts] = index.pop(ts)
        history._save_index(index)
    return neuf_ts


def test_publier_sans_repere_reste_la_norme(auth_client, history):
    """Publier ne doit pas devenir une formalité : le corps est facultatif."""
    auth_client.post("/api/people", json={"role": "HF", "beltpack": "12"})
    assert auth_client.post("/api/publish").status_code == 200
    item = history.list()[0]
    assert item["label"] == "" and item["pinned"] is False


def test_publier_avec_un_nom(auth_client, history):
    auth_client.post("/api/people", json={"role": "HF", "beltpack": "12"})
    r = auth_client.post("/api/publish", json={"label": "Générale", "pinned": True})
    assert r.status_code == 200 and r.get_json()["label"] == "Générale"
    item = history.list()[0]
    assert item["label"] == "Générale" and item["pinned"] is True


def test_nommer_apres_coup(auth_client, history):
    """Le cas le plus fréquent : on ne sait pas en publiant que ce sera « la bonne »."""
    auth_client.post("/api/people", json={"role": "HF", "beltpack": "12"})
    auth_client.post("/api/publish")
    ts = history.list()[0]["timestamp"]
    r = auth_client.post(f"/api/history/{ts}/label", json={"label": "Première", "pinned": True})
    assert r.status_code == 200
    item = history.list()[0]
    assert item["label"] == "Première" and item["pinned"] is True


def test_un_instantane_epingle_survit_a_la_purge_par_age(auth_client, history):
    auth_client.post("/api/people", json={"role": "HF", "beltpack": "12"})
    auth_client.post("/api/publish", json={"label": "Première", "pinned": True})
    garde = _vieillir(history, history.list()[0]["timestamp"], 90)

    auth_client.post("/api/publish")          # déclenche _prune()
    restants = [i["timestamp"] for i in history.list()]
    assert garde in restants, "un repère épinglé ne doit jamais être purgé par l'âge"


def test_un_instantane_ordinaire_est_bien_purge_par_age(auth_client, history):
    """Assertion miroir : sans l'épingle, la purge doit mordre — sinon le test
    précédent ne prouverait rien."""
    auth_client.post("/api/people", json={"role": "HF", "beltpack": "12"})
    auth_client.post("/api/publish")
    vieux = _vieillir(history, history.list()[0]["timestamp"], 90)

    auth_client.post("/api/publish")
    assert vieux not in [i["timestamp"] for i in history.list()]


def test_un_instantane_epingle_survit_au_plafond_de_nombre(app, history):
    """MAX_SNAPSHOTS coupe les plus vieux : l'épinglé doit passer au travers."""
    history.MAX_SNAPSHOTS = 3
    try:
        premier = history.archive({"version": 1, "n": 0}, label="Première", pinned=True)
        for n in range(1, 8):
            history.archive({"version": 1, "n": n})
        assert premier in [i["timestamp"] for i in history.list()]
    finally:
        history.MAX_SNAPSHOTS = History.MAX_SNAPSHOTS


def test_vider_l_historique_conserve_les_reperes(auth_client, history):
    """Les avoir mis à l'abri de la purge et les perdre au premier « vider » serait
    incohérent."""
    auth_client.post("/api/people", json={"role": "HF", "beltpack": "12"})
    auth_client.post("/api/publish", json={"label": "Générale", "pinned": True})
    auth_client.post("/api/publish")
    auth_client.post("/api/publish")

    r = auth_client.post("/api/history/clear")
    assert r.status_code == 200
    restants = history.list()
    assert len(restants) == 1 and restants[0]["label"] == "Générale"


def test_le_plafond_d_epingles_est_annonce_clairement(app, history):
    history.MAX_PINNED = 2
    try:
        for n in range(2):
            history.archive({"version": 1, "n": n}, label=f"R{n}", pinned=True)
        ts = history.archive({"version": 1, "n": 99})
        with pytest.raises(ValueError, match="maximum"):
            history.annotate(ts, pinned=True)
    finally:
        history.MAX_PINNED = History.MAX_PINNED


def test_le_plafond_d_epingles_remonte_en_409(auth_client, app, history):
    history.MAX_PINNED = 1
    try:
        auth_client.post("/api/people", json={"role": "HF", "beltpack": "12"})
        auth_client.post("/api/publish", json={"label": "Un", "pinned": True})
        auth_client.post("/api/publish")
        ts = history.list()[0]["timestamp"]
        r = auth_client.post(f"/api/history/{ts}/label", json={"pinned": True})
        assert r.status_code == 409 and r.get_json()["code"] == "pinned_full"
    finally:
        history.MAX_PINNED = History.MAX_PINNED


def test_detacher_puis_repurger(auth_client, history):
    auth_client.post("/api/people", json={"role": "HF", "beltpack": "12"})
    auth_client.post("/api/publish", json={"label": "Générale", "pinned": True})
    ts = _vieillir(history, history.list()[0]["timestamp"], 90)
    auth_client.post(f"/api/history/{ts}/label", json={"pinned": False})
    auth_client.post("/api/publish")
    assert ts not in [i["timestamp"] for i in history.list()]


def test_un_horodatage_inconnu_donne_404(auth_client):
    r = auth_client.post("/api/history/20200101T000000000000Z/label", json={"label": "x"})
    assert r.status_code == 404


def test_un_horodatage_malforme_ne_touche_pas_au_disque(auth_client):
    """Même garde que la restauration : le format sert de filtre anti-traversée."""
    assert auth_client.post("/api/history/..%2F..%2Fetc/label", json={"label": "x"}).status_code == 404


def test_index_json_n_est_pas_pris_pour_un_instantane(auth_client, history):
    auth_client.post("/api/people", json={"role": "HF", "beltpack": "12"})
    auth_client.post("/api/publish", json={"label": "Générale", "pinned": True})
    assert os.path.exists(history.index_path)
    assert all(i["timestamp"] != "index" for i in history.list())
    assert len(history.list()) == 1


def test_le_nom_est_borne_en_longueur(history):
    ts = history.archive({"version": 1}, label="x" * 500)
    assert len(history.list()[0]["label"]) <= History.LABEL_MAX
    history.annotate(ts, label="y" * 500)
    assert len(history.list()[0]["label"]) <= History.LABEL_MAX


def test_l_auto_sync_ne_pose_jamais_de_repere(app):
    """Un repère est une intention d'opérateur, pas un effet de bord du réseau."""
    from comroster.services.publisher import broadcast_published
    broadcast_published(app, {"version": 1, "groups": [], "people": []})
    assert app.extensions["history"].list()[0]["label"] == ""
    assert app.extensions["history"].list()[0]["pinned"] is False
