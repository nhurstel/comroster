import http.server
import io
import json
import os
import socketserver
import urllib.parse

import segno

from . import viewer_pages
from .services.netconfig import NetConfig
from .services.netconfig import validate as validate_network
from .services.viewer import ViewerConfig, probe_server
from .services.viewer_auth import ViewerAuth

#: Le formulaire de configuration fait quelques centaines d'octets. Sans borne, un
#: Content-Length annoncé énorme ferait lire jusqu'à saturation de la mémoire du Pi.
MAX_BODY_BYTES = 64 * 1024


def make_handler(data_dir, auth=None):
    viewer = ViewerConfig(data_dir)
    netcfg = NetConfig(data_dir)
    # Code d'appariement : écrire la configuration exige de lire le code AFFICHÉ sur
    # l'écran de l'afficheur. Sans lui, n'importe quoi sur le LAN pouvait repointer
    # l'afficheur vers un serveur arbitraire ou lui casser son adresse (audit 2026-07-28).
    auth = auth or ViewerAuth(data_dir, os.environ.get("COMROSTER_VIEWER_CODE"))

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _json(self, status, payload):
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _html(self, status, body):
            data = body.encode()
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _host_ip(self):
            # IP par laquelle le client nous joint (pour le QR pointant vers cet afficheur)
            host = self.headers.get("Host", "")
            return host.split(":")[0] or "comroster.local"

        def do_GET(self):
            if self.path.startswith("/api/server-status"):
                reachable = probe_server(viewer.health_url(), timeout=1.5)
                return self._json(200, {
                    "reachable": reachable,
                    "display_url": viewer.display_url(),
                })
            if self.path == "/" or self.path.startswith("/?"):
                # Le code d'appariement s'affiche ICI, sur l'écran de l'afficheur : c'est
                # ce qui fait de la présence physique la preuve d'autorisation.
                return self._html(200, viewer_pages.boot_html(viewer.display_url(), auth.code))
            if self.path.rstrip("/") == "/config":
                return self._html(200, viewer_pages.config_html(viewer.load(), netcfg.load()))
            if self.path.startswith("/qr.svg"):
                buf = io.BytesIO()
                segno.make(f"http://{self._host_ip()}:8081/config", error="m").save(
                    buf, kind="svg", scale=5, border=2)
                self.send_response(200)
                self.send_header("Content-Type", "image/svg+xml")
                self.end_headers()
                self.wfile.write(buf.getvalue())
                return
            return self._json(404, {"error": "not_found"})

        def do_POST(self):
            if self.path.rstrip("/") != "/config":
                return self._json(404, {"error": "not_found"})
            # Garde-fou mémoire : le corps est un petit formulaire (quelques centaines
            # d'octets). Sans borne, un Content-Length annoncé énorme ferait lire
            # jusqu'à saturation — l'agent tourne sur un Pi.
            try:
                length = int(self.headers.get("Content-Length", 0))
            except (TypeError, ValueError):
                return self._json(400, {"error": "Requête invalide"})
            if not (0 <= length <= MAX_BODY_BYTES):
                return self._json(413, {"error": "Requête trop volumineuse"})
            raw = self.rfile.read(length).decode("utf-8", "replace")
            form = {k: v[0] for k, v in urllib.parse.parse_qs(raw).items()}

            # 0. Code d'appariement — AVANT toute écriture. Il est affiché sur l'écran de
            # l'afficheur : le fournir prouve qu'on est physiquement dans la salle.
            if not auth.check(form.get("pairing_code", "")):
                if "text/html" in self.headers.get("Accept", ""):
                    return self._html(403, viewer_pages.config_html(
                        viewer.load(), netcfg.load(),
                        error="Code incorrect — il est affiché sur l'écran de l'afficheur."))
                return self._json(403, {"error": "Code d'appariement incorrect"})

            # 1. Cible serveur
            try:
                viewer.save({"server_ip": form.get("server_ip", ""),
                             "server_port": int(form.get("server_port", 8080))})
            except (ValueError, TypeError) as exc:
                return self._json(400, {"error": str(exc)})
            # 2. Réseau propre de l'afficheur (schéma NetConfig)
            net = {"link": "ethernet", "mode": form.get("network_mode", "link-local")}
            if net["mode"] == "static":
                net["address"] = form.get("network_address", "")
                try:
                    net["prefix"] = int(form.get("network_prefix", 24))
                except (ValueError, TypeError):
                    return self._json(400, {"error": "Préfixe réseau invalide"})
            ok, err = validate_network(net)
            if not ok:
                return self._json(400, {"error": err})
            netcfg.save(net)
            if "text/html" in self.headers.get("Accept", ""):
                return self._html(200, "<!DOCTYPE html><meta charset=utf-8>"
                    "<body style='background:#0A1628;color:#7CFFB2;font-family:sans-serif;"
                    "text-align:center;padding-top:20vh'><h1>✅ Enregistré</h1>"
                    "<p>Redémarrez l'afficheur pour appliquer.</p></body>")
            return self._json(200, {"ok": True, "reboot_required": True})

    return Handler


class _ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    """Un client lent ne doit pas bloquer l'agent entier.

    `HTTPServer` traite une requête à la fois : un téléphone qui perd le réseau au milieu
    d'un POST gelait la seule page permettant de reconfigurer l'afficheur, jusqu'au
    timeout TCP. `daemon_threads` pour que l'arrêt du service ne soit pas retenu par une
    connexion en cours.
    """
    daemon_threads = True
    allow_reuse_address = True


def build_server(data_dir, port=8081, auth=None):
    return _ThreadedHTTPServer(("0.0.0.0", port), make_handler(data_dir, auth=auth))


def main():
    data_dir = os.environ.get("DATA_DIR", os.path.join(os.getcwd(), "instance"))
    port = int(os.environ.get("COMROSTER_VIEWER_PORT", "8081"))
    auth = ViewerAuth(data_dir, os.environ.get("COMROSTER_VIEWER_CODE"))
    srv = build_server(data_dir, port=port, auth=auth)
    print(f"ComRoster viewer-agent sur 0.0.0.0:{port} (data={data_dir})")
    # Journalisé au démarrage : le code est normalement lu sur l'écran de l'afficheur,
    # mais si celui-ci affiche déjà le tableau, `journalctl -u comroster-viewer` le donne
    # sans avoir à redémarrer quoi que ce soit.
    print(f"Code d'appariement (affiché à l'écran) : {auth.code}")
    srv.serve_forever()


if __name__ == "__main__":
    main()
