import base64
import re
from datetime import datetime, timezone

from flask import Blueprint, current_app, jsonify, render_template, request

from .security import exclusive_state, json_body, login_required
from .services import backup, health, model, netstatus, wifi

bp = Blueprint("api", __name__)

_CODE_TO_HTTP = {
    "beltpack_conflict": 409,
    "beltpack_empty": 409,
    "not_found": 404,
}


def _storage():
    return current_app.extensions["storage"]


def _history():
    return current_app.extensions["history"]


def _netconfig():
    return current_app.extensions["netconfig"]


def _journal():
    return current_app.extensions["journal"]


def _error(exc):
    return jsonify({"error": str(exc), "code": exc.code}), _CODE_TO_HTTP.get(exc.code, 400)


@bp.get("/admin")
@login_required
def admin_page():
    return render_template("admin.html", initial_data=_storage().load_draft())


@bp.get("/admin/preview")
@login_required
def admin_preview():
    """Report de l'écran de régie : rend l'état PUBLIÉ par défaut, comme /display.

    C'est un témoin de ce qui est réellement affiché en salle, pas un aperçu du
    brouillon — l'admin travaille sur le brouillon, il a donc surtout besoin de voir
    ce que le public voit pendant qu'il le prépare.

    `?draft=1` rend au contraire le BROUILLON : c'est l'aperçu de l'onglet « Écran »,
    où régler une apparence, une luminosité ou un nombre de colonnes sans voir le
    résultat obligeait à publier pour juger. Les deux vues coexistent parce qu'elles
    répondent à deux questions distinctes — « qu'y a-t-il à l'antenne ? » et « à quoi
    ressemblera ce que je prépare ? » — ce n'est donc pas un doublon de fonction.

    `preview=True` coupe côté client tout ce qui coûte au serveur ou tourne en continu,
    au premier chef l'abonnement SSE : chaque flux /events occupe un thread gthread en
    permanence et un créneau de SSE_MAX_CLIENTS. Ce témoin étant monté en permanence
    dans l'admin, il en ouvrirait un par onglet ouvert (cf. leçon 2026-07-06).

    `?scroll=1` rend le défilement automatique, qui est la seule façon de voir si le
    contenu déborde de l'écran. Réservé au grand aperçu, ouvert à la demande : le témoin
    permanent le laisse coupé (une animation en continu dans un onglet toujours ouvert).
    """
    if request.args.get("draft") == "1":
        state = _storage().load_draft()
    else:
        state = _storage().load_published() or model.empty_state()
    return render_template("display.html", initial_data=state, preview=True,
                           preview_scroll=request.args.get("scroll") == "1")


@bp.get("/admin/print")
@login_required
def admin_print():
    """Feuille d'affectation à imprimer (fonction « Impression » de l'admin).

    Les régies travaillent sur papier, et c'est le filet quand le boîtier tombe : une
    conduite imprimée survit à une panne d'alimentation, pas un écran. Comme
    `/admin/preview`, elle rend l'état PUBLIÉ par défaut — c'est ce que la salle voit —
    et `?draft=1` rend le brouillon, pour imprimer une version en préparation.
    """
    draft = request.args.get("draft") == "1"
    state = (_storage().load_draft() if draft
             else _storage().load_published() or model.empty_state())
    groups = sorted(state.get("groups") or [], key=lambda g: g.get("order") or 0)
    people = state.get("people") or []
    by_group = {
        g["id"]: sorted((p for p in people if p.get("group_id") == g["id"]),
                        key=lambda p: _beltpack_sort_key(p.get("beltpack")))
        for g in groups
    }
    reserve = sorted((p for p in people if not p.get("group_id")),
                     key=lambda p: _beltpack_sort_key(p.get("beltpack")))
    return render_template(
        "print.html", state=state, groups=groups, by_group=by_group,
        reserve=reserve, is_draft=draft,
        printed_at=datetime.now(timezone.utc).astimezone().strftime("%d/%m/%Y à %H:%M"),
    )


def _beltpack_sort_key(value):
    """Tri NUMÉRIQUE des beltpacks : en tri texte, « 10 » se glisse entre « 1 » et « 2 »,
    ce qui rend une feuille papier pénible à parcourir. Les numéros non entiers
    (rarissimes, mais le champ est libre) passent en fin, par ordre alphabétique."""
    text = str(value or "").strip()
    return (0, int(text), "") if text.isdigit() else (1, 0, text)


