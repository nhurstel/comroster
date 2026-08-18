"""Ce que voit un régisseur qui revient devant un onglet dont la session est morte.

Le défaut corrigé, reproduit au banc le 2026-08-11 : l'onglet d'admin restait ouvert,
la session expirait (12 h, ou un boîtier redémarré), et l'interface CONTINUAIT de se
comporter comme si de rien n'était. Les groupes créés après coup s'affichaient, le
bouton Publier restait cliquable, et le seul signe était un libellé de 11 px dans la
barre du bas — « Échec de l'enregistrement », le même que pour une coupure réseau
passagère. Au rafraîchissement suivant : page de connexion, tout le travail perdu.

Deux causes, deux gardes ici. Côté serveur, Flask-WTF rejetait le jeton CSRF AVANT
`login_required`, si bien qu'un 400 générique partait à la place du 401 : le client ne
POUVAIT pas distinguer « reconnecte-toi » de « réessaie ». Côté client, aucun appelant
ne traitait le 401.

Exclus par défaut (marqueur `e2e`). Lancer :
    .venv/bin/pytest tests/e2e -m e2e
"""
import pytest

# `helpers` s'importe en ABSOLU : tests/e2e n'est pas un package (aucun __init__.py),
# pytest insère donc ce dossier dans sys.path et un import relatif échouerait.
from helpers import enter_admin, se_reconnecter

pytestmark = pytest.mark.e2e


def _creer_groupe(page, nom):
    page.click("#add-block-btn")
    page.fill("#block-name", nom)
    page.press("#block-name", "Enter")


def test_une_session_morte_avertit_gele_et_ne_perd_rien(page, live_server):
    """Les trois gestes attendus, dans l'ordre : avertir, geler, mettre à l'abri.

    On tue la session en vidant les cookies — c'est exactement ce que produit un
    portable refermé au-delà des 12 h, ou un redémarrage du boîtier.
    """
    enter_admin(page, live_server)
    _creer_groupe(page, "Régie")
    page.wait_for_timeout(1600)          # au-delà du debounce d'enregistrement

    page.context.clear_cookies()
    _creer_groupe(page, "Plateau")
    # 15 s comme le reste de la suite, et non 5 comme à l'écriture de ce fichier : ce qu'on
    # affirme, c'est que le bandeau APPARAÎT, pas qu'il apparaît en moins de cinq secondes.
    # La chaîne compte un anti-rebond de 900 ms (SAVE_DEBOUNCE_MS) plus un aller-retour
    # HTTP ; sur un runner partagé, ce budget a fini par manquer et a fait rougir la CI le
    # 2026-08-18 sans qu'aucun code n'ait bougé. Un test qui échoue au hasard coûte plus
    # cher que le défaut qu'il surveille : on cesse de le croire.
    page.wait_for_selector(".session-lost", timeout=15000)

    # AVERTIR — un bandeau, pas un libellé de 11 px.
    bandeau = page.locator(".session-lost")
    assert bandeau.is_visible()
    assert "Session expirée" in bandeau.inner_text()
    assert page.locator(".session-lost-go").is_visible(), "aucun chemin de retour proposé"

    # GELER — continuer à éditer ne produirait plus que du travail perdu.
    assert page.evaluate("document.body.dataset.session") == "lost"
    assert page.locator("#publish-btn").is_disabled(), "Publier reste cliquable dans le vide"

    # METTRE À L'ABRI — le brouillon en mémoire a été recopié AVANT tout le reste.
    sauve = page.evaluate("JSON.parse(localStorage.getItem('comroster.brouillon-rescape'))")
    assert sauve, "le travail non enregistré n'a pas été mis de côté"
    noms = [g["name"] for g in sauve["data"]["groups"]]
    assert "Plateau" in noms, f"le groupe créé après l'expiration est perdu : {noms}"


def test_le_travail_rescape_est_propose_puis_enregistre(page, live_server):
    """Après reconnexion, la reprise est PROPOSÉE — jamais imposée.

    Restaurer d'office écraserait un brouillon serveur qui a pu changer entre-temps :
    ce serait le défaut qu'on vient de corriger, retourné.
    """
    # Un groupe enregistré POUR DE BON : c'est ce que le serveur connaîtra.
    enter_admin(page, live_server)
    _creer_groupe(page, "Régie")
    page.wait_for_timeout(1600)

    # Puis la session meurt, et un second groupe part dans le vide.
    page.context.clear_cookies()
    _creer_groupe(page, "Lumière")
    page.wait_for_selector(".session-lost", timeout=15000)

    # On se reconnecte, comme le ferait l'utilisateur depuis le bandeau.
    se_reconnecter(page, live_server)

    page.wait_for_selector(".session-rescue", timeout=15000)
    assert "Travail non enregistré retrouvé" in page.locator(".session-rescue").inner_text()
    assert page.locator("#blocks-container .admin-block").count() == 1, \
        "tant que l'utilisateur n'a pas choisi, on montre le brouillon SERVEUR, pas le rescapé"

    page.click(".session-rescue-yes")
    page.wait_for_function(
        "() => document.querySelectorAll('#blocks-container .admin-block').length === 2",
        timeout=15000)
    page.wait_for_timeout(1600)          # laisse l'enregistrement partir

    # La reprise est allée jusqu'au SERVEUR, pas seulement à l'écran.
    page.reload()
    page.wait_for_selector("#blocks-container .admin-block", timeout=15000)
    assert page.locator("#blocks-container .admin-block").count() == 2, \
        "le travail restauré n'a pas été réenregistré côté serveur"
    assert page.locator(".session-rescue").count() == 0, \
        "la proposition de reprise doit disparaître une fois consommée"
