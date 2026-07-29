"""Version du logiciel : lecture du fichier gravé, et ce qu'on en montre au client."""
import os
import re
import subprocess

import pytest

from comroster.services.version import Version

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


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


def test_head_corrompu_ne_leve_pas(tmp_path):
    """Octets non-UTF-8 dans `.git/HEAD` (carte SD corrompue par une coupure de courant) :
    `UnicodeDecodeError` hérite de `ValueError`, exactement le défaut corrigé pour
    `_charger()` au commit 9179703 mais jamais reporté sur `_premiere_ligne()`. Sans le
    correctif, `Version()` lève, donc `create_app()` lève, donc gunicorn ne démarre pas."""
    paquet = tmp_path / "comroster"
    paquet.mkdir()
    (paquet / "VERSION").write_text("v1.4.0 9f3c1a2 2026-07-29\n", encoding="utf-8")
    git = tmp_path / ".git"
    git.mkdir()
    (git / "HEAD").write_bytes(b"\xff")
    v = Version(str(paquet), repo_dir=str(tmp_path))
    assert v.stale is False


def test_packed_refs_corrompu_ne_leve_pas(tmp_path):
    """Même défaut, sur le second lecteur : `.git/packed-refs` corrompu ne doit pas
    davantage faire lever `Version()`."""
    paquet = tmp_path / "comroster"
    paquet.mkdir()
    (paquet / "VERSION").write_text("v1.4.0 9f3c1a2 2026-07-29\n", encoding="utf-8")
    git = tmp_path / ".git"
    git.mkdir()
    (git / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (git / "packed-refs").write_bytes(b"\xff")
    v = Version(str(paquet), repo_dir=str(tmp_path))
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


# ---------- Câblage de l'application ----------

def test_healthz_porte_la_version(client):
    """C'est le point qu'on interroge à distance, sans ouvrir de session : « quel code
    tourne sur cette machine ? » doit avoir une réponse en un curl."""
    corps = client.get("/healthz").get_json()
    assert corps["status"] == "ok"
    assert "version" in corps          # None hors déploiement : la clé, elle, est due


def test_la_sante_expose_la_version(app):
    from comroster.services import health
    snap = health.snapshot(app)
    assert "version" in snap
    assert set(snap["version"]) == {"known", "label", "commit", "date", "public", "stale"}


def test_la_version_est_injectee_dans_les_gabarits(app):
    """Le pied de /display la lit sous le nom `appversion`. « version » tout court est
    déjà pris par le numéro de révision d'une publication (services/model.py)."""
    from flask import render_template_string
    with app.test_request_context("/"):
        rendu = render_template_string("{{ appversion.known }}|{{ appversion.public }}")
    assert rendu.startswith(("True|", "False|"))


# ---------- Gravure au déploiement ----------

def _setup_pi():
    with open(os.path.join(RACINE, "deploy", "setup-pi.sh"), encoding="utf-8") as fichier:
        return fichier.read()


def test_le_deploiement_grave_la_version():
    """Sans cette écriture, tout le reste de la chaîne affiche « inconnue » : c'est le
    seul endroit où le numéro est produit."""
    source = _setup_pi()
    assert "comroster/VERSION" in source
    assert "describe --tags --always" in source


def test_le_deploiement_n_utilise_pas_dirty():
    """La garantie visée est étroite : aucune COMMANDE `git describe` ne doit porter
    `--dirty` (l'option rafraîchit l'index, qu'une racine montée en lecture seule
    refuse). Sa mention dans un commentaire expliquant pourquoi elle est proscrite
    reste, elle, souhaitable — un `assert "--dirty" not in source` l'interdirait aussi
    et finirait contourné par une périphrase, laissant le prochain lecteur sans
    explication.

    `git\\w*` et non `git` seul : le script n'appelle jamais `git` nu, il passe par le
    wrapper `git_cible()` (`sudo -u "$TARGET_USER" git …`) — un motif ancré sur `git `
    strict ne verrait jamais `git_cible describe`, la commande réellement exécutée, et
    la garde serait un théâtre qui ne mord rien."""
    assert not re.search(r'git\w*\s+describe[^\n]*--dirty', _setup_pi())


def test_le_deploiement_interroge_git_sous_l_utilisateur_cible():
    """Le script tourne en root, le dépôt appartient à l'utilisateur : sans `sudo -u`,
    git refuse le dépôt (« dubious ownership ») et la version resterait inconnue sur
    tous les boîtiers, en silence."""
    assert re.search(r'sudo -u "\$TARGET_USER" git', _setup_pi())


@pytest.mark.skipif(not os.path.isdir(os.path.join(RACINE, ".git")), reason="hors dépôt git")
def test_le_fichier_de_version_est_ignore_par_git():
    """C'est un artefact GÉNÉRÉ. Committé, il se figerait à la valeur du poste qui l'a
    produit et mentirait sur tous les autres.

    `skipif` et non un `return` muet : c'est la convention de tests/test_gitignore.py, et
    un test qui se termine sans assertion se compte comme réussi — il mentirait sur sa
    propre couverture."""
    code = subprocess.run(["git", "check-ignore", "-q", "comroster/VERSION"],
                          cwd=RACINE, check=False).returncode
    assert code == 0, "comroster/VERSION n'est pas couvert par .gitignore"


# ---------- Pied de l'écran de régie ----------

def test_le_pied_du_display_porte_la_version_publique(app, monkeypatch):
    monkeypatch.setattr(app.extensions["version"], "public", "v1.4")
    html = app.test_client().get("/display").get_data(as_text=True)
    assert "v1.4" in html
    assert "9f3c1a2" not in html         # jamais de commit devant un client


def test_sans_version_publique_le_pied_est_inchange(app, monkeypatch):
    """Aucun tag posé : le pied doit retrouver mot pour mot ce qu'il était avant ce lot.
    Un séparateur orphelin (« Nathan Hurstel · ») trahirait une valeur manquante."""
    monkeypatch.setattr(app.extensions["version"], "public", "")
    html = app.test_client().get("/display").get_data(as_text=True)
    assert "COMROSTER par Nathan Hurstel" in html
    assert "Nathan Hurstel ·" not in html


# Le pied a DEUX branches (marque cliente active ou non), chacune avec son propre
# `{% if appversion.public %}` : ce sont donc quatre combinaisons, pas deux. Les tests
# ci-dessus ne couvrent que `brand.active = False` ; ceux-ci couvrent l'autre moitié —
# c'est le seul endroit où le client final voit la marque ComRoster, sur un écran de
# régie de deux mètres où une espace en trop ou un point médian incongru se verrait.
from test_branding import _client_avec_pack  # noqa: E402


def _pied(html):
    """Isole le contenu du <span class="created-by"> : chercher le texte dans la page
    ENTIÈRE ne prouverait rien, d'autres éléments du gabarit contiennent déjà « ComRoster »."""
    return html.split('class="created-by">', 1)[1].split("</span>", 1)[0]


def test_le_pied_avec_marque_active_porte_la_version_publique(tmp_path, monkeypatch):
    """Marque cliente active : le crédit ComRoster cède la place d'honneur mais reste le
    seul endroit qualifiant la version — séparateur en simple espace (le numéro qualifie
    le produit « ComRoster », pas un nom d'auteur distinct comme dans l'autre branche)."""
    client = _client_avec_pack(tmp_path)
    monkeypatch.setattr(client.application.extensions["version"], "public", "v1.4")
    html = client.get("/display").get_data(as_text=True)
    assert _pied(html) == "Propulsé par ComRoster v1.4"


def test_le_pied_avec_marque_active_et_sans_version_est_inchange(tmp_path, monkeypatch):
    """Même garde que sans marque cliente : aucune version connue ne doit laisser une
    espace orpheline derrière « ComRoster »."""
    client = _client_avec_pack(tmp_path)
    monkeypatch.setattr(client.application.extensions["version"], "public", "")
    html = client.get("/display").get_data(as_text=True)
    assert _pied(html) == "Propulsé par ComRoster"


# ---------- Écran de démarrage ----------

def _fichier_deploy(nom):
    with open(os.path.join(RACINE, "deploy", nom), encoding="utf-8") as fichier:
        return fichier.read()


def test_le_kiosk_transmet_la_version_au_splash():
    """Le splash s'ouvre en file:// AVANT que le serveur réponde : il ne peut rien
    demander à personne. La version doit lui arriver par l'URL, comme `next` et
    `health`."""
    source = _fichier_deploy("kiosk-run.sh")
    assert "comroster/VERSION" in source
    assert "&v=$" in source


def test_le_kiosk_encode_le_plus_dans_l_url():
    """Dans une chaîne de requête, « + » se décode en ESPACE : sans encodage,
    « v1.4.0+7 » s'afficherait « v1.4.0 7 » à l'écran de démarrage."""
    assert "%2B" in _fichier_deploy("kiosk-run.sh")


def test_le_splash_affiche_la_version_sans_injection():
    """Le paramètre d'URL est une entrée non fiable : textContent, jamais innerHTML."""
    source = _fichier_deploy("boot-splash.html")
    assert 'params.get("v")' in source
    assert 'getElementById("version").textContent' in source


# ---------- Journal ----------

def test_le_demarrage_est_journalise_avec_la_version(app):
    """Le journal devient l'historique des mises à jour du boîtier : « depuis quand
    tourne-t-il sur cette version ? » n'a aucune autre source."""
    evenements = app.extensions["journal"].entries()
    demarrages = [e for e in evenements if e["event"] == "startup"]
    assert len(demarrages) == 1
    assert demarrages[0]["detail"]          # jamais vide : « version inconnue » à défaut


def test_le_libelle_du_demarrage_existe_cote_navigateur():
    """Sans entrée dans EVENT_LABELS, la page Journal afficherait la clé technique
    « startup » à l'utilisateur."""
    with open(os.path.join(RACINE, "static", "js", "journal.js"), encoding="utf-8") as f:
        assert "startup:" in f.read()


# ---------- Onglet Santé ----------

def test_la_sante_rend_la_carte_d_identite():
    """`health.js` est une IIFE non exportable : on le lit comme du texte, à la manière
    de tests/test_js_constants.py. C'est peu, mais ça attrape la clé mal orthographiée
    qui produirait un « undefined » à l'écran."""
    with open(os.path.join(RACINE, "static", "js", "health.js"), encoding="utf-8") as f:
        source = f.read()
    assert "d.version" in source
    assert "version du logiciel" in source
    assert "ver.stale" in source
