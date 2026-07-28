import io
import json
import queue
import socket
import time

import segno
from flask import (
    Blueprint,
    Response,
    abort,
    current_app,
    render_template,
    request,
    send_file,
    stream_with_context,
)

from .security import limiter
from .services import model, netstatus, pubsub

bp = Blueprint("display", __name__)

HEARTBEAT_SECONDS = 15


def format_sse(event, data):
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _primary_lan_ip():
    """IP joignable depuis le réseau local, robuste sur une infra de switchs sans routeur.

    Ordre : IP fixe configurée → route par défaut → énumération des interfaces → loopback.
    Sur un réseau sans passerelle, la ruse du routage échoue : on ne doit PAS retomber
    bêtement sur 127.0.0.1 (le QR d'onboarding serait inutilisable depuis le téléphone).
    """
    cfg = current_app.extensions["netconfig"].load()
    if cfg.get("mode") == "static" and cfg.get("address"):
        return cfg["address"]
    # Les deux sondes vivent dans services/netstatus.py : la découverte d'antenne a
    # besoin de la même « quelle est mon adresse sur ce réseau ? », et deux copies de
    # cette logique finiraient par répondre différemment.
    return netstatus.route_lan_ip() or netstatus.enumerate_lan_ip() or "127.0.0.1"


def _admin_urls():
    """URL d'admin joignable depuis le téléphone du client (IP LAN + nom mDNS)."""
    port = request.host.partition(":")[2] or "8080"
    suffix = "" if port in ("80", "") else f":{port}"
    ip = _primary_lan_ip()
    host = socket.gethostname().split(".")[0] or "comroster"
    return (f"http://{ip}{suffix}/admin", f"http://{host}.local{suffix}/admin")


@bp.get("/api/onboarding")
@limiter.limit("120 per minute")
def onboarding():
    # Publique et sondée toutes les 8 s tant que le boîtier n'est pas configuré. Elle
    # ouvre un socket pour déterminer l'IP joignable : la seule route publique qui coûte
    # autre chose qu'une lecture mémoire, donc la seule à mériter une borne ici.
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


#: Une semaine. Le pack ne bouge qu'au redémarrage du service ; l'invalidation passe par
#: le `?v=<version>` que les templates ajoutent, comme le cache-buster des URLs static.
BRAND_CACHE_SECONDS = 604800


def _servir_logo(attribut):
    brand = current_app.extensions["branding"]
    if not brand.active:
        abort(404)
    reponse = send_file(getattr(brand, attribut), conditional=True)
    reponse.headers["Cache-Control"] = f"public, max-age={BRAND_CACHE_SECONDS}"
    return reponse


@bp.get("/branding/logo")
def brand_logo():
    """Logo de marque affiché en régie. 404 s'il n'y a pas de pack : les templates ne
    référencent alors pas cette route, mais elle reste honnête."""
    return _servir_logo("logo_path")


@bp.get("/branding/logo-print")
def brand_logo_print():
    """Variante encre noire, pour la feuille imprimable."""
    return _servir_logo("print_logo_path")


@bp.get("/display")
def display_page():
    published = current_app.extensions["storage"].load_published() or model.empty_state()
    return render_template("display.html", initial_data=published)


@bp.get("/events")
def events():
    broker = current_app.extensions["broker"]
    storage = current_app.extensions["storage"]

    # `?role=admin` : la page d'administration s'abonne au même flux, mais n'affiche rien
    # en salle. Le type sert à deux choses — ne pas la compter comme un écran de régie, et
    # l'empêcher d'affamer les vrais écrans (réserve ci-dessous). Allowlist : toute valeur
    # inconnue retombe sur « écran », le cas le plus prudent.
    kind = pubsub.sanitize_kind(request.args.get("role"))

    # Chaque flux occupe un thread gunicorn : au-delà du cap on répond 503 plutôt
    # que de saturer le pool (le display retente automatiquement 4 s plus tard).
    if broker.subscriber_count >= current_app.config["SSE_MAX_CLIENTS"]:
        return Response("Trop d'écrans connectés", status=503,
                        headers={"Retry-After": "5"})

    # RÉSERVE : les onglets d'administration sont bornés bien en dessous du cap total.
    # Sans elle, quelques onglets admin laissés ouverts consommeraient les créneaux des
    # écrans, et c'est la SALLE qui perdrait l'affichage — l'inverse exact de la priorité
    # voulue. Un admin dégradé se resynchronise au rechargement ; un écran de régie noir,
    # lui, se voit du fond de la salle.
    if kind == pubsub.ADMIN and broker.count(pubsub.ADMIN) >= current_app.config["SSE_ADMIN_MAX"]:
        return Response("Trop d'onglets d'administration ouverts", status=503,
                        headers={"Retry-After": "10"})

    def stream():
        q = broker.subscribe(kind)
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
