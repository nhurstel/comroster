"""Garde : les scripts de déploiement doivent au moins être syntaxiquement valides.

Un script de terrain n'est lancé qu'une fois, en root, sur un boîtier en préparation —
c'est-à-dire au pire endroit pour découvrir une accolade manquante. `bash -n` analyse sans
exécuter : c'est peu, mais c'est ce qui attrape la faute la plus coûteuse.
"""

import os
import subprocess

import pytest

DEPLOY = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "deploy"
)
SCRIPTS = sorted(f for f in os.listdir(DEPLOY) if f.endswith(".sh"))


@pytest.mark.parametrize("script", SCRIPTS)
def test_la_syntaxe_du_script_est_valide(script):
    r = subprocess.run(
        ["bash", "-n", os.path.join(DEPLOY, script)],
        capture_output=True, text=True, check=False,
    )
    assert r.returncode == 0, r.stderr


def test_le_script_de_marque_existe_et_est_executable():
    """Il est le seul chemin prévu pour poser une marque : s'il disparaît ou perd son bit
    d'exécution, la fonctionnalité n'est plus livrable.

    Le contrôle vise CE script seul, volontairement : `deploy/apply-network.sh` n'a pas
    son bit d'exécution aujourd'hui, et le rendre exécutable n'a rien à voir avec la
    marque client. À traiter séparément si c'est un oubli.
    """
    assert "set-branding.sh" in SCRIPTS
    assert os.access(os.path.join(DEPLOY, "set-branding.sh"), os.X_OK)
