"""Version du logiciel : lecture du fichier gravé, et ce qu'on en montre au client."""
from comroster.services.version import Version


def _graver(tmp_path, ligne):
    (tmp_path / "VERSION").write_text(ligne, encoding="utf-8")
    return Version(str(tmp_path))


def test_lecture_nominale(tmp_path):
    v = _graver(tmp_path, "v1.4.0+7 9f3c1a2 2026-07-29\n")
    assert v.known is True
    assert v.label == "v1.4.0+7"
    assert v.commit == "9f3c1a2"
    assert v.date == "2026-07-29"


def test_fichier_absent_donne_une_version_inconnue(tmp_path):
    """Cas du poste de développement, et de toute installation qui n'est pas passée par
    deploy/setup-pi.sh. Ne doit rien casser : une page ne disparaît pas faute de numéro."""
    v = Version(str(tmp_path))
    assert v.known is False
    assert v.label == "" and v.commit == "" and v.date == ""
    assert v.public == ""


def test_fichier_vide_ou_tronque_donne_une_version_inconnue(tmp_path):
    """Mieux vaut « inconnue » qu'un numéro partiel : un demi-numéro se lit comme un
    numéro entier et induit en erreur au téléphone."""
    for ligne in ("", "\n", "v1.4.0+7\n", "v1.4.0+7 9f3c1a2\n"):
        assert _graver(tmp_path, ligne).known is False


def test_champs_surnumeraires_refuses(tmp_path):
    """Un quatrième champ signale un format qu'on ne comprend pas : on ne devine pas."""
    assert _graver(tmp_path, "v1.4.0 9f3c1a2 2026-07-29 extra\n").known is False


def test_version_publique_tronquee_a_majeur_mineur(tmp_path):
    """Ce que voit le CLIENT au pied de l'écran : moins précis, jamais faux."""
    assert _graver(tmp_path, "v1.4.0+7 9f3c1a2 2026-07-29\n").public == "v1.4"
    assert _graver(tmp_path, "v1.4.0 9f3c1a2 2026-07-29\n").public == "v1.4"
    assert _graver(tmp_path, "v2.0.0 9f3c1a2 2026-07-29\n").public == "v2.0"


def test_sans_tag_il_n_y_a_pas_de_version_publique(tmp_path):
    """`git describe --always` retombe sur l'identifiant du commit quand aucun tag
    n'existe. Afficher « 9f3c1a2 » à un client ne veut rien dire pour lui : le pied de
    l'écran doit alors rester exactement ce qu'il était."""
    v = _graver(tmp_path, "9f3c1a2 9f3c1a2 2026-07-29\n")
    assert v.known is True          # l'admin, elle, a bien une information exploitable
    assert v.label == "9f3c1a2"
    assert v.public == ""


def test_snapshot_porte_toutes_les_cles_attendues(tmp_path):
    """L'onglet Santé lit ce dictionnaire tel quel : une clé manquante y devient un
    « undefined » silencieux à l'écran."""
    snap = _graver(tmp_path, "v1.4.0+7 9f3c1a2 2026-07-29\n").snapshot()
    assert set(snap) == {"known", "label", "commit", "date", "public", "stale"}
