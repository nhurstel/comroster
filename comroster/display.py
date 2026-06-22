import io
import json
import queue
import socket
import time

import segno
from flask import Blueprint, Response, current_app, render_template, request, stream_with_context

from .services import model

bp = Blueprint("display", __name__)

HEARTBEAT_SECONDS = 15


def format_sse(event, data):
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _route_lan_ip():
    """Interface de la route par défaut (échoue sur un réseau sans passerelle)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))   # ne envoie rien ; choisit l'interface sortante
        return s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()


def _enumerate_lan_ip():
    """Première IPv4 non-loopback liée à l'hôte (link-local incluse)."""
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127."):
                return ip
    except OSError:
        pass
    return None


def _primary_lan_ip():
    """IP joignable depuis le réseau local, robuste sur une infra de switchs sans routeur.

    Ordre : IP fixe configurée → route par défaut → énumération des interfaces → loopback.
    Sur un réseau sans passerelle, la ruse du routage échoue : on ne doit PAS retomber
    bêtement sur 127.0.0.1 (le QR d'onboarding serait inutilisable depuis le téléphone).
    """
    cfg = current_app.extensions["netconfig"].load()
    if cfg.get("mode") == "static" and cfg.get("address"):
        return cfg["address"]
    return _route_lan_ip() or _enumerate_lan_ip() or "127.0.0.1"


def _admin_urls():
    """URL d'admin joignable depuis le téléphone du client (IP LAN + nom mDNS)."""
    port = request.host.partition(":")[2] or "8080"
    suffix = "" if port in ("80", "") else f":{port}"
    ip = _primary_lan_ip()
    host = socket.gethostname().split(".")[0] or "comroster"
    return (f"http://{ip}{suffix}/admin", f"http://{host}.local{suffix}/admin")


@bp.get("/api/onboarding")
def onboarding():
    secret = current_app.extensions["secret"]
    published = current_app.extensions["storage"].load_published()
    admin_url, hostname_url = _admin_urls()
    return {
        "configured": secret.is_configured(),
        "published": published is not None,
        "admin_url": admin_url,
        "hostname_url": hostname_url,
    }


@bp.get("/display/qr.svg")
def qr_svg():
    admin_url, _ = _admin_urls()
    qr = segno.make(admin_url, error="m")
    buf = io.BytesIO()
    qr.save(buf, kind="svg", scale=6, border=2, dark="#0c111d", light=None)
    return Response(buf.getvalue(), mimetype="image/svg+xml",
                    headers={"Cache-Control": "no-store"})


@bp.get("/display")
def display_page():
    published = current_app.extensions["storage"].load_published() or model.empty_state()
    try:
        return render_template("display.html", initial_data=published)
    except Exception:
        return "DISPLAY OK"


@bp.get("/events")
def events():
    broker = current_app.extensions["broker"]
    storage = current_app.extensions["storage"]

    def stream():
        q = broker.subscribe()
        try:
            published = storage.load_published() or model.empty_state()
            yield "retry: 3000\n\n"
            yield format_sse("snapshot", published)
            last = time.monotonic()
            while True:
                try:
                    event, data = q.get(timeout=1.0)
                    yield format_sse(event, data)
                except queue.Empty:
                    pass
                if time.monotonic() - last >= HEARTBEAT_SECONDS:
                    yield ": keepalive\n\n"
                    last = time.monotonic()
        finally:
            broker.unsubscribe(q)

    resp = Response(stream_with_context(stream()), mimetype="text/event-stream")
    resp.headers["Cache-Control"] = "no-cache"
    resp.headers["X-Accel-Buffering"] = "no"
    resp.headers["Connection"] = "keep-alive"
    return resp
