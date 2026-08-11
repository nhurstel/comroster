"""Les captures du README existent, et aucune ne traîne sans être montrée.

Deux pourritures silencieuses, dans les deux sens :

* une image RÉFÉRENCÉE mais absente du dépôt ne casse rien — GitHub affiche un cadre
  vide, et personne ne relit un README à côté du code (c'est ce qui avait laissé passer
  « mot de passe admin (8 caractères min.) » quand le minimum était retombé à 4) ;
* une image PRÉSENTE mais qu'aucun texte ne montre est du poids mort qu'on n'ose plus
  supprimer, faute de savoir si quelqu'un s'en sert.

Les deux se règlent par la même confrontation, et elle ne coûte rien.
"""
import pathlib
import re

RACINE = pathlib.Path(__file__).resolve().parent.parent
README = RACINE / "README.md"
IMAGES = RACINE / "docs" / "img"

# ![légende](chemin) — on ne garde que les chemins LOCAUX : une URL distante n'est pas
# du ressort de ce test, et sa présence ne dit rien de l'état du dépôt.
_MARKDOWN_IMAGE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")


def _references():
    texte = README.read_text(encoding="utf-8")
    return [c for c in _MARKDOWN_IMAGE.findall(texte) if not c.startswith(("http://", "https://"))]


def test_chaque_image_du_readme_existe():
    manquantes = [c for c in _references() if not (RACINE / c).is_file()]
    assert manquantes == [], f"référencées par le README mais absentes du dépôt : {manquantes}"


def test_aucune_image_du_readme_nest_vide():
    """Un PNG de zéro octet s'affiche comme un cadre cassé, exactement comme un absent.

    Le seuil est délibérément bas : il ne juge pas la qualité de la capture, il attrape
    une écriture interrompue ou un fichier suivi par erreur via Git LFS sans pointeur.
    """
    # `is_file()` d'abord : l'ABSENCE appartient au test précédent. Sans ce filtre, un
    # fichier manquant fait lever un FileNotFoundError ici — deux tests rouges dont un
    # pour la mauvaise raison, et un message qui ne nomme pas le vrai défaut.
    creuses = [c for c in _references()
               if (RACINE / c).is_file() and (RACINE / c).stat().st_size < 1024]
    assert creuses == [], f"images vides ou tronquées : {creuses}"


def test_aucune_capture_orpheline():
    """Toute capture de docs/img est montrée quelque part dans le README.

    Sans cette moitié-ci, supprimer une section du README laisserait son image derrière
    elle, et le prochain lecteur n'aurait aucun moyen de savoir si elle sert encore.
    """
    montrees = {(RACINE / c).resolve() for c in _references()}
    orphelines = sorted(
        p.name for p in IMAGES.glob("*.png") if p.resolve() not in montrees
    )
    assert orphelines == [], (
        f"présentes dans docs/img mais montrées nulle part : {orphelines} — "
        "les référencer dans le README ou les supprimer"
    )
