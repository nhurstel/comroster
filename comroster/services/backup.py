"""Sauvegarde et restauration complètes du boîtier.

L'export existant ne couvre que le roster. Un boîtier qui meurt la veille d'une générale
emportait donc avec lui la configuration réseau, les identifiants de l'antenne, les
configurations nommées et le mot de passe d'administration : de quoi transformer une panne
matérielle en soirée perdue. Une archive unique, réinjectable sur un boîtier neuf, en fait
un incident de cinq minutes.

CHIFFREMENT OBLIGATOIRE. L'archive contient le PSK Wi-Fi en clair, le mot de passe de
l'antenne et l'empreinte du mot de passe admin. Non chiffrée, elle serait plus dangereuse
sur une clé USB que le boîtier qu'elle protège. La phrase de passe est choisie par
l'opérateur ; la clé en est dérivée par PBKDF2-HMAC-SHA256, et le sel — aléatoire par
archive — voyage en clair dans l'enveloppe, comme il se doit.

CE QUI N'EST PAS SAUVEGARDÉ, et pourquoi :
  • `lifetime.json` — le carnet de bord est l'identité du boîtier PHYSIQUE (première mise
    en service, heures de fonctionnement). Le restaurer ferait revendiquer à un boîtier
    neuf le vécu du mort : on préfère un compteur honnête à zéro.
  • `history/` — les instantanés de publication sont volumineux et dérivés. Ce qui compte
    pour repartir, c'est le brouillon et le publié, tous deux inclus.
"""
import base64
import json
import os
import secrets

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

#: Version du FORMAT d'archive. Une archive d'une version inconnue est refusée
#: explicitement, jamais appliquée « au mieux » — restaurer à moitié un boîtier est pire
#: que ne pas le restaurer.
FORMAT = "comroster-backup"
VERSION = 1

#: Phrase de passe : plus exigeante que le mot de passe admin (4 caractères), parce que
#: l'archive quitte le boîtier et peut être copiée sans qu'on le sache.
MIN_PASSPHRASE_LENGTH = 8

KDF_ITERATIONS = 480_000
SALT_BYTES = 16


class BackupError(Exception):
    """Erreur exploitable par l'utilisateur (phrase de passe, format, version)."""


def _key(passphrase, salt):
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt,
                     iterations=KDF_ITERATIONS)
    return base64.urlsafe_b64encode(kdf.derive(passphrase.encode("utf-8")))


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def build_payload(app):
    """Rassemble l'état complet du boîtier. Tout est facultatif : un boîtier neuf n'a
    pas encore d'antenne configurée, et ce n'est pas une erreur."""
    data_dir = app.config["DATA_DIR"]
    storage = app.extensions["storage"]
    antenna = app.extensions["antenna"]

    configs = {}
    configs_dir = app.extensions["configs"].dir
    if os.path.isdir(configs_dir):
        for name in sorted(os.listdir(configs_dir)):
            if name.endswith(".json"):
                content = _read_json(os.path.join(configs_dir, name))
                if content is not None:
                    configs[name] = content

    journal = []
    journal_path = os.path.join(data_dir, "journal.jsonl")
    try:
        with open(journal_path, encoding="utf-8") as fh:
            for line in fh:
                try:
                    journal.append(json.loads(line))
                except ValueError:
                    continue                      # ligne corrompue : ignorée (fail-safe)
    except OSError:
        pass

    return {
        "configs": configs,
        "draft": storage.load_draft(),
        "published": storage.load_published(),
        "settings": _read_json(app.extensions["settings"].path) or {},
        "network": _read_json(app.extensions["netconfig"].path),
        "viewer": _read_json(os.path.join(data_dir, "viewer.json")),
        "admin_secret": _read_json(app.extensions["secret"].secret_path),
        # Identifiants antenne DÉCHIFFRÉS : au repos ils sont scellés par la clé de
        # session du boîtier, qu'un boîtier neuf n'a pas. Les transporter en clair n'est
        # acceptable QUE parce que l'archive entière est chiffrée.
        "antenna": _antenna_payload(antenna),
        "journal": journal,
    }


def _antenna_payload(antenna):
    ip = getattr(antenna, "ip", None)
    if not ip:
        return None
    return {"ip": ip, "password": getattr(antenna, "_password", "") or ""}


def summarize(payload):
    """Ce que l'archive contient, en clair, pour l'annoncer AVANT de restaurer."""
    draft = payload.get("draft") or {}
    network = payload.get("network") or {}
    return {
        "groups": len(draft.get("groups") or []),
        "people": len(draft.get("people") or []),
        "configs": len(payload.get("configs") or {}),
        "has_network": bool(network),
        "network_link": network.get("link"),
        "has_antenna": bool(payload.get("antenna")),
        "has_password": bool(payload.get("admin_secret")),
        "journal": len(payload.get("journal") or []),
    }


def encrypt(payload, passphrase):
    """Enveloppe chiffrée, prête à écrire sur disque."""
    if len(passphrase or "") < MIN_PASSPHRASE_LENGTH:
        raise BackupError(
            f"Phrase de passe : {MIN_PASSPHRASE_LENGTH} caractères minimum."
        )
    salt = secrets.token_bytes(SALT_BYTES)
    token = Fernet(_key(passphrase, salt)).encrypt(
        json.dumps(payload, ensure_ascii=False).encode("utf-8")
    )
    envelope = {
        "format": FORMAT,
        "version": VERSION,
        "kdf": {"name": "pbkdf2-hmac-sha256", "iterations": KDF_ITERATIONS},
        "salt": base64.b64encode(salt).decode(),
        "data": token.decode(),
    }
    return json.dumps(envelope, ensure_ascii=False, indent=2).encode("utf-8")


