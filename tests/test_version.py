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


def test_fichier_corrompu_donne_une_version_inconnue(tmp_path):
    """Cas de la carte SD qui se corrompt lors d'une coupure de courant : des octets
    non-UTF-8 dans le fichier VERSION levaient UnicodeDecodeError, cassant le constructeur.
    Avec la politique fail-safe, aucune exception ne doit remonter."""
    (tmp_path / "VERSION").write_bytes(b"v1.4.0+7 \xff\xfe 2026-07-29\n")
    v = Version(str(tmp_path))
    assert v.known is False
    assert v.label == "" and v.commit == "" and v.date == ""
    assert v.public == ""


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


# ---------- Garde de fraîcheur ----------

SHA = "9f3c1a2b8e4d5f6a7c8b9d0e1f2a3b4c5d6e7f80"


def _depot(tmp_path, head, refs=None, packed=None):
    """Un faux dépôt : juste les fichiers que la garde sait lire, rien de plus.

    On ne lance jamais git — ni ici, ni en production. Sur un boîtier, l'exécutable peut
    très bien ne pas être installé.
    """
    paquet = tmp_path / "comroster"
    paquet.mkdir()
    (paquet / "VERSION").write_text("v1.4.0 9f3c1a2 2026-07-29\n", encoding="utf-8")
    git = tmp_path / ".git"
    git.mkdir()
    (git / "HEAD").write_text(head, encoding="utf-8")
    for nom, sha in (refs or {}).items():
        cible = git / nom
        cible.parent.mkdir(parents=True, exist_ok=True)
        cible.write_text(sha + "\n", encoding="utf-8")
    if packed is not None:
        (git / "packed-refs").write_text(packed, encoding="utf-8")
    return Version(str(paquet), repo_dir=str(tmp_path))


def test_code_a_jour_n_est_pas_signale(tmp_path):
    v = _depot(tmp_path, "ref: refs/heads/main\n", refs={"refs/heads/main": SHA})
    assert v.stale is False


def test_code_modifie_depuis_le_deploiement_est_signale(tmp_path):
    """Le cas qu'on veut attraper : `git pull` sans relancer deploy/setup-pi.sh."""
    autre = "0000000aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    v = _depot(tmp_path, "ref: refs/heads/main\n", refs={"refs/heads/main": autre})
    assert v.stale is True


def test_tete_detachee_resolue(tmp_path):
    """`.git/HEAD` porte alors le SHA directement, sans passer par une référence."""
    assert _depot(tmp_path, SHA + "\n").stale is False


def test_reference_compactee_resolue(tmp_path):
    """`git gc` déplace les références dans packed-refs et supprime le fichier
    refs/heads/main. Sans ce repli, la garde s'éteindrait en silence sur tout dépôt
    un peu ancien — une garde éteinte sans le dire est pire qu'une garde absente."""
    v = _depot(tmp_path, "ref: refs/heads/main\n",
               packed=f"# pack-refs with: peeled fully-peeled sorted \n{SHA} refs/heads/main\n")
    assert v.stale is False


def test_sans_depot_git_aucun_soupcon(tmp_path):
    """Cas d'un boîtier installé par copie d'image : on ne peut pas savoir, donc on
    n'invente pas un doute."""
    paquet = tmp_path / "comroster"
    paquet.mkdir()
    (paquet / "VERSION").write_text("v1.4.0 9f3c1a2 2026-07-29\n", encoding="utf-8")
    assert Version(str(paquet), repo_dir=str(tmp_path)).stale is False


def test_git_en_fichier_worktree_aucun_soupcon(tmp_path):
    """Dans un worktree git, `.git` est un FICHIER qui pointe ailleurs. Configuration
    inexistante sur un boîtier, courante sur un poste de développement : elle ne doit
    pas produire d'erreur."""
    paquet = tmp_path / "comroster"
    paquet.mkdir()
    (paquet / "VERSION").write_text("v1.4.0 9f3c1a2 2026-07-29\n", encoding="utf-8")
    (tmp_path / ".git").write_text("gitdir: /ailleurs/.git/worktrees/x\n", encoding="utf-8")
    assert Version(str(paquet), repo_dir=str(tmp_path)).stale is False


def test_version_inconnue_n_est_jamais_perimee(tmp_path):
    """Sans commit gravé, il n'y a rien à comparer : « inconnue » se suffit, l'affubler
    d'un « incertaine » n'ajouterait que du bruit."""
    paquet = tmp_path / "comroster"
    paquet.mkdir()
    git = tmp_path / ".git"
    git.mkdir()
    (git / "HEAD").write_text(SHA + "\n", encoding="utf-8")
    v = Version(str(paquet), repo_dir=str(tmp_path))
    assert v.known is False and v.stale is False
