"""Garde : tout fichier d'état écrit dans DATA_DIR doit être ignoré par git.

Sans ce filet, un fichier d'état ajouté plus tard atterrit à la racine du dépôt (DATA_DIR
vaut le répertoire courant par défaut) et finit committé. C'est arrivé : `lifetime.json`
traînait non suivi, et `network.json` — qui porte le PSK Wi-Fi EN CLAIR — n'était pas
davantage couvert (audit 2026-07-28).

Le test n'énumère pas les noms à la main : il interroge les SERVICES eux-mêmes pour savoir
où ils écrivent, puis délègue le verdict à `git check-ignore`, seul juge des règles réelles
(négations, répertoires, motifs). Réimplémenter la sémantique de .gitignore reviendrait à
tester notre copie plutôt que le fichier.
"""
import os
import subprocess

import pytest

from comroster.services.viewer import ViewerConfig

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _is_git_repo():
    return os.path.isdir(os.path.join(REPO, ".git"))


def _ignored(name):
    return subprocess.run(["git", "check-ignore", "-q", name],
                          cwd=REPO, check=False).returncode == 0


def _state_basenames(app, data_dir):
    """Où chaque service écrit — demandé aux services, jamais recopié à la main."""
    ext = app.extensions
    storage = ext["storage"]
    paths = [
        storage.draft_path,
        storage.published_path,
        storage.history_dir,
        ext["secret"].secret_path,
        ext["antenna"].path,
        ext["netconfig"].path,
        ext["journal"].path,
        ext["lifetime"].path,
        ext["settings"].path,
        ext["configs"].dir,
        # L'agent afficheur (mode 2 Pi) n'est pas monté dans l'app Flask, mais il écrit
        # dans le MÊME DATA_DIR : il compte autant que les autres.
        ViewerConfig(data_dir).path,
    ]
    return sorted({os.path.basename(p) for p in paths})


@pytest.mark.skipif(not _is_git_repo(), reason="hors dépôt git")
def test_gitignore_couvre_tous_les_fichiers_detat(app, tmp_path):
    names = _state_basenames(app, str(tmp_path))
    assert names, "aucun fichier d'état détecté — le test ne prouverait rien"
    non_ignores = [name for name in names if not _ignored(name)]
    assert not non_ignores, (
        "fichiers d'état non couverts par .gitignore : " + ", ".join(non_ignores)
        + " — ils finiront committés (rappel : network.json contient le PSK Wi-Fi)"
    )


@pytest.mark.skipif(not _is_git_repo(), reason="hors dépôt git")
def test_les_sauvegardes_atomiques_sont_ignorees():
    """`atomic_write` laisse des `<chemin>.bak` / `.tmp` : mêmes données, même exigence."""
    for name in ("data_draft.json.bak", "settings.json.tmp"):
        assert _ignored(name), name
