"""Gestes d'interface partagés par les e2e.

Une seule définition : les fonctions du boîtier vivent désormais dans un menu, et
sept tests existants cliquaient leurs boutons en direct. Recopier l'ouverture dans
chaque fichier reviendrait à entretenir deux versions du même geste.
"""


def open_reglages(page):
    """Ouvre le menu « Réglages » et attend que son panneau soit réellement visible.

    L'attente est explicite : le panneau est piloté par `hidden`, et un `wait_for_selector`
    sans état attend `visible` par défaut — c'est ce qui a fait expirer deux attentes dans
    ce dépôt (leçons 2026-07-23 et 2026-07-27).
    """
    page.click("#settings-btn")
    page.wait_for_selector("#settings-menu:not([hidden])", state="visible")


def wait_saved(page):
    """Attend la FIN du cycle d'enregistrement du brouillon.

    La chip d'état n'affiche pas un libellé figé « Brouillon enregistré » : sitôt la
    sauvegarde finie elle retourne à sa vérité (« N en attente » / « À jour »), qui dépend
    de l'écart publié. Le signal fiable est donc le CYCLE : « Enregistrement… »
    (data-state=syncing, tenu ≥ 500 ms par le debounce — immanquable si on appelle ce
    helper juste après l'édition) puis sa sortie.

    Promue ici depuis test_e2e.py (où elle s'appelait `_wait_saved`) : tout test qui
    demande au SERVEUR de relire le brouillon — enregistrer une configuration, publier —
    doit l'attendre, sinon il fige l'état d'AVANT son édition sans qu'aucune assertion
    ne le signale.
    """
    page.wait_for_selector("#sync-status[data-state='syncing']")
    page.wait_for_selector("#sync-status:not([data-state='syncing'])")
