import json
import os
import secrets

from werkzeug.security import check_password_hash, generate_password_hash


#: Alphabet du code de récupération, SANS caractères ambigus : ni I, ni O, ni 0,
#: ni 1. C'est le seul texte du produit qu'un humain recopie à la main, et un
#: caractère faux ferme le boîtier définitivement — la lisibilité tient donc à
#: l'alphabet, à la source, plutôt qu'à la police qui l'affiche. Constante de
#: module et non variable locale pour que cet invariant soit vérifiable.
ALPHABET_CODE = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _gen_recovery_code():
    # 4 groupes de 4 caractères, tirés de l'alphabet non ambigu ci-dessus.
    return "-".join(
        "".join(secrets.choice(ALPHABET_CODE) for _ in range(4)) for _ in range(4)
    )


class SecretStore:
    def __init__(self, data_dir):
        os.makedirs(data_dir, exist_ok=True)
        self.secret_path = os.path.join(data_dir, "admin_secret.json")

    def is_configured(self):
        return os.path.exists(self.secret_path)

    def _write(self, data):
        payload = json.dumps(data, ensure_ascii=False, indent=2)
        fd = os.open(self.secret_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(payload)
        os.chmod(self.secret_path, 0o600)

    def _read(self):
        with open(self.secret_path, encoding="utf-8") as fh:
            return json.load(fh)

    def setup(self, password):
        if self.is_configured():
            raise RuntimeError("Admin déjà configuré")
        code = _gen_recovery_code()
        self._write({
            "password_hash": generate_password_hash(password),
            "recovery_hash": generate_password_hash(code),
        })
        return code

    def verify_password(self, password):
        if not self.is_configured():
            return False
        return check_password_hash(self._read()["password_hash"], password)

    def change_password(self, current_password, new_password):
        """Rotation du mot de passe par quelqu'un qui connaît l'actuel.

        Le code de récupération est CONSERVÉ, délibérément : c'est toute la différence
        avec `recover()`. Sans ce chemin, changer de mot de passe imposait de brûler son
        code de récupération — donc d'en noter un nouveau et de le rediffuser. Un boîtier
        qui passe d'une production à l'autre n'avait aucun moyen de rotation
        (audit 2026-07-28).
        """
        if not self.is_configured():
            raise ValueError("Non configuré")
        data = self._read()
        if not check_password_hash(data["password_hash"], current_password):
            raise ValueError("Mot de passe actuel incorrect")
        data["password_hash"] = generate_password_hash(new_password)
        self._write(data)

    def recover(self, recovery_code, new_password):
        if not self.is_configured():
            raise ValueError("Non configuré")
        data = self._read()
        if not check_password_hash(data["recovery_hash"], recovery_code):
            raise ValueError("Code de récupération invalide")
        new_code = _gen_recovery_code()
        self._write({
            "password_hash": generate_password_hash(new_password),
            "recovery_hash": generate_password_hash(new_code),
        })
        return new_code
