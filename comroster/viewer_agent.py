import http.server
import json
import urllib.parse

from .services.viewer import ViewerConfig, probe_server
from .services.netconfig import NetConfig, validate as validate_network


def make_handler(data_dir):
    viewer = ViewerConfig(data_dir)
    netcfg = NetConfig(data_dir)

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

        def do_GET(self):
            if self.path.startswith("/api/server-status"):
                reachable = probe_server(viewer.health_url(), timeout=1.5)
                return self._json(200, {
                    "reachable": reachable,
                    "display_url": viewer.display_url(),
                })
            return self._json(404, {"error": "not_found"})

        def do_POST(self):
            if self.path.rstrip("/") != "/config":
                return self._json(404, {"error": "not_found"})
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length).decode()
            form = {k: v[0] for k, v in urllib.parse.parse_qs(raw).items()}
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
                net["prefix"] = int(form.get("network_prefix", 24))
            ok, err = validate_network(net)
            if not ok:
                return self._json(400, {"error": err})
            netcfg.save(net)
            return self._json(200, {"ok": True, "reboot_required": True})

    return Handler


def build_server(data_dir, port=8081):
    return http.server.HTTPServer(("0.0.0.0", port), make_handler(data_dir))
