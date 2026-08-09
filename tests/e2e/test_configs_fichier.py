"""Bout-en-bout du dialogue « Configurations » élargi aux fichiers.

Importer et Exporter ont quitté la barre latérale pour ce dialogue : ils manipulent le
même objet que les configurations enregistrées — l'état du plateau — seule la
destination change (le boîtier ou un fichier `.rost`).

Trois propriétés qui ne se voient QUE dans un vrai navigateur :
  - annuler la confirmation d'import laisse le plateau strictement intact — une
    confirmation qu'on peut annuler sans effet est la seule qui protège de quelque chose ;
  - exporter une configuration enregistrée sort l'état SUR LE DISQUE, pas celui à
    l'écran, et sans rien détruire au passage ;
  - le pied « Fichier », lui, sort bien ce qui est à l'écran.
"""
import json

import pytest

# `helpers` s'importe en ABSOLU : tests/e2e n'est pas un package (aucun __init__.py),
# pytest insère donc ce dossier dans sys.path et un import relatif échouerait.
from helpers import wait_saved

pytestmark = pytest.mark.e2e


def _enter_admin(page, base):
    page.goto(base + "/admin/setup")
    page.fill("input[name=password]", "motdepasse8")
    page.click("button[type=submit]")
    page.click("a.auth-go")
    page.wait_for_selector("#add-block-btn")


def _ajouter_beltpack(page, numero, role):
    """Le vrai geste (réserve + formulaire), comme dans test_e2e.py."""
    page.click("#add-beltpack-pool")
    # Le dialogue doit être OUVERT avant qu'on écrive dedans : remplir un champ
    # non encore affiché part en silence et soumet un formulaire incomplet.
    page.wait_for_selector("#person-dialog[open]")
    page.fill("#person-beltpack", numero)
    page.fill("#person-role", role)
    page.click("#person-form button[type=submit]")
    page.wait_for_selector(f".person .bp:has-text('{numero}')")
    # Et son RÔLE : c'est lui qui manquait en CI (« assert 'Régie' in [''] »). Attendre le
    # seul numéro laissait passer une carte dont le champ rôle n'était pas encore rendu.
    page.wait_for_selector(f".person .role:has-text('{role}')")
    # Le DOM est en avance sur le disque : enregistrer une configuration fait relire le
    # brouillon PAR LE SERVEUR, qui figerait sinon l'état d'avant cet ajout.
    wait_saved(page)


def _ouvrir_configs(page):
    page.click("#configs-btn")
    page.wait_for_selector("#configs-dialog[open]")


def _roles_a_l_ecran(page):
    return [t.lower() for t in page.locator(".person .role").all_inner_texts()]


def test_annuler_l_import_laisse_le_plateau_intact(page, live_server):
    """La garde qui compte : sans elle, la confirmation serait décorative."""
    _enter_admin(page, live_server)
    _ajouter_beltpack(page, "5", "Régie")
    avant = page.evaluate("async () => await (await fetch('/api/state')).json()")

    intrus = dict(avant)
    intrus["people"] = [{"id": "x1", "beltpack": "42", "role": "Intrus", "group_id": None}]

    _ouvrir_configs(page)
    page.set_input_files("#import-input", files=[{
        "name": "autre.rost", "mimeType": "application/json",
        "buffer": json.dumps(intrus).encode()}])
    page.wait_for_selector("#confirm-dialog[open]")
    # Le nom du fichier est rappelé : on confirme un fichier PRÉCIS, pas « un import ».
    assert "autre.rost" in page.inner_text("#confirm-text")

    page.click("#confirm-dialog button[value=cancel]")
    page.wait_for_selector("#confirm-dialog:not([open])", state="attached")

    # Le CSS met les rôles en capitales : comparer en minuscules (leçon 2026-07-30).
    roles = _roles_a_l_ecran(page)
    assert any("régie" in r for r in roles)
    assert not any("intrus" in r for r in roles)
    apres = page.evaluate("async () => await (await fetch('/api/state')).json()")
    assert apres["people"] == avant["people"]


def test_exporter_une_configuration_sort_l_etat_enregistre(page, live_server):
    """Le fichier vient du DISQUE, pas de l'écran — et rien n'est détruit au passage.

    On enregistre une configuration, on modifie le plateau APRÈS, puis on exporte. Si le
    bouton lisait `state.data` (le plateau à l'écran) au lieu de l'API, le fichier
    contiendrait la modification. Et s'il avait été câblé sur `/load`, faute d'une route
    de lecture pure, le plateau à l'écran aurait été écrasé par l'export lui-même.
    """
    _enter_admin(page, live_server)
    _ajouter_beltpack(page, "5", "Régie")

    _ouvrir_configs(page)
    page.fill("#config-name", "Jour 2")
    page.click("#config-save-btn")
    page.wait_for_selector("#configs-list [data-export='Jour 2']")
    page.click("#configs-dialog button[data-close='configs-dialog']")
    page.wait_for_selector("#configs-dialog:not([open])", state="attached")

    _ajouter_beltpack(page, "7", "Après coup")

    _ouvrir_configs(page)
    with page.expect_download() as telechargement:
        page.click("#configs-list [data-export='Jour 2']")
    fichier = telechargement.value
    # Le nom porte celui de la configuration : trois exports côte à côte restent lisibles.
    assert fichier.suggested_filename == "comroster-jour-2.rost"

    with open(fichier.path(), encoding="utf-8") as fh:
        contenu = json.load(fh)
    roles = [p["role"] for p in contenu["people"]]
    assert "Régie" in roles
    assert "Après coup" not in roles          # l'écran a changé, le fichier non

    # Exporter ne touche à rien : le dialogue reste ouvert, le plateau garde son ajout.
    assert page.is_visible("#configs-dialog")
    etat = page.evaluate("async () => await (await fetch('/api/state')).json()")
    assert "Après coup" in [p["role"] for p in etat["people"]]


def test_exporter_le_plateau_courant_depuis_le_pied(page, live_server):
    """Le pied « Fichier » exporte ce qui est À L'ÉCRAN."""
    _enter_admin(page, live_server)
    _ajouter_beltpack(page, "5", "Régie")

    _ouvrir_configs(page)
    with page.expect_download() as telechargement:
        page.click("#export-btn")
    fichier = telechargement.value
    assert fichier.suggested_filename.startswith("comroster-")
    assert fichier.suggested_filename.endswith(".rost")

    with open(fichier.path(), encoding="utf-8") as fh:
        contenu = json.load(fh)
    assert "Régie" in [p["role"] for p in contenu["people"]]
