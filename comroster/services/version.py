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
        self.stale = self._est_perimee()

    def _charger(self):
        try:
            with open(self.path, encoding="utf-8") as fichier:
                champs = fichier.readline().split()
        except OSError as exc:
            # Le cas normal en développement : pas un incident, d'où `info`.
            log.info("Aucun fichier de version (%s) — version inconnue", exc)
            return "", "", ""
        except ValueError as exc:
            # Fichier illisible : encoding incorrect, corruption (ex. coupure de courant
            # sur la gravure). Mieux vaut « inconnue » qu'une exception qui casserait l'écran.
            log.warning("Fichier de version illisible (%s) — version inconnue", exc)
            return "", "", ""
        if len(champs) != 3:
            log.warning(
                "Fichier de version mal formé (%d champ(s) au lieu de 3) — version inconnue",
                len(champs),
            )
            return "", "", ""
        return champs[0], champs[1], champs[2]

    # ---------- garde de fraîcheur ----------
    def _est_perimee(self):
        """Le code déployé correspond-il encore à ce que dit le dépôt ?

        Comparaison de VALEURS, pas de dates. Comparer le `mtime` de `.git/index` serait
        plus court et FAUX : `git status` réécrit l'index dès qu'un horodatage de fichier
        de travail a changé, sans qu'une ligne de code ait bougé. La garde crierait au
        loup, et une garde qui crie au loup finit ignorée.

        Aucune commande git n'est lancée : que de la lecture de fichiers. Sur un boîtier,
        l'exécutable git peut ne pas être installé du tout.

        Tout ce qu'on ne sait pas lire ⇒ False. On n'invente pas un doute.
        """
        if not self.commit:
            return False
        tete = self._sha_de_la_tete()
        return bool(tete) and not tete.startswith(self.commit)

    def _sha_de_la_tete(self):
        git = os.path.join(self.repo_dir, ".git")
        # Un `.git` FICHIER (worktree git) pointe ailleurs : on renonce sans erreur.
        if not os.path.isdir(git):
            return ""
        tete = _premiere_ligne(os.path.join(git, "HEAD"))
        if not tete.startswith("ref:"):
            return tete                     # tête détachée : le SHA est écrit directement
        reference = tete[len("ref:"):].strip()
        return (_premiere_ligne(os.path.join(git, reference))
                or _reference_compactee(git, reference))

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


def _premiere_ligne(path):
    try:
        with open(path, encoding="utf-8") as fichier:
            return fichier.readline().strip()
    except OSError:
        return ""


def _reference_compactee(git_dir, reference):
    """`git gc` déplace les références dans `.git/packed-refs` et supprime les fichiers
    individuels. Sans ce repli, la garde s'éteindrait silencieusement sur tout dépôt
    ayant subi un ramasse-miettes."""
    try:
        with open(os.path.join(git_dir, "packed-refs"), encoding="utf-8") as fichier:
            for ligne in fichier:
                morceaux = ligne.split()
                if len(morceaux) == 2 and morceaux[1] == reference:
                    return morceaux[0]
    except OSError:
        pass
    return ""
