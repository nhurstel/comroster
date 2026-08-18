"""Garde : les versions de Python supportées sont déclarées à UN endroit, et suivies partout.

Pourquoi ce fichier existe. Le 2026-08-16, la CI s'est mise à tester Python 3.11 parce que
c'est ce que le boîtier exécute. Cette décision vivait alors dans trois endroits qui
s'ignoraient : la matrice de `ci.yml`, la version du job e2e, et — nulle part — un
`requires-python`. Rien n'empêchait qu'on relève l'un sans les autres, et l'écart n'aurait
été visible qu'en production, sur un Raspberry Pi, un soir de montage.

Le plancher n'est pas un goût : il est DÉDUIT de la cible de déploiement. Raspberry Pi OS
Bookworm embarque Python 3.11, et `deploy/setup-pi.sh` crée le venv du boîtier avec le
`python3` du système. Le jour où `deploy/` visera Trixie (Debian 13, Python 3.13), c'est ce
test qui le rappellera — au lieu qu'on s'en aperçoive à l'usage.
"""
import os
import re
import tomllib

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PYPROJECT = os.path.join(RACINE, "pyproject.toml")
CI = os.path.join(RACINE, ".github", "workflows", "ci.yml")
DOC_PI = os.path.join(RACINE, "deploy", "raspberry-pi.md")

#: Python embarqué par chaque base Debian, donc par le Raspberry Pi OS correspondant.
#: C'est l'ancrage de tout le reste : le plancher du projet est celui de sa cible.
#: Bookworm = Debian 12 → 3.11. Trixie = Debian 13 → 3.13 (Pi OS Trixie, octobre 2025).
PYTHON_PAR_BASE = {"bookworm": "3.11", "trixie": "3.13"}


def _cle(version):
    """« 3.11 » → (3, 11), pour comparer des versions au lieu de comparer des chaînes.

    Sans ça, « 3.9 » passerait pour plus grand que « 3.11 » — le genre de comparaison
    lexicale qui rend un test faussement vert.
    """
    return tuple(int(n) for n in version.split("."))


def _lire(chemin):
    with open(chemin, encoding="utf-8") as fh:
        return fh.read()


def _plancher_declare():
    """Le plancher de `requires-python`, lu dans pyproject.toml (tomllib, stdlib ≥ 3.11)."""
    with open(PYPROJECT, "rb") as fh:
        exigence = tomllib.load(fh)["project"]["requires-python"]
    trouve = re.fullmatch(r">=\s*(\d+\.\d+)", exigence.strip())
    assert trouve, (
        f"requires-python vaut « {exigence} » : ce test ne sait lire qu'une forme « >=X.Y ». "
        "Si la contrainte se complique, c'est ce test qu'il faut étendre — pas contourner."
    )
    return trouve.group(1)


def _matrice_ci():
    """Les versions de la matrice du job `unit`."""
    trouve = re.search(r"matrix:\s*\n\s*python:\s*\[([^\]]+)\]", _lire(CI))
    assert trouve, "matrice python introuvable dans ci.yml — le test ne prouverait rien"
    return re.findall(r"\d+\.\d+", trouve.group(1))


def _versions_figees():
    """Toute version LITTÉRALE de ci.yml — celle du job `unit` est une expression de matrice
    (`${{ matrix.python }}`) et n'apparaît donc pas ici.

    Il y en a plusieurs (lint, e2e) et c'est très bien : ce qui compte n'est pas leur
    nombre mais qu'elles soient TOUTES celle du boîtier. Exiger l'unicité, comme le faisait
    la première version de ce test, aurait interdit d'ajouter un job sans rien prouver de
    plus — et son premier échec venait de là, pas d'un vrai défaut du workflow.
    """
    versions = re.findall(r'python-version:\s*"(\d+\.\d+)"', _lire(CI))
    assert versions, "aucune version littérale dans ci.yml — le test ne prouverait rien"
    return versions


def _base_visee_par_le_deploiement():
    """La base Debian que `deploy/` documente comme cible, et elle seule."""
    texte = _lire(DOC_PI).lower()
    citees = {base for base in PYTHON_PAR_BASE if base in texte}
    assert len(citees) == 1, (
        f"deploy/raspberry-pi.md cite {sorted(citees) or 'aucune base connue'} : la cible "
        "doit être unique pour que le plancher Python s'en déduise. Si une migration est "
        "en cours, trancher la cible AVANT de relever la matrice."
    )
    return citees.pop()


def test_le_plancher_declare_est_celui_de_la_cible_de_deploiement():
    """Le test qui empêche la dérive : c'est le boîtier qui décide, pas nos préférences."""
    base = _base_visee_par_le_deploiement()
    attendu = PYTHON_PAR_BASE[base]
    assert _plancher_declare() == attendu, (
        f"deploy/ vise Raspberry Pi OS {base.capitalize()}, qui embarque Python {attendu}, "
        f"or requires-python déclare un plancher de {_plancher_declare()}. Relever ou "
        "abaisser le plancher — et la matrice de ci.yml avec lui."
    )


def test_le_plancher_est_le_premier_cran_de_la_matrice():
    matrice = _matrice_ci()
    plancher = _plancher_declare()
    assert min(matrice, key=_cle) == plancher, (
        f"requires-python déclare {plancher}, la matrice commence à "
        f"{min(matrice, key=_cle)} ({matrice}). Une version supportée mais jamais testée "
        "n'est pas supportée."
    )


def test_les_jobs_hors_matrice_tournent_sur_le_python_du_boitier():
    """Les jobs qui ne balaient pas la matrice tournent sur UNE version : celle du client.

    Les e2e sont la seule suite qui traverse tout le produit ; les faire tourner ailleurs
    que sur la version du boîtier leur retire l'essentiel de leur valeur. Le lint suit la
    même règle, pour que la version de Python ne soit jamais un choix de circonstance.
    """
    plancher = _plancher_declare()
    dissidentes = sorted({v for v in _versions_figees() if v != plancher})
    assert not dissidentes, (
        f"ci.yml fige {dissidentes} alors que le boîtier exécute {plancher}. Une version "
        "écrite en dur dans un job finit toujours par être celle qu'on avait sous la main."
    )


def test_la_matrice_ne_saute_aucune_version():
    """Une matrice à trous laisserait une version « supportée » sans jamais l'exécuter."""
    versions = sorted(_matrice_ci(), key=_cle)
    attendues = [f"3.{n}" for n in range(_cle(versions[0])[1], _cle(versions[-1])[1] + 1)]
    assert versions == attendues, (
        f"la matrice {versions} saute des versions : attendu la suite continue {attendues}. "
        "Un trou signifie qu'on annonce un intervalle qu'on ne vérifie pas."
    )
