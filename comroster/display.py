import json
import queue
import time

from flask import Blueprint, Response, current_app, render_template, stream_with_context

from .services import model

bp = Blueprint("display", __name__)

HEARTBEAT_SECONDS = 15


def format_sse(event, data):
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@bp.get("/display")
def display_page():
    try:
        return render_template("display.html")
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
