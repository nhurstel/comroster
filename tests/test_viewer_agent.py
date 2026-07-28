import json
import threading
import urllib.error
import urllib.parse
import urllib.request

import pytest

from comroster.services.viewer_auth import ViewerAuth
from comroster.viewer_agent import build_server

#: Code d'appariement imposé aux tests. En vrai il est tiré au sort au premier démarrage
#: et AFFICHÉ sur l'écran de l'afficheur : le fournir prouve qu'on est dans la salle.
CODE = "TEST42"


@pytest.fixture
def agent(tmp_path):
    srv = build_server(str(tmp_path), port=0, auth=ViewerAuth(str(tmp_path), CODE))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]
    yield f"http://127.0.0.1:{port}", tmp_path
    srv.shutdown()
    srv.server_close()      # ferme le socket d'écoute (shutdown seul le laisse ouvert)


def _get(base, path):
    with urllib.request.urlopen(base + path) as r:
        return r.status, r.read().decode()


def _post(base, path, fields, code=CODE):
    """POST du formulaire. `code=None` omet le code d'appariement."""
    payload = dict(fields)
    if code is not None:
        payload["pairing_code"] = code
    data = urllib.parse.urlencode(payload).encode()
    req = urllib.request.Request(base + path, data=data, method="POST")
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def test_server_status_unreachable_by_default(agent):
    base, _ = agent
    status, body = _get(base, "/api/server-status")
    assert status == 200
    payload = json.loads(body)
    assert payload["reachable"] is False
    assert payload["display_url"] is None


def test_post_config_writes_viewer_and_network(agent):
    base, tmp = agent
    status, body = _post(base, "/config", {
        "server_ip": "192.168.42.10",
        "network_mode": "static",
        "network_address": "192.168.42.50",
        "network_prefix": "24",
    })
    assert status == 200
    assert json.loads(body)["ok"] is True
    with open(tmp / "viewer.json") as fh:
        viewer = json.load(fh)
    assert viewer["server_ip"] == "192.168.42.10"
    with open(tmp / "network.json") as fh:
        net = json.load(fh)
    assert net["mode"] == "static" and net["address"] == "192.168.42.50"


def test_post_config_rejects_bad_server_ip(agent):
    base, _ = agent
    status, body = _post(base, "/config", {"server_ip": "nope", "network_mode": "dhcp"})
    assert status == 400
    assert "error" in json.loads(body)


def test_post_config_rejects_bad_prefix(agent):
    base, _ = agent
    status, _ = _post(base, "/config", {
        "server_ip": "192.168.42.10", "network_mode": "static",
        "network_address": "192.168.42.50", "network_prefix": "abc",
    })
    assert status == 400


def test_post_config_dhcp_no_address(agent):
    base, tmp = agent
    status, _ = _post(base, "/config", {"server_ip": "192.168.42.10", "network_mode": "dhcp"})
    assert status == 200
    with open(tmp / "network.json") as fh:
        assert json.load(fh)["mode"] == "dhcp"


# ---------- Code d'appariement (audit 2026-07-28) ----------

def test_sans_code_rien_n_est_ecrit(agent):
    """Le défaut d'origine : n'importe quoi sur le LAN pouvait repointer l'afficheur."""
    base, tmp = agent
    status, body = _post(base, "/config",
                         {"server_ip": "10.0.0.1", "network_mode": "dhcp"}, code=None)
    assert status == 403
    assert "error" in json.loads(body)
    assert not (tmp / "viewer.json").exists(), "un refus ne doit RIEN écrire"
    assert not (tmp / "network.json").exists()


def test_un_mauvais_code_est_refuse(agent):
    base, tmp = agent
    status, _ = _post(base, "/config",
                      {"server_ip": "10.0.0.1", "network_mode": "dhcp"}, code="ZZZZZZ")
    assert status == 403
    assert not (tmp / "viewer.json").exists()


def test_le_code_tolere_casse_espaces_et_tirets(agent):
    """Il est recopié à la main depuis un écran, souvent de loin."""
    base, tmp = agent
    status, _ = _post(base, "/config", {"server_ip": "192.168.42.10", "network_mode": "dhcp"},
                      code=" te-st 42 ")
    assert status == 200
    assert (tmp / "viewer.json").exists()


def test_le_code_est_affiche_sur_l_ecran_de_l_afficheur(agent):
    """C'est ce qui fait de la présence physique la preuve d'autorisation."""
    base, _ = agent
    _, body = _get(base, "/")
    assert CODE in body


def test_le_code_n_est_pas_affiche_sur_la_page_de_configuration(agent):
    """Sinon la protection ne prouverait plus rien : la page est ouverte à tout le LAN."""
    base, _ = agent
    _, body = _get(base, "/config")
    assert CODE not in body
    assert 'name="pairing_code"' in body


def test_le_code_persiste_entre_deux_demarrages(tmp_path):
    premier = ViewerAuth(str(tmp_path))
    assert premier.code and len(premier.code) == 6
    assert ViewerAuth(str(tmp_path)).code == premier.code, (
        "un code régénéré à chaque redémarrage obligerait à relire l'écran à chaque fois"
    )


def test_un_fichier_de_code_corrompu_repart_sur_un_code_neuf(tmp_path):
    """Fail-safe appliance : jamais d'exception qui empêcherait l'agent de démarrer."""
    (tmp_path / "viewer_agent.json").write_text("{ pas du json", encoding="utf-8")
    auth = ViewerAuth(str(tmp_path))
    assert auth.code and len(auth.code) == 6


def test_un_corps_surdimensionne_est_refuse(agent):
    """Garde-fou mémoire : l'agent tourne sur un Pi."""
    base, _ = agent
    data = urllib.parse.urlencode({"pairing_code": CODE, "server_ip": "1.2.3.4",
                                   "bourrage": "x" * 100_000}).encode()
    req = urllib.request.Request(base + "/config", data=data, method="POST")
    try:
        with urllib.request.urlopen(req) as r:
            status = r.status
    except urllib.error.HTTPError as e:
        status = e.code
    assert status == 413


def test_l_agent_sert_plusieurs_clients_de_front(agent):
    """Un client lent ne doit pas geler la seule page qui permet de reconfigurer."""
    base, _ = agent
    resultats = []

    def interroger():
        try:
            resultats.append(_get(base, "/api/server-status")[0])
        except OSError:
            resultats.append(0)

    fils = [threading.Thread(target=interroger) for _ in range(6)]
    for f in fils:
        f.start()
    for f in fils:
        f.join(timeout=10)
    assert resultats == [200] * 6


def test_boot_page_served(agent):
    base, _ = agent
    status, body = _get(base, "/")
    assert status == 200
    assert "server-status" in body        # le JS interroge l'agent
    assert "Configurer" in body           # bannière de config


def test_config_page_has_fields(agent):
    base, _ = agent
    status, body = _get(base, "/config")
    assert status == 200
    assert 'name="server_ip"' in body
    assert 'name="network_mode"' in body


def test_qr_is_svg(agent):
    base, _ = agent
    status, body = _get(base, "/qr.svg")
    assert status == 200
    assert "<svg" in body


def test_main_callable_exists():
    from comroster import viewer_agent
    assert callable(viewer_agent.main)
