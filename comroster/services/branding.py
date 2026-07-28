"""Marque du boîtier : le logo d'un client à la place de celui de ComRoster.

La marque n'est PAS une donnée d'application — ni brouillon, ni état publié, ni contenu de
DATA_DIR. C'est une propriété du boîtier, posée à la fabrication dans un dossier système
que l'application lit et n'écrit jamais.

C'est là tout le verrouillage demandé : le client peut disposer de la totalité de
l'administration, il n'y a rien à atteindre. Ce n'est pas un mot de passe qu'on pourrait
contourner, c'est l'ABSENCE de mutateur. D'où une classe sans aucune méthode d'écriture.

Politique appliance (fail-safe), la même que le carnet de bord : toute faute — dossier
absent, manifeste illisible, logo introuvable, extension interdite — retombe intégralement
sur ComRoster avec un avertissement journalisé. Jamais une exception : un logo mal nommé ne
doit pas empêcher un boîtier de démarrer une heure avant un show.

Chargement UNIQUE au démarrage : la marque ne change pas pendant qu'un show tourne, et
poser un pack implique de toute façon un redémarrage du service (deploy/set-branding.sh).
"""
import json
import logging
import os

log = logging.getLogger(__name__)

#: Formats acceptés pour un logo. Le JPEG est écarté volontairement : sans canal alpha, un
#: logo rend mal sur le fond sombre du tableau. La conversion appartient à la préparation
#: du pack, pas au boîtier.
EXTENSIONS_ADMISES = (".svg", ".png")

MANIFESTE = "brand.json"


class Branding:
    def __init__(self, brand_dir=""):
        self._reset()
        if not brand_dir:
            return
        try:
            self._charger(brand_dir)
        except (OSError, ValueError) as exc:
            log.warning("Pack de marque ignoré (%s) — repli sur ComRoster", exc)
            self._reset()

    def _reset(self):
        self.active = False
        self.name = ""
        self.logo_path = None
        self.print_logo_path = None
        self.mono = False
        self.version = 0

    def _charger(self, brand_dir):
        with open(os.path.join(brand_dir, MANIFESTE), encoding="utf-8") as f:
            manifeste = json.load(f)
        if not isinstance(manifeste, dict):
            raise ValueError("racine du manifeste non-objet")

        nom = (manifeste.get("name") or "").strip()
        if not nom:
            raise ValueError("champ « name » absent ou vide")

        logo = self._resoudre(brand_dir, manifeste.get("logo"))
        logo_print = logo
        if manifeste.get("logo_print"):
            logo_print = self._resoudre(brand_dir, manifeste["logo_print"])

        self.name = nom
        self.logo_path = logo
        self.print_logo_path = logo_print
        self.mono = bool(manifeste.get("mono"))
        # Une seule version pour les deux logos : le pack est posé d'un bloc, la variante
        # papier ne peut pas changer sans l'écran.
        self.version = max(int(os.stat(p).st_mtime) for p in {logo, logo_print})
        self.active = True

    @staticmethod
    def _resoudre(brand_dir, nom_fichier):
        """Transforme un nom déclaré dans le manifeste en chemin absolu vérifié.

        La source est de confiance (le pack est posé en root, à la fabrication), mais on ne
        concatène jamais un chemin non validé : exiger un simple nom de fichier coûte trois
        lignes et ferme définitivement la question de la traversée de répertoire.
        """
        if not nom_fichier or not isinstance(nom_fichier, str):
            raise ValueError("nom de fichier de logo absent")
        if nom_fichier != os.path.basename(nom_fichier):
            raise ValueError(f"« {nom_fichier} » n'est pas un simple nom de fichier")
        extension = os.path.splitext(nom_fichier)[1].lower()
        if extension not in EXTENSIONS_ADMISES:
            raise ValueError(f"extension « {extension} » non autorisée")
        chemin = os.path.join(brand_dir, nom_fichier)
        if not os.path.isfile(chemin):
            raise ValueError(f"fichier « {nom_fichier} » introuvable")
        return chemin