@bp.get("/api/state")
@login_required
def get_state():
    return jsonify(_storage().load_draft())


@bp.get("/api/status")
@login_required
def get_status():
    """Ce qui est réellement à l'antenne, pour la barre d'état de l'admin.

    - `displays` : nombre d'ÉCRANS DE RÉGIE abonnés au flux SSE. Deux exclusions, pour
      deux raisons distinctes : les aperçus de l'admin n'ouvrent jamais de flux (ils
      n'apparaissent donc nulle part), et la page d'administration en ouvre bien un mais
      s'annonce `?role=admin` — sans quoi elle se comptait comme un écran, et l'admin
      ouvert seul affichait « 1 afficheur » (corrigé à l'audit 2026-07-28).
    - `published` : résumé de l'état PUBLIÉ (groupes, beltpacks, horodatage), pour
      afficher la dernière diffusion et l'écart avec le brouillon en cours. On ne
      renvoie qu'un résumé, pas l'état entier : la barre n'a besoin que des compteurs.
    """
    published = _storage().load_published()
    summary = None
    if published:
        summary = {
            "groups": len(published.get("groups", [])),
            "people": len(published.get("people", [])),
            "updated_at": published.get("updated_at"),
        }
    return jsonify({
        "displays": current_app.extensions["broker"].display_count,
        "published": summary,
    })


@bp.get("/api/network")
@login_required
def get_network():
    # Vue publique : le psk Wi-Fi est write-only (psk_set en lecture).
    return jsonify(_netconfig().load_public())


@bp.put("/api/network")
@login_required
def put_network():
    data = json_body()
    try:
        _netconfig().save(data)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    # L'application réelle (nmcli) se fait par le service système comroster-network :
    # soit à chaud via POST /api/network/apply, soit au prochain démarrage.
    # Vue publique dans la réponse : le psk ne doit jamais ressortir.
    public = _netconfig().load_public()
    _journal().record("network_save",
                      f"{public.get('link', '?')} · {public.get('mode', '?')}")
    return jsonify({"ok": True, "config": public, "reboot_required": True})


@bp.get("/api/network/status")
@login_required
def network_status():
    """État réseau courant (lecture seule) : où le boîtier est joignable maintenant.

    En dev/test : état fictif. Sur le Pi : nmcli en lecture, sans privilège.
    """
    if current_app.debug or current_app.testing:
        return jsonify({"available": True, "simulated": True, "links": netstatus.sample()})
    return jsonify(netstatus.current())


@bp.get("/api/network/wifi-scan")
@login_required
def wifi_scan():
    """Réseaux Wi-Fi à proximité (lecture seule) pour le sélecteur du dialogue réseau.

    En dev/test : liste fictive (aucun nmcli disponible) — l'UI reste testable.
    Sur le Pi : nmcli en lecture, sans privilège (le scan ne modifie rien).
    """
    if current_app.debug or current_app.testing:
        return jsonify({"available": True, "simulated": True, "networks": wifi.sample()})
    return jsonify(wifi.scan())


@bp.post("/api/network/apply")
@login_required
def apply_network_now():
    """Applique la config réseau immédiatement, sans redémarrer le boîtier."""
    if current_app.debug or current_app.testing:
        _journal().record("network_apply", "simulé (mode dev)")
        return jsonify({"ok": True, "simulated": True})
    ok, error = _apply_network()
    if not ok:
        return jsonify({"ok": False, "error": f"Application impossible : {error}"}), 500
    _journal().record("network_apply")
    return jsonify({"ok": True})


