"""Espacement des copies `.bak` du brouillon — usure de la carte SD.

Le brouillon est réenregistré à chaque salve de frappe. Copier intégralement le fichier à
chaque fois produisait, sur une saisie soutenue, plusieurs copies par seconde sur la SD du
boîtier — alors que le carnet de bord, lui, n'écrit que toutes les 5 minutes pour cette
raison exacte (audit 2026-07-28).

Ce qui doit rester vrai : l'ÉCRITURE est toujours atomique et durable ; seule la COPIE de
sauvegarde s'espace. Et les états qui comptent (publié, historique, configurations) gardent
leur sauvegarde systématique.
"""
import json
import os

from comroster.services.storage import Storage


def _write(storage, path, value, **kw):
    storage.atomic_write(path, {"v": value}, **kw)


def test_sans_intervalle_chaque_ecriture_sauvegarde(tmp_path):
    storage = Storage(str(tmp_path))
    path = os.path.join(str(tmp_path), "x.json")
    _write(storage, path, 1)
    _write(storage, path, 2)
    with open(path + ".bak", encoding="utf-8") as fh:
        assert json.load(fh)["v"] == 1, "le .bak doit porter l'AVANT-dernier état"
    _write(storage, path, 3)
    with open(path + ".bak", encoding="utf-8") as fh:
        assert json.load(fh)["v"] == 2


def test_avec_intervalle_la_sauvegarde_ne_se_refait_pas_en_rafale(tmp_path):
    storage = Storage(str(tmp_path))
    path = os.path.join(str(tmp_path), "draft.json")
    _write(storage, path, 1)                                  # pas de .bak : rien à sauver
    assert not os.path.exists(path + ".bak")

    _write(storage, path, 2, backup_min_interval=300)         # 1re sauvegarde : due
    assert os.path.exists(path + ".bak")
    for n in range(3, 20):                                    # la rafale qui suit
        _write(storage, path, n, backup_min_interval=300)

    with open(path + ".bak", encoding="utf-8") as fh:
        assert json.load(fh)["v"] == 1, (
            "le .bak a été réécrit pendant la rafale — l'espacement ne sert à rien"
        )


def test_l_ecriture_reste_atomique_et_complete_meme_sans_sauvegarde(tmp_path):
    """L'espacement ne touche QUE la copie : le fichier principal est toujours à jour."""
    storage = Storage(str(tmp_path))
    path = os.path.join(str(tmp_path), "draft.json")
    for n in range(10):
        _write(storage, path, n, backup_min_interval=300)
    with open(path, encoding="utf-8") as fh:
        assert json.load(fh)["v"] == 9
    assert not os.path.exists(path + ".tmp"), "aucun temporaire ne doit subsister"


def test_le_brouillon_espace_sa_sauvegarde_mais_pas_le_publie(tmp_path):
    """Le chemin réel : save_draft espace, save_published non."""
    storage = Storage(str(tmp_path))
    for n in range(6):
        storage.save_draft({"version": 1, "n": n})
    with open(storage.draft_path + ".bak", encoding="utf-8") as fh:
        assert json.load(fh)["n"] == 0, "le brouillon ne doit pas resauvegarder en rafale"

    for n in range(3):
        storage.save_published({"version": 1, "n": n})
    with open(storage.published_path + ".bak", encoding="utf-8") as fh:
        assert json.load(fh)["n"] == 1, (
            "le publié s'écrit sur action explicite : il garde sa sauvegarde systématique"
        )


def test_une_sauvegarde_perimee_est_refaite(tmp_path):
    """L'espacement borne l'ÂGE du .bak, il ne le fige pas."""
    storage = Storage(str(tmp_path))
    path = os.path.join(str(tmp_path), "draft.json")
    _write(storage, path, 1)
    _write(storage, path, 2, backup_min_interval=300)
    # On vieillit artificiellement la sauvegarde de 10 minutes.
    old = os.stat(path + ".bak").st_mtime - 600
    os.utime(path + ".bak", (old, old))
    _write(storage, path, 3, backup_min_interval=300)
    with open(path + ".bak", encoding="utf-8") as fh:
        assert json.load(fh)["v"] == 2, "la sauvegarde périmée aurait dû être refaite"