def decrypt(blob, passphrase):
    """Enveloppe → contenu. Chaque refus dit LAQUELLE des causes s'applique : « archive
    illisible » laisserait l'opérateur retaper indéfiniment une phrase de passe correcte."""
    try:
        envelope = json.loads(blob.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise BackupError("Ce fichier n'est pas une sauvegarde ComRoster.") from exc
    if not isinstance(envelope, dict) or envelope.get("format") != FORMAT:
        raise BackupError("Ce fichier n'est pas une sauvegarde ComRoster.")
    if envelope.get("version") != VERSION:
        raise BackupError(
            f"Sauvegarde en version {envelope.get('version')} — ce boîtier attend la "
            f"version {VERSION}. Mettez le boîtier à jour avant de restaurer."
        )
    try:
        salt = base64.b64decode(envelope["salt"])
        token = envelope["data"].encode()
    except (KeyError, ValueError, AttributeError) as exc:
        raise BackupError("Sauvegarde incomplète ou abîmée.") from exc
    try:
        raw = Fernet(_key(passphrase or "", salt)).decrypt(token)
    except (InvalidToken, ValueError) as exc:
        raise BackupError("Phrase de passe incorrecte.") from exc
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise BackupError("Sauvegarde abîmée.") from exc
    if not isinstance(payload, dict):
        raise BackupError("Sauvegarde abîmée.")
    return payload


def _write_json(path, data, mode=0o600):
    tmp = path + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def apply_payload(app, payload):
    """Écrit l'archive sur le boîtier. Retourne ce qui a été restauré.

    Appelée SOUS `state_lock` par la route : on ne restaure pas pendant qu'une édition
    écrit le brouillon. Chaque élément est facultatif — restaurer une archive faite avant
    la configuration réseau ne doit pas effacer celle du boîtier d'accueil.
    """
    data_dir = app.config["DATA_DIR"]
    storage = app.extensions["storage"]
    restored = []

    draft = payload.get("draft")
    if isinstance(draft, dict):
        storage.save_draft(draft)
        restored.append("brouillon")

    published = payload.get("published")
    if isinstance(published, dict):
        storage.save_published(published)
        app.extensions["broker"].publish("published", published)
        restored.append("état publié")

    settings = payload.get("settings")
    if isinstance(settings, dict) and settings:
        storage.atomic_write(app.extensions["settings"].path, settings)
        restored.append("réglages")

    network = payload.get("network")
    if isinstance(network, dict) and network:
        _write_json(app.extensions["netconfig"].path, network)
        restored.append("réseau")

    viewer = payload.get("viewer")
    if isinstance(viewer, dict) and viewer:
        _write_json(os.path.join(data_dir, "viewer.json"), viewer)
        restored.append("afficheur")

    secret = payload.get("admin_secret")
    if isinstance(secret, dict) and secret.get("password_hash"):
        _write_json(app.extensions["secret"].secret_path, secret)
        restored.append("mot de passe")

    configs = payload.get("configs")
    if isinstance(configs, dict) and configs:
        configs_dir = app.extensions["configs"].dir
        os.makedirs(configs_dir, exist_ok=True)
        for name, content in configs.items():
            # Le nom vient de l'archive : on ne garde que le nom de fichier, jamais un
            # chemin. Sans cela, « ../../etc/x.json » écrirait hors du répertoire.
            safe = os.path.basename(str(name))
            if safe.endswith(".json") and safe not in (".json", ""):
                _write_json(os.path.join(configs_dir, safe), content, mode=0o644)
        restored.append("configurations")

    antenna = payload.get("antenna")
    if isinstance(antenna, dict) and antenna.get("ip"):
        client = app.extensions["antenna"]
        # Re-scellé avec la clé de CE boîtier : l'archive les portait en clair parce
        # qu'elle est chiffrée, mais au repos ils redeviennent illisibles sans la clé.
        client._ip = antenna["ip"]
        client._password = antenna.get("password") or ""
        client._persist()
        restored.append("antenne")

    journal = payload.get("journal")
    if isinstance(journal, list) and journal:
        _merge_journal(app, journal)
        restored.append("journal")

    return restored


def _merge_journal(app, incoming):
    """FUSIONNE le journal de l'archive avec celui du boîtier — sans jamais l'écraser.

    Un journal répond à « que s'est-il passé ? » : le remplacer effacerait les évènements
    du boîtier d'accueil, à commencer par ceux de la restauration en cours. On réunit donc
    les deux, on dédoublonne sur (horodatage, évènement, détail) et on garde les plus
    récents dans la limite du journal. Les horodatages sont en ISO 8601 UTC à zéro
    décalage : l'ordre lexical y vaut l'ordre chronologique.
    """
    journal = app.extensions["journal"]
    fusion = {}
    for entry in list(incoming) + list(journal.entries()):
        if not isinstance(entry, dict):
            continue
        cle = (entry.get("ts", ""), entry.get("event", ""), entry.get("detail", ""))
        fusion.setdefault(cle, entry)
    ordonne = [fusion[k] for k in sorted(fusion)][-journal.MAX_EVENTS:]

    tmp = journal.path + ".tmp"
    with journal._lock:
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.writelines(json.dumps(e, ensure_ascii=False) + "\n" for e in ordonne)
        os.replace(tmp, journal.path)
