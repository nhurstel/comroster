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
from helpers import enter_admin, open_screen_tab, open_systeme, ouvrir_ajout_beltpack

pytestmark = pytest.mark.e2e


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


# ---------- A. L'admin ne se compte pas comme écran connecté ----------

def test_l_admin_seul_n_annonce_aucun_ecran_connecte(page, live_server):
    erreurs, _ = _collect_console(page)
    enter_admin(page, live_server)
    # La barre d'état lit /api/status. Sans le correctif, l'admin comptait son propre
    # flux SSE et affichait « 1 écran connecté » sans le moindre écran branché.
    page.wait_for_function(
        "() => document.getElementById('status-sse-text')?.textContent.trim() === 'aucun écran connecté'",
        timeout=10000)
    assert erreurs == []


def test_un_vrai_ecran_est_bien_compte(page, live_server):
    """Assertion miroir : sans elle, le test précédent passerait même si le compteur
    était bloqué à zéro."""
    enter_admin(page, live_server)
    ecran = page.context.new_page()
    ecran.goto(live_server + "/display")
    ecran.wait_for_selector("#display-grid", state="attached")
    page.wait_for_function(
        "() => /1 écran connecté/.test(document.getElementById('status-sse-text')?.textContent || '')",
        timeout=15000)
    ecran.close()


# ---------- B. L'import ne perd plus de champs ----------

def test_l_import_conserve_le_nom_de_production_et_la_taille_du_texte(page, live_server):
    enter_admin(page, live_server)
    open_screen_tab(page)
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
    enter_admin(page, live_server)
    open_systeme(page, "password")
    page.fill("#pw-current", "motdepasse8")
    page.fill("#pw-new", "nouveau-mdp")
    page.fill("#pw-confirm", "pas-pareil")
    page.click("#password-form button[type=submit]")
    page.wait_for_selector("#pw-error:not([hidden])")     # la confirmation ne suit pas

    page.fill("#pw-confirm", "nouveau-mdp")
    page.click("#password-form button[type=submit]")
    # Attendre le TOAST, seul signal prouvant que le serveur a répondu. La ligne
    # précédente attendait `#pw-current` visible — un champ qui l'est en permanence, donc
    # une attente qui rendait la main aussitôt : on se déconnectait AVANT que le POST
    # /admin/password ne parte (tracé le 2026-08-20 : il arrivait 1,5 s plus tard). Le
    # mot de passe n'était pas changé, la reconnexion échouait, et le test ne tenait que
    # par la chance du calendrier — la moindre variation de rendu le faisait tomber.
    page.wait_for_selector(".cr-toast:has-text('Mot de passe changé')")

    page.click("#logout-link")
    page.wait_for_selector("input[name=password]")
    page.fill("input[name=password]", "nouveau-mdp")
    page.click("button[type=submit]")
    page.wait_for_selector("#add-block-btn")
    assert erreurs == []


# ---------- C1. Sauvegarde complète ----------

def test_sauvegarder_puis_restaurer_le_boitier(page, live_server):
    erreurs, vus = _collect_console(page)
    enter_admin(page, live_server)
    page.click("#add-block-btn")
    page.fill("#block-name", "Lumière")
    page.click("#block-form button[type=submit]")
    page.wait_for_selector("#blocks-container >> text=Lumière")

    open_systeme(page, "backup")
    page.fill("#bk-pass", "phrase-de-passe")
    with page.expect_download() as dl:
        page.click("#bk-create")
    fichier = dl.value
    chemin = fichier.path()
    assert fichier.suggested_filename.endswith(".rostbak")

    # On efface le groupe, puis on restaure l'archive téléchargée.
    page.click('.admin-tabs .tab[data-tab="board"]')
    # Le survol est le GESTE RÉEL : les actions d'un bloc sont repliées (largeur nulle)
    # tant qu'on ne le survole pas, pour ne pas manger le nom du groupe. Sans ce hover,
    # le clic viserait le centre d'une boîte de 0 px et l'en-tête l'intercepterait — le
    # test s'appuyait jusqu'ici sur la place que ces boutons occupaient en étant invisibles.
    page.hover(".admin-block .block-header")
    page.click(".admin-block .block-actions button:has-text('Supprimer')")
    page.click("#confirm-ok")
    page.wait_for_selector(".admin-block", state="detached")

    open_systeme(page, "backup")
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
    enter_admin(page, live_server)
    open_systeme(page, "backup")
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
    enter_admin(page, live_server)
    ouvrir_ajout_beltpack(page)
    # Le dialogue doit être OUVERT avant qu'on écrive dedans : remplir un champ
    # non encore affiché part en silence et soumet un formulaire incomplet.
    page.wait_for_selector("#person-dialog[open]")
    page.fill("#person-beltpack", "7")
    page.click("#person-form button[type=submit]")
    page.click("#publish-btn")
    page.keyboard.press("Control+Enter")
    page.wait_for_selector("#sync-label:has-text('À jour')")

    page.click("#versions-btn")
    page.wait_for_selector("#versions-dialog[open] .hi-row")
    page.click(".hi-row .hi-label")
    page.fill(".hi-row .hi-label input", "Générale")
    page.keyboard.press("Enter")
    page.wait_for_selector(".hi-row .hi-label:has-text('Générale')")

    page.click(".hi-row .hi-pin")
    page.wait_for_selector(".hi-row.pinned")
    page.reload()
    page.wait_for_selector("#add-block-btn")
    page.click("#versions-btn")
    page.wait_for_selector(".hi-row.pinned .hi-label:has-text('Générale')")


