"""Version du logiciel : quel code, exactement, tourne sur ce boîtier.

Le numéro n'est jamais saisi — il est GRAVÉ au déploiement par deploy/setup-pi.sh, qui
interroge git. Un numéro saisi à la main mentirait dès le premier `git pull`
intermédiaire, et sur une appliance un numéro faux est pire que pas de numéro : il
donne une réponse fausse à la seule question qui compte au téléphone.

Fichier `comroster/VERSION`, une ligne, trois champs séparés par une espace :

    v1.4.0+7 9f3c1a2 2026-07-29
    │        │       └── date du commit (YYYY-MM-DD)
    │        └────────── commit court
    └─────────────────── label, DÉJÀ normalisé par le shell

Le label est normalisé une seule fois, côté shell. Si Python le renormalisait de son
côté, l'écran de démarrage (qui lit le même fichier, en shell) et l'onglet Santé
pourraient afficher deux chaînes différentes pour un même code — exactement le genre de
divergence que ce fichier unique existe pour empêcher.

Politique appliance fail-safe, comme services/lifetime.py : fichier absent, vide ou
mal formé ⇒ `known = False` et champs vides, avec un avertissement journalisé. Jamais
d'exception : aucune page ne doit disparaître faute d'un numéro de version.
"""
import logging
import os
import re

log = logging.getLogger(__name__)

#: Le paquet `comroster/` — c'est là que le déploiement grave VERSION. Ce module vit dans
#: `comroster/services/`, d'où les deux remontées.
PAQUET = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: Un label public commence par « v » suivi de majeur.mineur. Tout le reste (identifiant
#: de commit nu, préfixe inhabituel) n'a pas de version publique.
_MAJEUR_MINEUR = re.compile(r"^v(\d+)\.(\d+)")


def _version_publique(label):
    """Le label tronqué à majeur.mineur, pour le seul écran que le client regarde.

    « v1.4 » là où l'administration dit « v1.4.0+7 ». Être MOINS PRÉCIS n'est pas mentir ;
    afficher un numéro inventé le serait. Sans tag, on ne renvoie rien plutôt qu'un
    identifiant de commit, qui ne signifie rien pour un client.
    """
    trouve = _MAJEUR_MINEUR.match(label or "")
    return f"v{trouve.group(1)}.{trouve.group(2)}" if trouve else ""


class Version:
    def __init__(self, package_dir=PAQUET, repo_dir=None):
        self.path = os.path.join(package_dir, "VERSION")
        #: La racine du dépôt, où vit `.git`. Séparée du paquet pour que les tests
        #: puissent les dissocier.
        self.repo_dir = repo_dir if repo_dir is not None else os.path.dirname(package_dir)
        self.label, self.commit, self.date = self._charger()
        self.known = bool(self.label)
        self.public = _version_publique(self.label)
        self.stale = False

    def _charger(self):
        try:
            with open(self.path, encoding="utf-8") as fichier:
                champs = fichier.readline().split()
        except OSError as exc:
            # Le cas normal en développement : pas un incident, d'où `info`.
            log.info("Aucun fichier de version (%s) — version inconnue", exc)
            return "", "", ""
        if len(champs) != 3:
            log.warning(
                "Fichier de version mal formé (%d champ(s) au lieu de 3) — version inconnue",
                len(champs),
            )
            return "", "", ""
        return champs[0], champs[1], champs[2]

    def snapshot(self):
        """Ce que l'onglet Santé reçoit via /api/health."""
        return {
            "known": self.known,
            "label": self.label,
            "commit": self.commit,
            "date": self.date,
            "public": self.public,
            "stale": self.stale,
        }
