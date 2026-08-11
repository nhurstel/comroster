"""Régénère les captures d'écran du README.

    .venv/bin/python tools/captures.py

Pourquoi un script commité plutôt qu'une poignée de PNG déposés à la main : une capture
qu'on ne sait pas refaire se périme en silence, et personne ne relit une image à côté du
code. Ici, une commande la reconstruit — et si l'interface change, la différence saute
aux yeux au prochain passage.

Trois partis pris, chacun payé par une erreur passée :

* **Résolution réelle.** L'écran de régie est rendu en 1920×1080, la résolution du kiosk
  Pi, parce que le nombre de colonnes dépend de la largeur en pixels (`minmax(340px, 1fr)`).
  Capturer à une taille commode donnerait une image fidèle à rien.
* **Jeu de données représentatif.** Six groupes, une trentaine de beltpacks, et des
  couleurs prises dans la palette bornée du produit — dont des teintes claires ET sombres,
  pour que les deux sorties de la règle d'encre soient visibles. Un échantillon trop petit
  ou trop neutre n'exerce pas ce qu'on veut montrer.
* **Souris écartée avant chaque prise.** Playwright laisse le curseur où le dernier clic
  l'a posé, et ce point survit à la navigation : sans cela on photographie un `:hover`
  en croyant voir l'état de repos.
"""
import pathlib
import shutil
import socket
import sys
import threading

from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server

RACINE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from comroster import create_app  # noqa: E402
from comroster.services.model import build_draft  # noqa: E402
from comroster.services.storage import Storage  # noqa: E402

SORTIE = RACINE / "docs" / "img"
MOT_DE_PASSE = "captures-doc-8"

# Un plateau plausible de spectacle. Les couleurs viennent de GROUP_PALETTE (admin.js) :
# on prend volontairement des teintes claires (jaune, vert tendre, cyan) et sombres
# (grenat, bleu nuit) pour que l'apparence `grille`, qui pose le texte SUR la couleur,
# montre ses deux encres — noire sur clair, blanche sur sombre.
SPECTACLE = {
    # Le titre (haut-gauche) et le nom de production (centré) sont DEUX champs distincts.
    # Leur donner la même valeur affiche « Carmen » deux fois dans le même bandeau : un
    # défaut de composition que ni l'un ni l'autre ne porte, et qu'aucun test ne voit.
    "title": "Théâtre des Célestins",
    "subtitle": "Générale — jeudi 20h30",
    "production_name": "Carmen",
    "theme": "night",
    "groups": [
        ("Régie", "#2C4C8E", ["Régie générale", "Régie plateau", "Assistant"]),
        ("Plateau", "#9B2F2F", ["Chef machiniste", "Machiniste cour", "Machiniste jardin",
                                "Cintrier", "Accessoires"]),
        ("Lumière", "#E4B93C", ["Chef électro", "Pupitreur", "Poursuite cour",
                                "Poursuite jardin", "Électro"]),
        ("Son", "#8FBF52", ["Ingénieur son", "Retours", "HF plateau"]),
        ("Vidéo", "#7FC8D6", ["Chef vidéo", "Projection", "Captation"]),
        ("Habillage", "#8B7CC8", ["Chef habilleuse", "Habilleuse cour", "Habilleuse jardin",
                                  "Maquillage"]),
    ],
    # Quelques beltpacks non affectés : c'est l'état réel d'un plateau en préparation,
    # et c'est la réserve que montre l'écran d'administration.
    "reserve": ["Régisseur son", "Renfort plateau", "Stagiaire"],
}