def _run_privileged(cmd, timeout=10):
    """Lance une commande root via sudo. Retourne (ok, message d'erreur ou None).

    Deux pièges évités ici :
      • `sudo -n` : sans TTY (service systemd), un sudo qui demande un mot de passe
        BLOQUERAIT. En non-interactif il échoue immédiatement, on peut le signaler.
      • on ATTEND le retour : un refus (droit sudo manquant) est donc détecté ici, au
        lieu d'être avalé silencieusement par un Popen « fire-and-forget ».

    Un dépassement de délai n'est PAS une erreur : la commande coupe volontairement le
    tapis sous nos pieds (redémarrage, ou changement d'IP qui tue la connexion).
    """
    import subprocess
    try:
        proc = subprocess.run(["sudo", "-n", *cmd], check=False,   # code retour inspecté
                              capture_output=True, text=True,      # plus bas, pas ici
                              timeout=timeout)
    except subprocess.TimeoutExpired:
        return True, None          # pas de retour = c'est en train de s'appliquer
    except OSError as exc:         # sudo/systemctl absent du PATH
        return False, str(exc)
    if proc.returncode != 0:
        lines = [ln for ln in (proc.stderr or "").strip().splitlines() if ln.strip()]
        return False, lines[-1] if lines else f"code {proc.returncode}"
    return True, None


def _trigger_reboot():
    """`systemctl reboot` rend la main dès que systemd a accepté la demande."""
    return _run_privileged(["systemctl", "reboot"])


def _apply_network():
    """Rejoue le service qui applique instance/network.json via nmcli (même chemin qu'au boot).

    Évite le redémarrage complet : nmcli reconfigure l'interface à chaud. La session
    admin en cours tombera si l'IP change — c'est inhérent, reboot ou pas.
    """
    return _run_privileged(["systemctl", "restart", "comroster-network.service"], timeout=30)


@bp.post("/api/reboot")
@login_required
def reboot_box():
    # En dev (debug) ou sous tests, on ne redémarre pas vraiment la machine.
    if current_app.debug or current_app.testing:
        _journal().record("reboot", "simulé (mode dev)")
        return jsonify({"ok": True, "simulated": True})
    ok, error = _trigger_reboot()
    if not ok:
        # Cas typique : /etc/sudoers.d/comroster-reboot absent (Pi installé avant 2026-07-15)
        # → « sudo: a password is required ». On le dit au lieu de faire semblant.
        return jsonify({"ok": False, "error": f"Redémarrage refusé : {error}"}), 500
    _journal().record("reboot")
    return jsonify({"ok": True})


@bp.post("/api/groups")
@login_required
@exclusive_state
def create_group():
    data = json_body()
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Nom de groupe requis", "code": "invalid"}), 400
    state = _storage().load_draft()
    try:
        g = model.add_group(state, name, data.get("color", "#888888"), data.get("order"))
    except model.ValidationError as exc:
        return _error(exc)
    _storage().save_draft(state)
    return jsonify(g)


@bp.patch("/api/groups/<gid>")
@login_required
@exclusive_state
def patch_group(gid):
    data = json_body()
    fields = {k: data[k] for k in ("name", "color", "order") if k in data}
    state = _storage().load_draft()
    try:
        g = model.update_group(state, gid, **fields)
    except model.ValidationError as exc:
        return _error(exc)
    _storage().save_draft(state)
    return jsonify(g)


@bp.delete("/api/groups/<gid>")
@login_required
@exclusive_state
def delete_group(gid):
    state = _storage().load_draft()
    try:
        model.delete_group(state, gid)
    except model.ValidationError as exc:
        return _error(exc)
    _storage().save_draft(state)
    return jsonify({"ok": True})


@bp.post("/api/people")
@login_required
@exclusive_state
def create_person():
    data = json_body()
    state = _storage().load_draft()
    try:
        p = model.add_person(state, data.get("role", ""), data.get("beltpack"), data.get("group_id"))
    except model.ValidationError as exc:
        return _error(exc)
    _storage().save_draft(state)
    return jsonify(p)


@bp.patch("/api/people/<pid>")
@login_required
@exclusive_state
def patch_person(pid):
    data = json_body()
    fields = {k: data[k] for k in ("role", "beltpack", "group_id") if k in data}
    state = _storage().load_draft()
    try:
        p = model.update_person(state, pid, **fields)
    except model.ValidationError as exc:
        return _error(exc)
    _storage().save_draft(state)
    return jsonify(p)


@bp.delete("/api/people/<pid>")
@login_required
@exclusive_state
def delete_person(pid):
    state = _storage().load_draft()
    try:
        model.delete_person(state, pid)
    except model.ValidationError as exc:
        return _error(exc)
    _storage().save_draft(state)
    return jsonify({"ok": True})


