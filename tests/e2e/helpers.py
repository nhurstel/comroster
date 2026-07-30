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