def _plateau():
    """Construit l'état publié : groupes colorés + beltpacks numérotés par dizaine."""
    groupes, gens, numero = [], [], 10
    for index, (nom, couleur, roles) in enumerate(SPECTACLE["groups"]):
        gid = f"g{index}"
        groupes.append({"id": gid, "name": nom, "color": couleur, "order": index})
        for role in roles:
            gens.append({"beltpack": str(numero), "role": role, "group_id": gid})
            numero += 1
        numero = (numero // 10 + 1) * 10          # une dizaine par groupe : 10, 20, 30…
    for role in SPECTACLE["reserve"]:
        gens.append({"beltpack": str(numero), "role": role, "group_id": None})
        numero += 1
    return groupes, gens


def _etat(skin):
    groupes, gens = _plateau()
    return build_draft({
        "title": SPECTACLE["title"],
        "subtitle": SPECTACLE["subtitle"],
        "production_name": SPECTACLE["production_name"],
        "theme": SPECTACLE["theme"],
        "skin": skin,
        "groups": groupes,
        "people": gens,
    })


def _port_libre():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _ecrire(dossier, skin):
    """Pose le même plateau en brouillon ET en publié — l'admin lit l'un, l'écran l'autre.

    On passe par le SERVICE et non par des noms de fichiers recopiés : ils s'appellent
    `data_draft.json` / `data_published.json`, ce que j'avais d'abord deviné de travers.
    Un chemin réécrit à la main dérive silencieusement au premier renommage.
    """
    etat = _etat(skin)
    magasin = Storage(str(dossier))
    magasin.save_draft(etat)
    magasin.save_published(etat)


def _prendre(page, chemin):
    """Capture après avoir écarté la souris : sans cela on photographie un `:hover`."""
    page.mouse.move(4, 4)
    page.wait_for_timeout(400)
    page.screenshot(path=str(chemin))
    print(f"  {chemin.relative_to(RACINE)}")


def main():
    SORTIE.mkdir(parents=True, exist_ok=True)
    donnees = RACINE / ".captures-tmp"
    donnees.mkdir(exist_ok=True)
    _ecrire(donnees, "basique")

    app = create_app({"DATA_DIR": str(donnees), "SECRET_KEY": "captures", "DEBUG": True})
    port = _port_libre()
    serveur = make_server("127.0.0.1", port, app, threaded=True)
    fil = threading.Thread(target=serveur.serve_forever, daemon=True)
    fil.start()
    base = f"http://127.0.0.1:{port}"

    try:
        with sync_playwright() as p:
            navigateur = p.chromium.launch()

            # L'ADMINISTRATION D'ABORD, et pas par confort : tant qu'aucun mot de passe
            # n'est défini, la box est « neuve » et /display affiche le guide d'accueil
            # avec son QR au lieu du tableau. Capturer l'écran de régie avant la
            # configuration initiale photographierait l'onboarding.
            bureau = navigateur.new_context(viewport={"width": 1440, "height": 900})
            admin = bureau.new_page()
            admin.goto(base + "/admin/setup")
            admin.fill("input[name=password]", MOT_DE_PASSE)
            admin.click("button[type=submit]")
            admin.click("a.auth-go")                  # « Accéder à l'administration »
            admin.wait_for_selector("#blocks-container .admin-block")
            _prendre(admin, SORTIE / "administration.png")
            bureau.close()

            # L'écran de régie, dans ses trois apparences, à la résolution du kiosk.
            # LA PORTE D'ENTRÉE, dans les deux thèmes. Le générateur l'ignorait,
            # et c'est précisément là qu'un défaut a échappé à toute la suite :
            # un champ cerclé de la couleur d'erreur au repos ne fait tomber
            # aucune assertion. Une capture le montre en une image.
            for theme in ("dark", "light"):
                porte = navigateur.new_context(
                    viewport={"width": 1440, "height": 900}, color_scheme=theme)
                page = porte.new_page()
                page.goto(base + "/admin/login")
                page.wait_for_selector(".auth-form")
                _prendre(page, SORTIE / f"connexion-{theme}.png")
                porte.close()

            regie = navigateur.new_context(viewport={"width": 1920, "height": 1080})
            ecran = regie.new_page()
            for skin in ("basique", "lineaire", "grille"):
                _ecrire(donnees, skin)
                ecran.goto(base + "/display")
                ecran.wait_for_selector("#display-grid .person")
                # La transition d'arrivée doit être finie, sinon on fige une opacité
                # intermédiaire : on attend que l'attribut d'animation soit retombé.
                ecran.wait_for_function(
                    "() => !document.getElementById('display-grid').dataset.anim")
                _prendre(ecran, SORTIE / f"ecran-{skin}.png")
            regie.close()

            navigateur.close()
    finally:
        serveur.shutdown()
        serveur.server_close()
        fil.join(timeout=5)
        # `rmtree` et non une boucle d'`unlink` : l'application crée des SOUS-DOSSIERS
        # (configs, sauvegardes). Une boucle plate y échoue — et son exception masque
        # alors celle qui a réellement fait tomber la génération.
        shutil.rmtree(donnees, ignore_errors=True)


if __name__ == "__main__":
    main()
