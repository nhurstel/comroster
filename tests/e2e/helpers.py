"""Gestes d'interface partagés par les e2e.

Une seule définition : les fonctions du boîtier vivent désormais dans un menu, et
sept tests existants cliquaient leurs boutons en direct. Recopier l'ouverture dans
chaque fichier reviendrait à entretenir deux versions du même geste.
"""


MOT_DE_PASSE = "motdepasse8"


def enter_admin(page, base):
    """Configuration initiale → connexion automatique → page d'administration.

    Sept fichiers portaient leur propre copie de ce parcours, à l'octet près. Ce n'était
    pas gratuit : renommer la classe du bouton de connexion (`auth-submit` → `auth-go`,
    2026-08-04) a coûté huit corrections au lieu d'une, et chaque copie manquait de la
    même attente. Une seule définition, désormais.
    """
    page.goto(base + "/admin/setup")
    page.fill("input[name=password]", MOT_DE_PASSE)
    page.click("button[type=submit]")
    page.click("a.auth-go")                 # « Accéder à l'administration »
    page.wait_for_selector("#add-block-btn")


def ajouter_beltpack(page, numero, role, ouvrir="#add-beltpack-pool"):
    """Ajoute un beltpack par le VRAI geste : ouvrir la boîte, saisir, soumettre.

    Les trois attentes ci-dessous ne sont pas du confort — chacune répare un flaky
    constaté en CI le 2026-08-09 :

    1. `#person-dialog[open]` AVANT d'écrire. `fill` sur un champ non encore affiché
       n'échoue pas bruyamment : il part en silence et le formulaire est soumis
       incomplet, produisant tantôt une personne sans rôle, tantôt aucune personne.
       Ce motif manquait à douze endroits, dans six fichiers.
    2. le numéro rendu, puis 3. le RÔLE rendu — attendre le seul numéro laissait passer
       une carte dont le champ rôle n'était pas encore là (`assert 'Régie' in ['']`).

    `ouvrir` sélectionne le point d'entrée : la réserve par défaut, ou la tuile de dépôt
    d'un groupe (`.block-items .drop-tile`) quand on veut affecter directement.
    """
    page.click(ouvrir)
    page.wait_for_selector("#person-dialog[open]")
    page.fill("#person-beltpack", numero)
    page.fill("#person-role", role)
    page.click("#person-form button[type=submit]")
    page.wait_for_selector(f".person .bp:has-text('{numero}')")
    page.wait_for_selector(f".person .role:has-text('{role}')")


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
