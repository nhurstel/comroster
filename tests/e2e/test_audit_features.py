"""Bout-en-bout des correctifs et ajouts de l'audit 2026-07-28.

Ces fonctions vivent dans le navigateur : compteur d'afficheurs, dialogues de sauvegarde
et de mot de passe, repères d'historique, découverte d'antenne, impression. Les
valider en DOM seul ne prouverait rien (leçon 2026-07-07) — on passe donc par un vrai
navigateur, et on vérifie la console à chaque fois.
"""
import re

import pytest

# `helpers` s'importe en ABSOLU : tests/e2e n'est pas un package (aucun __init__.py),
# pytest insère donc ce dossier dans sys.path et un import relatif échouerait.
from helpers import open_reglages

pytestmark = pytest.mark.e2e


def _enter_admin(page, base):
    page.goto(base + "/admin/setup")
    page.fill("input[name=password]", "motdepasse8")
    page.click("button[type=submit]")
    page.click("a.auth-submit")
    page.wait_for_selector("#add-block-btn")


def _collect_console(page):
    """Collecteur d'erreurs, armé AVANT tout chargement.

    Une assertion « aucune erreur » est CREUSE si le collecteur ne s'arme jamais
    (leçon 2026-07-23) : on renvoie donc aussi le compteur de messages vus, pour
    pouvoir vérifier que le canal fonctionne.
    """
    erreurs, vus = [], []
    page.on("console", lambda m: (vus.append(m.type),
                                  erreurs.append(m.text) if m.type == "error" else None))
    page.on("pageerror", lambda e: erreurs.append(str(e)))
    return erreurs, vus


# ---------- A. L'admin ne se compte pas comme afficheur ----------

def test_l_admin_seul_n_annonce_aucun_afficheur(page, live_server):
    erreurs, _ = _collect_console(page)
    _enter_admin(page, live_server)
    # La barre d'état lit /api/status. Sans le correctif, l'admin comptait son propre
    # flux SSE et affichait « 1 afficheur » sans le moindre écran branché.
    page.wait_for_function(
        "() => document.getElementById('status-sse-text')?.textContent.trim() === 'aucun afficheur'",
        timeout=10000)
    assert erreurs == []


def test_un_vrai_ecran_est_bien_compte(page, live_server):
    """Assertion miroir : sans elle, le test précédent passerait même si le compteur
    était bloqué à zéro."""
    _enter_admin(page, live_server)
    ecran = page.context.new_page()
    ecran.goto(live_server + "/display")
    ecran.wait_for_selector("#display-grid", state="attached")
    page.wait_for_function(
        "() => /1 afficheur/.test(document.getElementById('status-sse-text')?.textContent || '')",
        timeout=15000)
    ecran.close()


# ---------- B. L'import ne perd plus de champs ----------

def test_l_import_conserve_le_nom_de_production_et_la_taille_du_texte(page, live_server):
    _enter_admin(page, live_server)
    page.click(".admin-tabs .tab[data-tab='screen']")
    page.fill("#meta-production", "Carmen")
    page.select_option("#meta-text-scale", "tres-grand")
    page.wait_for_selector("#sync-status[data-state='syncing']")
    page.wait_for_selector("#sync-status:not([data-state='syncing'])", state="attached")

    # On exporte via l'API, puis on réimporte le fichier tel quel.
    exporte = page.evaluate("async () => JSON.stringify(await (await fetch('/api/state')).json())")
    page.set_input_files("#import-input", files=[{
        "name": "essai.rost", "mimeType": "application/json", "buffer": exporte.encode()}])
    # L'import remplace TOUT le plateau : il demande maintenant confirmation.
    page.wait_for_selector("#confirm-dialog[open]")
    page.click("#confirm-ok")
    page.wait_for_selector("#sync-status:not([data-state='syncing'])", state="attached")
    page.reload()
    # L'onglet actif est PERSISTÉ : on revient sur « Écran », donc le bouton du panneau
    # « Affectations » est légitimement masqué — attendre sa visibilité expirerait.
    page.wait_for_selector(".tab-panel[data-panel='screen']:not([hidden])")
    assert page.input_value("#meta-production") == "Carmen"
    assert page.input_value("#meta-text-scale") == "tres-grand"