@bp.post("/api/people/delete-batch")
@login_required
@exclusive_state
def delete_people_batch():
    data = json_body()
    ids = data.get("ids")
    if not isinstance(ids, list):
        return jsonify({"error": "ids doit être une liste", "code": "invalid"}), 400
    state = _storage().load_draft()
    deleted = model.delete_people(state, ids)
    _storage().save_draft(state)
    return jsonify({"deleted": deleted})


@bp.put("/api/draft")
@login_required
@exclusive_state
def replace_draft():
    """Remplace le brouillon complet (édition en bloc depuis l'admin)."""
    payload = json_body()
    try:
        state = model.build_draft(payload)
    except model.ValidationError as exc:
        return _error(exc)
    _storage().save_draft(state)
    return jsonify(state)


@bp.get("/api/export")
@login_required
def export_state():
    resp = jsonify(_storage().load_draft())
    resp.headers["Content-Disposition"] = "attachment; filename=comroster.json"
    return resp


@bp.post("/api/import")
@login_required
@exclusive_state
def import_state():
    # Même chemin que PUT /api/draft : build_draft normalise (ids, champs, scale)
    # et valide — un JSON malformé donne 400/409, jamais un 500.
    payload = json_body()
    try:
        state = model.build_draft(payload)
    except model.ValidationError as exc:
        return _error(exc)
    _storage().save_draft(state)
    _journal().record("import",
                      _counts(state))
    return jsonify(state)


def _counts(state):
    """Résumé chiffré d'un état, au journal. Le pluriel est accordé : « 1 groupes »
    dans une conduite de régie fait négligé, et c'est le cas le plus fréquent au
    démarrage d'une production."""
    g, p = len(state["groups"]), len(state["people"])
    return f"{g} groupe{'s' if g > 1 else ''} · {p} beltpack{'s' if p > 1 else ''}"


@bp.post("/api/publish")
@login_required
@exclusive_state
def publish():
    """Publie le brouillon. `{"label": "Générale", "pinned": true}` pose un repère.

    Un corps est FACULTATIF : le raccourci clavier et le bouton publient sans rien
    envoyer, et une publication ordinaire ne doit pas devenir une formalité.
    """
    data = request.get_json(force=True, silent=True)
    data = data if isinstance(data, dict) else {}
    label = str(data.get("label") or "").strip()
    pinned = bool(data.get("pinned"))

    state = _storage().load_draft()
    try:
        model.validate_state(state)
    except model.ValidationError as exc:
        # Brouillon invalide : on refuse de publier (409, cf. cahier des charges §10.3).
        return jsonify({"error": str(exc), "code": exc.code}), 409
    from .services.publisher import broadcast_published
    try:
        broadcast_published(current_app, state, label=label, pinned=pinned)
    except ValueError as exc:              # plafond de repères épinglés atteint
        return jsonify({"error": str(exc), "code": "pinned_full"}), 409
    _journal().record("publish", f"{_counts(state)}{' · ' + label if label else ''}")
    return jsonify({"ok": True, "updated_at": state["updated_at"], "label": label})


@bp.post("/api/history/<ts>/label")
@login_required
def history_label(ts):
    """Nomme et/ou épingle un instantané après coup.

    On ne sait pas toujours au moment de publier que cette version-là sera celle qui
    compte : nommer a posteriori est le cas le plus fréquent.
    """
    if not re.fullmatch(r"\d{8}T\d{6}\d*Z", ts):     # format des snapshots uniquement
        return jsonify({"error": "not_found", "code": "not_found"}), 404
    data = json_body()
    label = data.get("label")
    pinned = data.get("pinned")
    if pinned is not None and not isinstance(pinned, bool):
        return jsonify({"error": "pinned doit être un booléen"}), 400
    try:
        meta = _history().annotate(ts, label=label, pinned=pinned)
    except KeyError:
        return jsonify({"error": "not_found", "code": "not_found"}), 404
    except ValueError as exc:
        return jsonify({"error": str(exc), "code": "pinned_full"}), 409
    return jsonify(meta)


@bp.get("/admin/journal")
@login_required
def journal_page():
    """Page Journal : événements applicatifs + logs techniques (debug sans SSH)."""
    return render_template("journal.html")


