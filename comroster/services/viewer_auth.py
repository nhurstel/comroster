"""Code d'appariement de l'agent afficheur (mode 2 Pi).

L'agent expose sur le port 8081 un formulaire qui écrit `viewer.json` ET `network.json` :
n'importe qui sur le LAN pouvait donc repointer l'afficheur vers un serveur arbitraire, ou
lui casser son adresse — sans mot de passe, sans CSRF (audit 2026-07-28).

MODÈLE D'AUTORISATION : la présence physique. L'afficheur AFFICHE son code sur son propre
écran ; le fournir prouve qu'on est dans la salle, ce qui est exactement le droit qu'on
veut accorder à un boîtier de régie. Pas de compte à gérer, rien à retenir entre deux
productions, et l'installateur peut l'imposer d'avance via `COMROSTER_VIEWER_CODE`.

Le code est PERSISTÉ (0600) : il ne change pas à chaque redémarrage, sinon il faudrait
relire l'écran à chaque intervention. Alphabet sans caractères ambigus — il est recopié
depuis un écran, souvent de loin.
"""
import hmac
import json
import logging
import os
import secrets

log = logging.getLogger(__name__)

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"     # ni O/0 ni I/1
CODE_LENGTH = 6


def _generate():
    return "".join(secrets.choice(ALPHABET) for _ in range(CODE_LENGTH))


class ViewerAuth:
    """Code d'appariement, créé au premier démarrage puis conservé."""

    def __init__(self, data_dir, env_code=None):
        self.path = os.path.join(data_dir, "viewer_agent.json")
        self._code = (env_code or "").strip().upper() or None
        if self._code is None:
            self._code = self._load_or_create()

    def _load_or_create(self):
        try:
            with open(self.path, encoding="utf-8") as fh:
                code = (json.load(fh) or {}).get("code")
            if isinstance(code, str) and code.strip():
                return code.strip().upper()
        except (OSError, ValueError, AttributeError):
            pass                       # absent ou corrompu → on en refait un
        code = _generate()
        self._write(code)
        return code

    def _write(self, code):
        try:
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump({"code": code}, fh)
        except OSError as exc:
            # Fail-safe appliance : un code non persisté reste utilisable pour cette
            # session (il est affiché à l'écran), il changera au prochain démarrage.
            log.warning("Code d'appariement non enregistré : %s", exc)

    @property
    def code(self):
        return self._code

    def check(self, submitted):
        """Comparaison à temps constant, insensible à la casse et aux espaces.

        Le code est recopié à la main depuis un écran : refuser « ab cd ef » en minuscules
        serait de la rigueur pour rien, et pousserait à désactiver la protection.
        """
        if not isinstance(submitted, str):
            return False
        cleaned = submitted.strip().upper().replace(" ", "").replace("-", "")
        return hmac.compare_digest(cleaned, self._code)
