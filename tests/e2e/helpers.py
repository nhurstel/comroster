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


def se_reconnecter(page, base):
    """Reconnexion sur un boîtier DÉJÀ configuré — le geste d'un utilisateur dont la
    session a expiré.

    `enter_admin` ne convient pas ici : il passe par /admin/setup, qui redirige vers la
    connexion dès qu'un administrateur existe. Appelé deux fois, il attend donc un
    bouton « Accéder à l'administration » qui n'apparaîtra jamais.
    """
    page.goto(base + "/admin/login")
    page.fill("input[name=password]", MOT_DE_PASSE)
    page.click("button[type=submit]")
    page.wait_for_selector("#add-block-btn")


def ouvrir_ajout_beltpack(page):
    """Clique « ajouter un beltpack », où qu'il soit.

    La fonction n'a qu'UN accès à la fois, mais son emplacement suit l'état de la
    réserve : au pied du panneau quand elle est ouverte, sur le rail quand elle s'est
    repliée — ce qui arrive dès que tous les beltpacks sont affectés, c'est-à-dire dans
    le cas nominal (refonte 2026-08-14). Un sélecteur en dur dans dix fichiers, c'est dix
    corrections le jour où l'état change ; ce helper est le seul à connaître les deux.
    """
    if page.is_visible("#add-beltpack-pool"):
        page.click("#add-beltpack-pool")
    else:
        page.click("#pool-rail-add")


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

    Depuis que la réserve se replie en rail quand tout est affecté (refonte 2026-08-14),
    « ajouter un beltpack » a DEUX emplacements — le pied de la réserve ouverte, le « + »
    du rail replié — dont un seul est visible à la fois. Le défaut par défaut vise donc
    celui qui est réellement là, sinon le helper échoue dès que le plateau est complet,
    c'est-à-dire dans le cas nominal.
    """
    if ouvrir == "#add-beltpack-pool":
        ouvrir_ajout_beltpack(page)
    else:
        page.click(ouvrir)
    page.wait_for_selector("#person-dialog[open]")
    page.fill("#person-beltpack", numero)
    # L'application RÉAGIT au numéro : elle propose le rôle déjà connu pour ce beltpack
    # et, s'il est inconnu, VIDE le champ rôle (admin.js, écouteur `input` de
    # #person-beltpack). Écrire le rôle avant que cette réaction n'ait eu lieu le fait
    # donc effacer — c'est ce qui sortait « BP 42 — » sur l'écran de régie en CI.
    page.fill("#person-role", role)
    # Vérification AVANT de soumettre : un formulaire soumis incomplet échoue plus tard,
    # ailleurs, sur une assertion qui ne parle pas de la vraie cause. Le contournement
    # (reposer la valeur si elle avait été effacée) a été RETIRÉ le 2026-08-09, la cause
    # étant corrigée dans admin.js : le garder masquerait une régression de ce correctif.
    assert page.input_value("#person-role") == role, (
        f"le champ rôle vaut « {page.input_value('#person-role')} » et non « {role} » : "
        "la proposition automatique l'a écrasé"
    )
    page.click("#person-form button[type=submit]")
    page.wait_for_selector(f".person .bp:has-text('{numero}')")
    page.wait_for_selector(f".person .role:has-text('{role}')")


def open_systeme(page, section="health"):
    """Ouvre l'onglet « Système » et va sur une de ses sept sections.

    Remplace `open_reglages` : le menu déroulant qu'elle ouvrait n'existe plus. Il
    mélangeait deux panneaux et trois dialogues sous un nom qui ne contenait aucun des
    réglages les plus manipulés — tout vit maintenant dans un rail, et chaque section
    est un vrai panneau (refonte 2026-08-14).

    L'attente est explicite : les panneaux sont pilotés par `hidden`, et un
    `wait_for_selector` sans état attend `visible` par défaut — c'est ce qui a fait
    expirer deux attentes dans ce dépôt (leçons 2026-07-23 et 2026-07-27).
    """
    page.click('.admin-tabs .tab[data-famille="systeme"]')
    page.wait_for_selector(".sys-rail", state="visible")
    if section != "health":
        page.click(f'.sys-rail .nav-item[data-tab="{section}"]')
    page.wait_for_selector(f'.tab-panel[data-panel="{section}"]:not([hidden])', state="visible")


def open_screen_tab(page):
    """Active l'onglet « Écran » et attend que ses champs soient réellement là.

    Les réglages d'écran (apparence, thème, colonnes, indicateurs) y vivent depuis la
    refonte admin : il faut l'activer avant d'agir sur eux, sinon Playwright refuse
    d'interagir avec des champs masqués.

    Promue ici depuis test_e2e.py (où elle s'appelait `_open_screen_tab`) au moment du
    découpage : ses appelants se répartissent en TROIS fichiers, et `test_audit_features`
    réinventait déjà le même clic en dur. Quatre copies d'un sélecteur, c'est quatre
    corrections le jour où l'onglet change de nom.
    """
    page.click('.admin-tabs .tab[data-tab="screen"]')
    page.wait_for_selector("#skin-select", state="visible")


def open_board_tab(page):
    """Revient à l'onglet « Affectations » (le bouton « + Groupe » y vit)."""
    page.click('.admin-tabs .tab[data-tab="board"]')
    page.wait_for_selector("#add-block-btn", state="visible")


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
