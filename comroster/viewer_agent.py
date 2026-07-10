import http.server
import io
import json
import os
import urllib.parse

import segno

from . import viewer_pages
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
                return self._html(200, viewer_pages.boot_html(viewer.display_url()))
            if self.path.rstrip("/") == "/config":
                return self._html(200, viewer_pages.config_html(viewer.load(), netcfg.load()))
            if self.path.startswith("/qr.svg"):
                buf = io.BytesIO()
                segno.make("http://%s:8081/config" % self._host_ip(), error="m").save(
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
            if "text/html" in self.headers.get("Accept", ""):
                return self._html(200, "<!DOCTYPE html><meta charset=utf-8>"
                    "<body style='background:#0A1628;color:#7CFFB2;font-family:sans-serif;"
                    "text-align:center;padding-top:20vh'><h1>✅ Enregistré</h1>"
                    "<p>Redémarrez l'afficheur pour appliquer.</p></body>")
            return self._json(200, {"ok": True, "reboot_required": True})

    return Handler


def build_server(data_dir, port=8081):
    return http.server.HTTPServer(("0.0.0.0", port), make_handler(data_dir))


def main():
    data_dir = os.environ.get("DATA_DIR", os.path.join(os.getcwd(), "instance"))
    port = int(os.environ.get("COMROSTER_VIEWER_PORT", "8081"))
    srv = build_server(data_dir, port=port)
    print(f"ComRoster viewer-agent sur 0.0.0.0:{port} (data={data_dir})")
    srv.serve_forever()


if __name__ == "__main__":
    main()