@bp.get("/admin/health")
@login_required
def health_page():
    """Page de monitoring : santé du boîtier (température, disque, RAM, uptime…)."""
    return render_template("health.html")


@bp.get("/api/health")
@login_required
def health_snapshot():
    """Instantané de santé du boîtier (lecture seule, tolérant hors Pi)."""
    return jsonify(health.snapshot(current_app))


@bp.get("/api/journal")
@login_required
def journal_list():
    """Les derniers événements du boîtier (publications, imports, antenne, réseau…)."""
    return jsonify(_journal().entries())


@bp.get("/api/logs")
@login_required
def logs_list():
    """Logs techniques captés en mémoire (volet « Technique » de la page Journal)."""
    return jsonify(current_app.extensions["logbuffer"].entries())


# ---------------------------------------------------------------------------
# Sauvegarde complète du boîtier
#
# L'export `.rost` ne couvre que le roster : un boîtier mort emportait avec lui le réseau,
# l'antenne, les configurations nommées et le mot de passe. Ces trois routes transportent
# l'archive en base64 dans du JSON plutôt qu'en multipart : la protection CSRF et le
# `json_body()` du reste de l'API s'appliquent alors sans traitement particulier.
# ---------------------------------------------------------------------------

@bp.post("/api/backup")
@login_required
def backup_create():
    """Fabrique l'archive chiffrée. La phrase de passe ne quitte jamais cette requête."""
    data = json_body()
    try:
        blob = backup.encrypt(backup.build_payload(current_app), data.get("passphrase") or "")
    except backup.BackupError as exc:
        return jsonify({"error": str(exc)}), 400
    _journal().record("backup_create")
    stamp = model.now_iso().replace(":", "").replace("-", "")
    return jsonify({
        "filename": f"comroster-sauvegarde-{stamp}.rostbak",
        "content": base64.b64encode(blob).decode(),
    })


def _decode_upload(data):
    """Contenu d'archive envoyé par le navigateur (base64) → octets."""
    try:
        return base64.b64decode(data.get("content") or "", validate=True)
    except (ValueError, TypeError) as exc:
        raise backup.BackupError("Fichier illisible.") from exc


@bp.post("/api/backup/inspect")
@login_required
def backup_inspect():
    """Ce que l'archive contient, AVANT de l'appliquer.

    Restaurer écrase le réseau et le mot de passe : l'opérateur doit voir ce qu'il
    s'apprête à remplacer, pas cliquer à l'aveugle sur « Restaurer ».
    """
    data = json_body()
    try:
        payload = backup.decrypt(_decode_upload(data), data.get("passphrase") or "")
    except backup.BackupError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(backup.summarize(payload))


@bp.post("/api/backup/restore")
@login_required
@exclusive_state
def backup_restore():
    """Applique l'archive. Sous verrou : on ne restaure pas pendant une édition."""
    data = json_body()
    try:
        payload = backup.decrypt(_decode_upload(data), data.get("passphrase") or "")
        restored = backup.apply_payload(current_app, payload)
    except backup.BackupError as exc:
        return jsonify({"error": str(exc)}), 400
    _journal().record("backup_restore", ", ".join(restored) or "rien")
    # `password_changed` prévient le client : si l'archive portait un autre mot de passe,
    # la session en cours reste ouverte mais la prochaine connexion utilisera celui-là.
    return jsonify({"ok": True, "restored": restored,
                    "password_changed": "mot de passe" in restored})


@bp.get("/api/history")
@login_required
def history_list():
    return jsonify(_history().list())


@bp.post("/api/history/clear")
@login_required
def history_clear():
    cleared = _history().clear()
    _journal().record("history_clear", f"{cleared} publications effacées")
    return jsonify({"cleared": cleared})


@bp.post("/api/history/<ts>/restore")
@login_required
@exclusive_state
def history_restore(ts):
    if not re.fullmatch(r"\d{8}T\d{6}\d*Z", ts):     # format des snapshots uniquement
        return jsonify({"error": "not_found", "code": "not_found"}), 404
    try:
        snapshot = _history().load(ts)
    except KeyError:
        return jsonify({"error": "not_found", "code": "not_found"}), 404
    model.touch(snapshot)
    _storage().save_draft(snapshot)
    _journal().record("restore", _history()._humanize(ts))
    return jsonify(snapshot)