# ---------- G. Changement de mot de passe ----------

def test_changer_le_mot_de_passe_depuis_l_admin(page, live_server):
    erreurs, _ = _collect_console(page)
    _enter_admin(page, live_server)
    open_reglages(page)
    page.click("#password-btn")
    page.wait_for_selector("#password-dialog[open]")
    page.fill("#pw-current", "motdepasse8")
    page.fill("#pw-new", "nouveau-mdp")
    page.fill("#pw-confirm", "pas-pareil")
    page.click("#password-form button[type=submit]")
    page.wait_for_selector("#pw-error:not([hidden])")     # la confirmation ne suit pas

    page.fill("#pw-confirm", "nouveau-mdp")
    page.click("#password-form button[type=submit]")
    page.wait_for_selector("#password-dialog:not([open])", state="attached")

    page.click("#logout-link")
    page.wait_for_selector("input[name=password]")
    page.fill("input[name=password]", "nouveau-mdp")
    page.click("button[type=submit]")
    page.wait_for_selector("#add-block-btn")
    assert erreurs == []


# ---------- C1. Sauvegarde complète ----------

def test_sauvegarder_puis_restaurer_le_boitier(page, live_server):
    erreurs, vus = _collect_console(page)
    _enter_admin(page, live_server)
    page.click("#add-block-btn")
    page.fill("#block-name", "Lumière")
    page.click("#block-form button[type=submit]")
    page.wait_for_selector("#blocks-container >> text=Lumière")

    open_reglages(page)
    page.click("#backup-btn")
    page.wait_for_selector("#backup-dialog[open]")
    page.fill("#bk-pass", "phrase-de-passe")
    with page.expect_download() as dl:
        page.click("#bk-create")
    fichier = dl.value
    chemin = fichier.path()
    assert fichier.suggested_filename.endswith(".rostbak")

    # On efface le groupe, puis on restaure l'archive téléchargée.
    page.click("#backup-dialog [data-close='backup-dialog']")
    # Le survol est le GESTE RÉEL : les actions d'un bloc sont repliées (largeur nulle)
    # tant qu'on ne le survole pas, pour ne pas manger le nom du groupe. Sans ce hover,
    # le clic viserait le centre d'une boîte de 0 px et l'en-tête l'intercepterait — le
    # test s'appuyait jusqu'ici sur la place que ces boutons occupaient en étant invisibles.
    page.hover(".admin-block .block-header")
    page.click(".admin-block .block-actions button:has-text('Supprimer')")
    page.click("#confirm-ok")
    page.wait_for_selector(".admin-block", state="detached")

    open_reglages(page)
    page.click("#backup-btn")
    page.wait_for_selector("#backup-dialog[open]")
    page.set_input_files("#bk-file", chemin)
    page.fill("#bk-restore-pass", "phrase-de-passe")
    page.click("#bk-inspect")
    # L'examen ANNONCE le contenu avant d'écraser quoi que ce soit.
    page.wait_for_selector("#bk-summary:not([hidden])")
    assert "groupe" in page.inner_text("#bk-summary")
    page.click("#bk-restore")
    page.click("#confirm-ok")
    page.wait_for_selector("#blocks-container >> text=Lumière", timeout=15000)
    assert erreurs == [], erreurs

    # L'assertion ci-dessus ne vaut que si le collecteur est réellement branché : une page
    # qui ne journalise rien la rendrait vraie pour de mauvaises raisons (leçon 2026-07-23).
    # On provoque donc une erreur console et on vérifie qu'elle est bien vue.
    page.evaluate("() => console.error('sonde-collecteur')")
    page.wait_for_timeout(150)
    assert any("sonde-collecteur" in e for e in erreurs), (
        "le collecteur console ne capte rien — l'assertion « aucune erreur » serait creuse"
    )
    assert vus, "aucun message console vu, pas même la sonde"


