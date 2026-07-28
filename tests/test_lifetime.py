"""Carnet de bord : cumul de fonctionnement, démarrages, première mise en service."""
import json

from comroster.services.lifetime import Lifetime


def test_premiere_mise_en_service_horodatee(tmp_path):
    life = Lifetime(str(tmp_path))
    life.register_start()
    snap = life.snapshot()
    assert snap["installed_at"]          # posé au tout premier démarrage
    assert snap["starts"] == 1
    assert snap["total_runtime_s"] >= 0


def test_le_cumul_survit_aux_redemarrages(tmp_path):
    """Le cumul REPREND là où il s'était arrêté : c'est tout l'intérêt face à
    /proc/uptime, remis à zéro à chaque coupure."""
    first = Lifetime(str(tmp_path))
    first.register_start()
    first._base_runtime = 7200                # simule 2 h déjà accumulées
    first.checkpoint()

    second = Lifetime(str(tmp_path))          # nouveau processus, même boîtier
    installed = first.snapshot()["installed_at"]
    second.register_start()
    snap = second.snapshot()
    assert snap["total_runtime_s"] >= 7200    # le passé n'est pas perdu
    assert snap["starts"] == 2                # et le démarrage est compté
    assert snap["installed_at"] == installed  # la date d'origine ne bouge jamais


def test_fichier_corrompu_repart_a_zero_sans_planter(tmp_path):
    """Politique appliance : récupérer plutôt que planter (cf. leçon 2026-06-22).
    Un carnet illisible ne doit pas rendre la page Santé inaccessible."""
    (tmp_path / "lifetime.json").write_text("{ceci n'est pas du json", encoding="utf-8")

    life = Lifetime(str(tmp_path))
    life.register_start()
    assert life.snapshot()["starts"] == 1
    assert (tmp_path / "lifetime.json.bak").exists()      # la pièce à conviction est gardée


def test_le_point_de_reprise_est_relisible(tmp_path):
    life = Lifetime(str(tmp_path))
    life.register_start()
    life.checkpoint()
    with open(tmp_path / "lifetime.json", encoding="utf-8") as f:
        data = json.load(f)
    assert set(data) >= {"installed_at", "starts", "total_runtime_s", "last_seen_at"}


def test_expose_dans_la_sante(app):
    """La page Santé lit le carnet via /api/health : sans cette clé, les statistiques
    temporelles disparaîtraient en silence de l'écran."""
    from comroster.services import health
    snap = health.snapshot(app)
    assert "lifetime" in snap
    assert snap["lifetime"]["starts"] >= 1
