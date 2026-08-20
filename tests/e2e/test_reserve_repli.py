"""Replier la réserve est un GESTE, pas un calcul.

Signalé par Nathan le 2026-08-20 : « la liste des beltpacks dispo peut se déplier mais je
ne peux pas la replier ». Le relevé a donné raison au symptôme, et montré autre chose que
ce que le mot « bug » laissait attendre — il n'y avait aucun contrôle de repli.

La refonte du 2026-08-14 traitait le pli comme un ÉTAT CALCULÉ : replié si et seulement si
zéro beltpack disponible. Deux conséquences, aucune voulue :
  1. une réserve non vide ne pouvait pas être repliée, quoi qu'on fasse ;
  2. `state.poolOuvert` passait à `true` au dépliage et rien ne le remettait à `false` :
     déplier était donc IRRÉVERSIBLE pour la session.

D'où trois états au lieu de deux — `null` calcule, `true`/`false` commandent — et ces
tests, qui portent sur les deux sens du geste plutôt que sur la présence du bouton.
"""
import pytest
from helpers import ajouter_beltpack, enter_admin

pytestmark = pytest.mark.e2e


def test_replier_une_reserve_non_vide(page, live_server):
    """Le cas que Nathan ne pouvait PAS faire : des beltpacks en réserve, et replier."""
    enter_admin(page, live_server)
    ajouter_beltpack(page, "11", "Regie")
    # Le beltpack reste en réserve : le panneau est donc déplié, et le rail masqué.
    page.wait_for_selector("#panel-pool:not([hidden])")
    assert page.is_hidden("#pool-rail")

    page.click("#pool-fold")

    page.wait_for_selector("#pool-rail:not([hidden])")
    assert page.is_hidden("#panel-pool"), (
        "la réserve est restée dépliée alors que le repli a été commandé"
    )
    # Le compte survit au repli : c'est la fonction que le rail doit garder.
    assert page.inner_text("#pool-rail-count") == "1"


def test_le_repli_est_reversible_dans_les_deux_sens(page, live_server):
    """Déplier après avoir replié, et REPLIER À NOUVEAU.

    C'est la seconde moitié du défaut : `poolOuvert` ne repassait jamais à faux, donc le
    deuxième repli était impossible même une fois le premier obtenu. Un test qui
    s'arrêterait au premier aller-retour ne verrait rien.
    """
    enter_admin(page, live_server)
    ajouter_beltpack(page, "11", "Regie")

    page.click("#pool-fold")
    page.wait_for_selector("#pool-rail:not([hidden])")
    page.click("#pool-rail-open")
    page.wait_for_selector("#panel-pool:not([hidden])")
    page.click("#pool-fold")
    page.wait_for_selector("#pool-rail:not([hidden])")

    assert page.is_hidden("#panel-pool"), (
        "le second repli n'a pas eu lieu : l'état de pli n'est pas retombé"
    )


def test_le_choix_de_l_operateur_survit_au_rendu_suivant(page, live_server):
    """Replié à la demande, la réserve doit le RESTER quand la liste se redessine.

    C'est le cœur de la correction : `renderAvailable` recalcule le pli à chaque
    changement de la réserve. Tant que le calcul avait le dernier mot, un repli commandé
    aurait été défait par l'action suivante — donc inutilisable en pratique. Ajouter un
    beltpack depuis le rail redessine la liste : c'est le rendu qui doit respecter le choix.
    """
    enter_admin(page, live_server)
    ajouter_beltpack(page, "11", "Regie")
    page.click("#pool-fold")
    page.wait_for_selector("#pool-rail:not([hidden])")

    # Ajout écrit à la main, et non via `ajouter_beltpack` : le helper attend la carte
    # VISIBLE dans la réserve, ce qu'une réserve repliée ne peut par construction pas
    # offrir. L'utiliser ici ferait échouer le test sur son propre décor.
    page.click("#pool-rail-add")
    page.wait_for_selector("#person-dialog[open]")
    page.fill("#person-beltpack", "22")
    page.fill("#person-role", "Lumiere")
    page.click("#person-form button[type=submit]")
    page.wait_for_selector("#person-dialog:not([open])", state="attached")

    assert page.inner_text("#pool-rail-count") == "2", "le rail n'a pas vu le nouvel ajout"
    assert page.is_hidden("#panel-pool"), (
        "le rendu a rouvert une réserve que l'opérateur avait repliée"
    )


def test_pas_de_bouton_de_repli_sur_un_roster_vide(page, live_server):
    """Replier au premier démarrage cacherait le produit à qui le découvre.

    Le bouton DISPARAÎT plutôt que de rester présent sans effet : un contrôle qui ne fait
    rien quand on l'actionne est pire que son absence.
    """
    enter_admin(page, live_server)
    page.wait_for_selector("#panel-pool:not([hidden])")
    assert page.is_hidden("#pool-fold"), (
        "le bouton de repli est offert alors qu'aucun beltpack n'existe encore"
    )