def test_une_mauvaise_phrase_de_passe_le_dit_et_ne_restaure_rien(page, live_server):
    _enter_admin(page, live_server)
    open_reglages(page)
    page.click("#backup-btn")
    page.fill("#bk-pass", "phrase-de-passe")
    with page.expect_download() as dl:
        page.click("#bk-create")
    chemin = dl.value.path()

    page.set_input_files("#bk-file", chemin)
    page.fill("#bk-restore-pass", "pas-la-bonne")
    page.click("#bk-inspect")
    page.wait_for_selector("#bk-error:not([hidden])")
    assert "hrase de passe" in page.inner_text("#bk-error")
    # Le bouton de restauration ne doit pas être proposé sur un examen qui a échoué.
    assert page.is_hidden("#bk-restore")


# ---------- C3. Repères d'historique ----------

def test_nommer_et_epingler_une_publication(page, live_server):
    _enter_admin(page, live_server)
    page.click("#add-beltpack-pool")
    page.fill("#person-beltpack", "7")
    page.click("#person-form button[type=submit]")
    page.click("#publish-btn")
    page.keyboard.press("Control+Enter")
    page.wait_for_selector("#sync-label:has-text('À jour')")

    page.click("#history-btn")
    page.wait_for_selector("#history-dialog[open] .hi-row")
    page.click(".hi-row .hi-label")
    page.fill(".hi-row .hi-label input", "Générale")
    page.keyboard.press("Enter")
    page.wait_for_selector(".hi-row .hi-label:has-text('Générale')")

    page.click(".hi-row .hi-pin")
    page.wait_for_selector(".hi-row.pinned")
    page.reload()
    page.wait_for_selector("#add-block-btn")
    page.click("#history-btn")
    page.wait_for_selector(".hi-row.pinned .hi-label:has-text('Générale')")


# ---------- C4. Impression ----------

def test_la_feuille_imprimable_s_ouvre_et_liste_les_affectations(page, live_server):
    _enter_admin(page, live_server)
    page.click("#add-block-btn")
    page.fill("#block-name", "Son")
    page.click("#block-form button[type=submit]")
    page.click("#add-beltpack-pool")
    page.fill("#person-beltpack", "12")
    page.fill("#person-role", "HF")
    page.select_option("#person-assign", label="Son")
    page.click("#person-form button[type=submit]")
    page.click("#publish-btn")
    page.keyboard.press("Control+Enter")
    page.wait_for_selector("#sync-label:has-text('À jour')")

    feuille = page.context.new_page()
    erreurs, _ = _collect_console(feuille)
    feuille.goto(live_server + "/admin/print")
    feuille.wait_for_selector(".sheet-table")
    texte = feuille.inner_text("body")
    assert "Son" in texte and "12" in texte and "HF" in texte
    # Le filet de couleur est posé en CSSOM (la CSP interdit l'attribut style).
    couleur = feuille.evaluate(
        "() => getComputedStyle(document.querySelector('.sheet-rule')).backgroundColor")
    assert couleur and couleur != "rgba(0, 0, 0, 0)"
    assert erreurs == []
    feuille.close()


# ---------- C5. Découverte d'antenne ----------

def test_la_decouverte_propose_sans_remplacer_la_saisie_manuelle(page, live_server):
    erreurs, _ = _collect_console(page)
    _enter_admin(page, live_server)
    page.click("#antenna-btn")
    page.wait_for_selector("#antenna-dialog[open]")
    # En mode dev le serveur rend un jeu fictif : la liste doit se remplir seule.
    page.wait_for_selector(".ant-row", timeout=10000)

    # Le champ d'adresse reste là, et il est LIBREMENT saisissable.
    page.fill("#wiz-ip", "10.0.0.9")
    assert page.input_value("#wiz-ip") == "10.0.0.9"

    # Cliquer une antenne REMPLIT le champ — et ne connecte rien.
    page.click(".ant-row")
    assert re.match(r"^\d+\.\d+\.\d+\.\d+$", page.input_value("#wiz-ip"))
    assert page.is_visible("#wiz-connect-btn"), "la connexion reste une action explicite"
    assert erreurs == []