# ---------- C4. Impression ----------

def test_la_feuille_imprimable_s_ouvre_et_liste_les_affectations(page, live_server):
    enter_admin(page, live_server)
    page.click("#add-block-btn")
    page.fill("#block-name", "Son")
    page.click("#block-form button[type=submit]")
    ouvrir_ajout_beltpack(page)
    # Le dialogue doit être OUVERT avant qu'on écrive dedans : remplir un champ
    # non encore affiché part en silence et soumet un formulaire incomplet.
    page.wait_for_selector("#person-dialog[open]")
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
    # casefold : les noms de groupe sont rendus en capitales par le CSS (leçon n°73).
    texte = texte.casefold()
    assert "son" in texte and "12" in texte and "hf" in texte
    # Le filet de couleur est posé en CSSOM (la CSP interdit l'attribut style).
    couleur = feuille.evaluate(
        "() => getComputedStyle(document.querySelector('.sheet-rule')).backgroundColor")
    assert couleur and couleur != "rgba(0, 0, 0, 0)"
    assert erreurs == []
    feuille.close()


# ---------- C5. Découverte d'antenne ----------

def test_la_decouverte_propose_sans_remplacer_la_saisie_manuelle(page, live_server):
    erreurs, _ = _collect_console(page)
    enter_admin(page, live_server)
    page.click("#antenna-btn")
    page.wait_for_selector('.tab-panel[data-panel="intercom"]:not([hidden])')
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


def test_le_dialogue_ne_vole_pas_le_focus_a_qui_saisit_deja(page, live_server):
    """`openPersonDialog` posait le focus sur le champ numéro à la frame SUIVANTE.

    Entre l'ouverture et cet instant, l'utilisateur a le temps de viser le champ rôle :
    le focus différé le lui reprenait, et sa frappe partait dans le champ numéro. À
    l'écran de régie, cela donnait un beltpack publié sans rôle (« BP 42 — »).

    La course est RETENUE plutôt que courue : `requestAnimationFrame` est mis en file
    d'attente, on saisit, puis on la libère. Une première version de ce test se
    contentait de viser vite le champ rôle — elle passait AUSSI avec le défaut réintroduit
    (`wait_for_selector` dure bien plus qu'une frame, la frame était donc déjà écoulée),
    donc elle ne prouvait rien.
    """
    page.add_init_script("""
        window.__rafs = [];
        window.requestAnimationFrame = (cb) => { window.__rafs.push(cb); return 0; };
    """)
    enter_admin(page, live_server)
    ouvrir_ajout_beltpack(page)
    page.wait_for_selector("#person-dialog[open]")

    # L'utilisateur vise le rôle et tape, AVANT que la frame différée ne s'exécute.
    page.focus("#person-role")
    page.keyboard.type("Régie plateau")

    # Témoin positif : sans lui, un rAF jamais mis en file rendrait le test creux.
    assert page.evaluate("window.__rafs.length") > 0, (
        "aucune frame différée en attente : la course n'est pas reproduite"
    )
    page.evaluate("window.__rafs.splice(0).forEach((cb) => cb())")

    assert page.evaluate("document.activeElement.id") == "person-role", (
        "le focus différé a repris la main sur une saisie déjà commencée"
    )
    assert page.input_value("#person-role") == "Régie plateau"
