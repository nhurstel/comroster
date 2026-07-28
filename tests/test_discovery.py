"""Découverte des antennes Bolero (ajout n°5, audit 2026-07-28).

Deux exigences tenues ici : la SAISIE MANUELLE reste le chemin de référence (la découverte
ne fait que proposer), et la garde anti-SSRF de `connect` n'est pas contournée — le
balayage n'accepte aucune adresse du client.
"""
import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from comroster.services import discovery

NODE_STATUS = {"nodeStatus": [{"isLocal": True, "name": "Bolero-Régie",
                               "bp": [{"id": 1}, {"id": 2}]}]}


# ---------- Périmètre du balayage (le point sensible) ----------

def test_le_perimetre_exclut_l_adresse_du_boitier_le_reseau_et_la_diffusion():
    hosts = discovery.candidate_hosts("192.168.1.50", 24)
    assert "192.168.1.50" not in hosts, "le boîtier ne se sonde pas lui-même"
    assert "192.168.1.0" not in hosts and "192.168.1.255" not in hosts
    assert len(hosts) == 253
    assert "192.168.1.11" in hosts


def test_une_plage_publique_est_refusee():
    """Un boîtier mal configuré ne doit pas se mettre à balayer Internet depuis la
    régie d'un client."""
    assert discovery.candidate_hosts("8.8.8.8", 24) == []
    assert discovery.candidate_hosts("51.15.0.1", 24) == []


def test_les_plages_privees_et_link_local_sont_acceptees():
    for ip in ("192.168.1.10", "10.0.0.5", "172.16.4.9", "169.254.7.3"):
        assert discovery.candidate_hosts(ip, 24), ip


def test_un_reseau_trop_vaste_est_refuse():
    """Balayer un /16 prendrait des minutes : la saisie manuelle reprend la main."""
    assert discovery.candidate_hosts("10.0.0.5", 16) == []


def test_une_adresse_absurde_ne_leve_pas():
    for mauvais in ("", "pas-une-ip", None, "192.168.1.999", "::1"):
        assert discovery.candidate_hosts(mauvais, 24) == []


# ---------- La sonde ----------

@pytest.fixture
def faux_bolero():
    """Un serveur HTTP local qui répond comme une antenne."""
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            if self.path != "/rest/nodeStatus":
                self.send_response(404)
                self.end_headers()
                return
            body = json.dumps(NODE_STATUS).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    srv = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1]
    srv.shutdown()
    srv.server_close()          # sinon le socket d'écoute fuit (leçon 2026-07-22)


def test_la_sonde_reconnait_une_antenne(faux_bolero):
    fiche = discovery.probe("127.0.0.1", port=faux_bolero)
    assert fiche["ip"] == "127.0.0.1"
    assert fiche["name"] == "Bolero-Régie"
    assert fiche["beltpacks"] == 2


@pytest.fixture
def hote_muet():
    """Un hôte qui écoute sur le port mais n'est pas une antenne (switch, imprimante)."""
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            body = b"<html>routeur</html>"
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    srv = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1]
    srv.shutdown()
    srv.server_close()


def test_un_hote_qui_n_est_pas_une_antenne_est_ecarte(hote_muet):
    assert discovery.probe("127.0.0.1", port=hote_muet) is None


def test_une_adresse_morte_ne_leve_pas_et_rend_none():
    """250 des 254 adresses d'un /24 sont mortes : elles doivent coûter un None, pas
    une exception qui interromprait le balayage."""
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    ferme = s.getsockname()[1]
    s.close()
    assert discovery.probe("127.0.0.1", port=ferme, connect_timeout=0.2) is None


def test_le_port_est_respecte_par_les_deux_etapes(faux_bolero):
    """La sonde TCP lisait la constante pendant que l'URL portait 80 en dur : changer
    le port n'aurait sondé qu'à moitié."""
    assert discovery.probe("127.0.0.1", port=faux_bolero) is not None
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    autre = s.getsockname()[1]
    s.close()
    assert discovery.probe("127.0.0.1", port=autre, connect_timeout=0.2) is None


def test_la_signature_exige_la_forme_d_une_reponse_bolero():
    assert discovery._looks_like_antenna({"nodeStatus": []})
    for faux in ({"autre": 1}, {"nodeStatus": "texte"}, [], None, "x"):
        assert not discovery._looks_like_antenna(faux)


# ---------- La route ----------

def test_la_route_propose_sans_jamais_connecter(auth_client, app):
    r = auth_client.post("/api/antenna/discover")
    assert r.status_code == 200
    body = r.get_json()
    assert body["available"] is True and body["antennas"]
    assert app.extensions["antenna"].connected is False, (
        "la découverte doit PROPOSER, jamais connecter d'elle-même"
    )


def test_la_route_n_accepte_aucune_adresse_du_client(auth_client, app):
    """Anti-SSRF : le périmètre vient du boîtier, pas de la requête."""
    r = auth_client.post("/api/antenna/discover",
                         json={"base_ip": "10.99.0.1", "target": "169.254.169.254"})
    assert r.status_code == 200
    # Rien de ce qui a été envoyé n'est repris : en test la réponse est le jeu fictif.
    assert [a["ip"] for a in r.get_json()["antennas"]] == ["192.168.1.11", "192.168.1.12"]


def test_la_saisie_manuelle_reste_le_chemin_de_reference(auth_client):
    """Exigence explicite : la découverte n'enlève rien."""
    r = auth_client.post("/api/antenna/connect", json={"ip": "192.168.1.11", "password": "x"})
    assert r.status_code in (200, 502), "la connexion par IP directe doit rester possible"
    assert auth_client.post("/api/antenna/connect", json={"ip": "pas-une-ip"}).status_code == 400


def test_la_route_exige_une_session(client):
    client.post("/admin/setup", data={"password": "motdepasse8"})
    client.post("/admin/logout")
    assert client.post("/api/antenna/discover").status_code in (401, 302)
