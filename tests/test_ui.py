import re
from pathlib import Path

import pytest

from comroster.services import model

STATIC_CSS = Path(__file__).resolve().parent.parent / "static" / "css"
SKINS_CSS = STATIC_CSS / "skins.css"
DISPLAY_CSS = STATIC_CSS / "display.css"


@pytest.fixture
def auth_client(client):
    client.post("/admin/setup", data={"password": "motdepasse8"})
    return client


def test_display_precharge_toutes_les_apparences(client):
    """Le `skin` change en direct par SSE, SANS rechargement de page.

    Deux conséquences, gardées ici parce que rien d'autre ne les tenait :
      1. `skins.css` doit être servi inconditionnellement — un `<link>` choisi
         côté serveur selon l'apparence courante ne serait jamais réévalué.
      2. Chaque apparence ACCEPTÉE par l'API doit avoir des règles dans ce
         fichier. Sans ce contrôle, ajouter une entrée à `SKINS` suffirait à
         produire un `data-skin` que personne ne style : l'écran retomberait en
         silence sur l'allure de base, sans erreur nulle part.
    """
    html = client.get("/display").get_data(as_text=True)
    assert "css/skins.css" in html

    css = SKINS_CSS.read_text(encoding="utf-8")
    sans_regles = [s for s in model.SKINS if f'data-skin="{s}"' not in css]
    assert sans_regles == [], f"apparences déclarées mais non stylées : {sans_regles}"


def test_transition_publication_declinee_par_apparence():
    """Chaque apparence doit DÉCIDER de son geste d'arrivée, aucune ne l'hérite en silence.

    `basique` pose les valeurs de référence dans display.css. Les autres ne peuvent pas
    reprendre son déplacement vertical : `lineaire` est un tableau réglé (`gap: 0`, un
    filet par case) qu'un glissement disloque, et `grille` une mosaïque bord à bord dont
    un déplacement ferait fuir le fond dans les gouttières. Une apparence ajoutée demain
    hériterait pourtant du lift de `basique` sans que rien ne bronche — c'est exactement
    le défaut que ce projet répète. On exige donc une redéfinition explicite.
    """
    base = DISPLAY_CSS.read_text(encoding="utf-8")
    for jeton in ("--anim-out", "--anim-in", "--anim-stagger", "--anim-cap", "--anim-lift"):
        assert f"{jeton}:" in base, f"{jeton} n'est pas défini pour l'apparence de base"

    css = SKINS_CSS.read_text(encoding="utf-8")
    muettes = [
        s for s in model.SKINS
        if s != "basique"
        and not re.search(rf'\[data-skin="{s}"\][^{{}}]*\{{[^{{}}]*--anim-lift\s*:', css)
    ]
    assert muettes == [], (
        f"apparences qui n'ont pas décidé de leur geste d'arrivée : {muettes} — "
        "elles héritent du déplacement de `basique`, qui casse leur structure"
    )


def test_transition_publication_toujours_coupee_par_le_mode_performance():
    """Aucune règle d'animation ne doit échapper à la garde du mode performance.

    La garde principale vit dans display.js (il rend directement, sans timer) ; celle-ci
    est le second filet, et c'est elle qui tiendra quand on ajoutera une règle plus tard.
    """
    sans_garde = []
    for feuille in (DISPLAY_CSS, SKINS_CSS):
        for regle in feuille.read_text(encoding="utf-8").split("}"):
            selecteur = regle.split("{")[0]
            if "data-anim" in selecteur and ':not([data-perf="on"])' not in selecteur:
                sans_garde.append(f"{feuille.name}: {' '.join(selecteur.split())}")
    assert sans_garde == [], (
        f"règles d'animation actives en mode performance : {sans_garde}"
    )


def test_admin_page_renders(auth_client):
    r = auth_client.get("/admin")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "js/admin.js" in html
    # admin.css est AUTONOME (source : design/maquette-admin-7.html) : recharger
    # main.css réintroduirait l'héritage global qui faussait la refonte.
    assert "css/main.css" not in html
    assert "css/admin.css" in html
    assert 'id="publish-btn"' in html      # bouton de publication (libellé « Publier »)
    assert "csrf-token" in html


def test_admin_un_bouton_par_fonction(auth_client):
    """Chaque fonction a UN accès : pas de lanceurs en doublon (revue 2026-07-25)."""
    html = auth_client.get("/admin").get_data(as_text=True)
    assert 'data-tab="journal"' in html             # Journal = panneau (entrée du menu)
    assert 'href="/admin/journal"' not in html      # …et plus une page qu'on va ouvrir
    assert "journal-dialog" not in html             # plus de dialogue Journal
    assert "data-launch" not in html                # aucun onglet-lanceur en doublon
    assert 'id="add-beltpack-btn"' not in html      # ajout beltpack = réserve seule
    assert 'id="status-preview"' not in html        # aperçu = témoin « Affichage en cours »
    assert ">Historique<" in html                   # entrée latérale des publications passées


def test_admin_has_antenna_panel(auth_client):
    html = auth_client.get("/admin").get_data(as_text=True)
    assert 'id="antenna-btn"' in html
    assert 'id="antenna-dialog"' in html
    assert "antenna-wizard" in html
    assert "antenna-dashboard" in html
    assert "import-dialog" in html
    assert "settings-dialog" not in html      # ancien dialog retiré


def test_admin_color_palette_replaces_native_picker(auth_client):
    html = auth_client.get("/admin").get_data(as_text=True)
    assert 'id="color-dialog"' in html          # palette bornée
    assert 'id="color-grid"' in html
    assert 'type="color"' not in html            # plus de sélecteur natif illisible


def test_admin_has_configs_and_selection(auth_client):
    html = auth_client.get("/admin").get_data(as_text=True)
    assert "configs-dialog" in html
    assert 'id="configs-btn"' in html
    assert "ranges-list" in html
    assert "selection-bar" in html           # sélection par clic direct (plus de bouton dédié)
    assert 'id="selection-delete"' in html


def test_les_commandes_de_fichier_vivent_dans_le_dialogue_configs(auth_client):
    """Importer / Exporter sont DANS le dialogue « Configurations », plus dans la latérale.

    Assertion d'APPARTENANCE, pas de présence : un `assert 'id="export-btn"' in html`
    resterait vert si le bouton était resté dans la barre latérale, et ne garderait donc
    rien du déplacement. On découpe le dialogue (ils ne s'imbriquent pas) et on regarde
    dedans, puis dans le reste du document.
    """
    html = auth_client.get("/admin").get_data(as_text=True)
    dialogue = re.search(r'<dialog id="configs-dialog".*?</dialog>', html, re.DOTALL)
    assert dialogue, "dialogue Configurations introuvable"
    dedans = dialogue.group(0)
    dehors = html.replace(dedans, "")

    for cible in ('id="import-btn"', 'id="import-input"', 'id="export-btn"'):
        assert cible in dedans, f"{cible} devrait être dans le dialogue"
        assert cible not in dehors, f"{cible} traîne encore hors du dialogue"

    # Le sélecteur de fichiers reste ouvrable : le bouton ne peut pas s'en passer.
    assert 'type="file"' in dedans
    # La latérale « Données » n'a plus ses deux rangées de fichier.
    assert "import-label" not in html


# --------------------------------------------------------------------------
# Apparence de l'administration : le choix vient d'un cookie, donc de
# l'utilisateur — il ne doit JAMAIS atterrir tel quel dans un attribut.
# `re` et `pytest` sont déjà importés en tête de ce fichier.
# --------------------------------------------------------------------------
@pytest.mark.parametrize("cookie,attendu", [
    (None, "auto"),          # aucun choix : on suit le système
    ("auto", "auto"),
    ("day", "day"),
    ("night", "night"),
])
def test_le_cookie_de_theme_pilote_l_attribut(auth_client, cookie, attendu):
    if cookie:
        auth_client.set_cookie("comroster_theme", cookie)
    html = auth_client.get("/admin").get_data(as_text=True)
    assert f'data-theme="{attendu}"' in html


@pytest.mark.parametrize("hostile", [
    'night" onload="alert(1)',        # évasion d'attribut
    "<script>alert(1)</script>",
    "jour",                            # simplement inconnue
    "",
    "DAY",                             # la casse n'est pas une valeur admise
])
def test_un_cookie_hostile_ou_inconnu_retombe_sur_auto(auth_client, hostile):
    """Une valeur de cookie est une DONNÉE UTILISATEUR. Rendue sans liste blanche
    dans un attribut HTML, elle en sort — Jinja échappe les guillemets, mais on ne
    veut pas dépendre de cet échappement pour une valeur qui n'a que trois formes
    légitimes. La liste blanche est la garde, l'échappement n'est que le filet."""
    auth_client.set_cookie("comroster_theme", hostile)
    html = auth_client.get("/admin").get_data(as_text=True)
    assert 'data-theme="auto"' in html
    assert "onload" not in html
    assert "<script>alert" not in html


def _cran(html, valeur):
    """La balise ENTIÈRE du cran demandé. On remonte à l'ouverture du `<button>`
    et non au seul `data-theme-choice` : les attributs sont répartis sur
    plusieurs lignes, et certains — `role` notamment — le précèdent."""
    repere = html.index(f'data-theme-choice="{valeur}"')
    debut = html.rindex("<button", 0, repere)
    return html[debut:html.index("</button>", debut)]


def test_le_pied_porte_un_inverseur_d_apparence_accessible(auth_client):
    """Un inverseur à trois positions EST un choix exclusif : `radiogroup` et
    `radio`, pas un groupe de boutons-poussoirs. Les trois crans sont muets à
    l'écran — c'est le curseur qui dit lequel est actif — donc chacun porte un nom
    accessible, sans quoi un lecteur d'écran annoncerait trois boutons vides."""
    html = auth_client.get("/admin").get_data(as_text=True)
    pied = html[html.index('<footer class="admin-status"'):html.index("</footer>")]
    assert 'class="s theme-switch"' in pied
    assert 'role="radiogroup"' in pied
    for valeur, libelle in (("auto", "Auto"), ("day", "Clair"), ("night", "Sombre")):
        cran = _cran(pied, valeur)
        assert 'role="radio"' in cran
        assert f'aria-label="{libelle}"' in cran


def test_l_inverseur_reflete_le_cookie_des_le_rendu_serveur(auth_client):
    """`aria-checked`, la position du curseur et le mot affiché doivent dire la
    vérité AVANT qu'aucun script ne tourne. La CSP interdit les scripts en ligne :
    il n'existe aucune occasion de corriger l'état entre le rendu et l'affichage."""
    auth_client.set_cookie("comroster_theme", "day")
    html = auth_client.get("/admin").get_data(as_text=True)
    assert 'aria-checked="true"' in _cran(html, "day")
    assert 'aria-checked="false"' in _cran(html, "auto")
    # Un groupe radio n'expose qu'un seul arrêt de tabulation.
    assert 'tabindex="0"' in _cran(html, "day")
    assert 'tabindex="-1"' in _cran(html, "auto")
    assert 'data-pos="day"' in html, "le curseur ne part pas au bon cran"
    assert ">Clair</b>" in html, "le mot affiché ne dit pas l'état"


def test_les_deux_reglages_de_luminosite_nomment_leur_objet(auth_client):
    """L'admin porte DEUX réglages de luminosité : le sien, dans le pied, et celui
    de l'écran de régie, dans Réglages → Écran. Tant qu'aucun des deux ne nommait
    son objet, ils se confondaient.

    Trois signaux se répondent, et aucun ne suffit seul : le libellé de portée du
    pied, l'infobulle qui renvoie à l'autre réglage, et le nom explicite de celui
    de l'écran. Cette garde empêche un futur nettoyage de libellés de rouvrir la
    confusion."""
    html = auth_client.get("/admin").get_data(as_text=True)
    pied = html[html.index('<footer class="admin-status"'):html.index("</footer>")]
    assert "cette interface" in pied, "le sélecteur du pied ne nomme pas sa portée"
    assert "Réglages → Écran" in pied, "l'infobulle ne renvoie pas à l'autre réglage"
    assert "Luminosité de l'écran de régie" in html, \
        "le réglage de l'écran de régie ne nomme pas son objet"


def test_display_page_renders(client):
    r = client.get("/display")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "js/display.js" in html
    assert "css/main.css" in html
    assert "display-grid" in html


def test_display_template_error_is_not_swallowed(client, monkeypatch):
    # Politique appliance : fail-safe sur les DONNÉES, jamais de masquage des BUGS.
    # Une erreur de template doit remonter (500/exception), pas un faux "OK".
    import pytest

    import comroster.display as display_mod

    def boom(*args, **kwargs):
        raise RuntimeError("template cassé")
    monkeypatch.setattr(display_mod, "render_template", boom)
    with pytest.raises(RuntimeError):
        client.get("/display")


def test_display_has_no_inline_style_block(client):
    # CSP stricte (default-src 'self') : tout <style>/style inline est bloqué par le
    # navigateur → mise en page cassée. Le CSS du display doit être un fichier statique.
    html = client.get("/display").data.decode()
    assert "<style" not in html
    assert "/static/css/display.css?v=" in html


def test_display_reflects_perf_mode(app, client):
    # Le mode perf publié doit produire data-perf="on" sur le body du display,
    # ce qui déclenche la surcharge CSS (flou désactivé).
    from comroster.services import model
    st = model.empty_state()
    st["perf"] = True
    app.extensions["storage"].save_published(st)
    html = client.get("/display").data.decode()
    assert 'data-perf="on"' in html

def test_display_perf_off_by_default(client):
    html = client.get("/display").data.decode()
    assert 'data-perf="off"' in html


def _fragment(html, debut, fin):
    """Découpe le fragment de `html` entre deux marqueurs.

    On borne sur des balises FERMANTES de conteneur (`</nav>`, `</aside>`) et non sur
    `</div>`, qui serait ambigu : le panneau contient lui-même des `<div>` séparateurs.
    """
    i = html.index(debut)
    return html[i:html.index(fin, i)]


def test_reglages_regroupe_les_fonctions_boitier(auth_client):
    """Les six fonctions du boîtier vivent dans le menu, et NULLE PART AILLEURS.

    Le comptage à 1 est le cœur du test : il échoue aussi bien si une fonction est
    perdue (0) que si un ancien accès survit ou revient (2). C'est exactement le
    défaut relevé à la revue du 2026-07-25 (« Système » ouvrait le dialogue de
    « Réseau », l'aperçu était accessible à deux endroits).
    """
    html = auth_client.get("/admin").get_data(as_text=True)

    menu = _fragment(html, 'id="settings-menu"', "</nav>")
    for cible in ('id="network-btn"', 'id="backup-btn"',
                  'id="password-btn"', ">Santé<", ">Journal<"):
        assert cible in menu, f"{cible} absent du menu Réglages"
        assert html.count(cible) == 1, f"{cible} a {html.count(cible)} accès, il en faut 1"
    # Redémarrer, lui, RESTE au pied de la latérale (choix Nathan) : il voisine l'autre
    # action de sortie, et une action destructrice ne traîne pas dans un menu qu'on parcourt.
    assert 'id="reboot-btn"' not in menu
    assert html.count('id="reboot-btn"') == 1

    # Le déclencheur annonce son panneau, et le panneau part fermé.
    assert 'id="settings-btn"' in html
    assert 'aria-expanded="false"' in html
    assert 'aria-controls="settings-menu"' in html
    assert 'id="settings-menu" role="menu" hidden' in html

    # Anciens emplacements : la section « Boîtier » de la latérale n'existe plus, et le
    # pied ne garde que la déconnexion.
    assert "Boîtier" not in html
    pied = _fragment(html, 'class="side-foot"', "</aside>")
    assert "logout-link" in pied
    assert "reboot-btn" in pied


# --------------------------------------------------------------------------
# Palette claire : deux fois pour garantir que les deux copies ne divergent
# --------------------------------------------------------------------------
ADMIN_CSS = (STATIC_CSS / "admin.css").read_text(encoding="utf-8")


def _bloc(depart):
    """Le bloc CSS ouvert à `depart`, jusqu'à son accolade fermante en colonne 0."""
    d = ADMIN_CSS.index(depart)
    return ADMIN_CSS[d:ADMIN_CSS.index("\n}", d)]


def _declarations(bloc):
    """Les paires jeton/valeur, mises à plat — l'indentation et les commentaires
    diffèrent entre les deux copies, pas les valeurs."""
    return re.findall(r"(--[a-z0-9-]+)\s*:\s*([^;]+);", bloc)


def test_les_deux_palettes_claires_sont_identiques():
    """La palette claire est écrite DEUX fois : sous la media query pour le mode
    auto, sous l'attribut pour le mode forcé. Aucune construction CSS ne partage
    un bloc entre une media query et un sélecteur — c'est le coût du CSS nu.

    Deux copies qui divergent est le mode de panne garanti : cette garde est ce
    qui rend la duplication tenable."""
    auto = _declarations(_bloc('body[data-theme="auto"]'))
    force = _declarations(_bloc('body[data-theme="day"]'))
    assert auto == force, "les deux palettes claires ont divergé"


def test_le_theme_clair_redefinit_toutes_les_couleurs_du_sombre():
    """Un jeton oublié laisse un aplat sombre au milieu d'une page claire, et
    rien ne le signale — ni test, ni erreur, ni console."""
    def couleurs(bloc):
        # "var" est inclus : un jeton défini en `var(--autre-jeton)` (--primary,
        # alias de --accent) est une couleur au même titre qu'un littéral — la
        # garde doit le voir passer si sa redéfinition claire manque, exactement
        # le trou qui a laissé --primary figé sur l'accent sombre partout.
        return {n for n, v in _declarations(bloc) if v.strip().startswith(("#", "rgb", "var"))}
    manquants = couleurs(_bloc(":root {")) - couleurs(_bloc('body[data-theme="day"]'))
    assert not manquants, f"jetons non redéfinis en clair : {sorted(manquants)}"


#: Littéraux de couleur TOLÉRÉS hors du :root d'admin.css. La liste est CLOSE :
#: en ajouter un fera échouer ce test, ce qui force la décision au moment de
#: l'écriture. C'est la réponse directe à la leçon du 2026-08-11 — le thème clair
#: des pages d'authentification a rendu invisible un glyphe dont la couleur était
#: figée dans son fichier, sans qu'aucun des 636 tests ne bronche.
LITTERAUX_TOLERES = {
    # Encre calculée par static/js/ink.js (inkFor) : verdict "dark"/"light" tiré
    # de la LUMINANCE de la couleur du groupe (--gel, palette fixe choisie par
    # l'utilisateur), pas du thème de l'administration. La couleur d'un groupe
    # ne change pas entre jour et nuit — l'encre qui la rend lisible ne doit
    # donc pas suivre le thème non plus. Paire fixe : #141005 (encre sombre) /
    # #F4F7FB (encre claire), utilisée par .admin-block[data-ink] et
    # .board-table .bt-assign[data-ink].
    "#141005",
    "#F4F7FB",
    # Bouton "confirm-danger" : texte blanc fixe sur fond --error, préexistant à
    # cette tâche. Il ne DÉPEND PAS du thème (raison de sa présence ici), mais il
    # ne le RÉUSSIT pas pour autant : au seuil d'ink.js (0.179), la luminance de
    # --error sombre (F04D3E, 0.24) appelle une encre SOMBRE, pas blanche — et le
    # contraste réel (~3,6:1) est sous les 4,5:1 AA pour du texte courant. En
    # clair (C0392B, luminance 0.14) le blanc passe (~5,4:1). Corriger ça change
    # l'ALLURE d'un bouton établi (nouvelle encre à choisir), ce qui dépasse le
    # cadre de cette tâche (faire suivre le thème à des littéraux) ; signalé
    # pour un correctif d'accessibilité séparé, pas corrigé ici.
    "#FFFFFF",
    # Trame de la feuille d'impression (.print-frame) : simule une page de
    # papier, TOUJOURS blanche, quel que soit le thème de l'écran qui la montre.
    "#ffffff",
    # Fond des trois cadres d'aperçu de l'écran display (.screen-preview-frame,
    # .preview-tile-frame, .preview-frame) : simule l'écran/kiosk réel derrière
    # l'iframe pendant son chargement — un noir de "moniteur éteint", indépendant
    # du thème de l'administration qui l'affiche.
    "#000",
    # Huit couleurs qui se posent sur --gel, la couleur du GROUPE (donnée du
    # plateau choisie par l'utilisateur), invariante au thème — même raison que
    # la paire d'encre #141005/#F4F7FB ci-dessus. Chacune restaurée à sa valeur
    # de thème sombre : .block-header (filet), .person + .person (séparateur),
    # .person:hover (survol), .person.selected (fond — l'ancien voile turquoise à
    # 14 % était déjà jugé invisible sur les gels colorés, et le thème clair
    # ramenait --ombre à 10 %, exactement ce défaut), .bp-dot.on (anneau et
    # couleur), .bp-batt.low (couleur), .color-swatch (liseré). Les séparateur et
    # survol avaient chacun leur propre intensité AVANT jetonisation (0.1 et
    # 0.12) ; les rabattre sur le même jeton --ombre-faible (0.17) les avait
    # toutes deux intensifiées de 40 à 70 % en thème nocturne — la garde ci-après
    # empêche ce genre de dérive de repasser inaperçue.
    "rgb(0 0 0 / 0.17)",
    "rgb(0 0 0 / 0.3)",
    "rgb(0 0 0 / 0.1)",
    "rgb(0 0 0 / 0.12)",
    "#E8A13A",
    "#2ECC71",
    # Repli de `.admin-dialog::backdrop { background: var(--ombre-scrim, …) }` : sur un
    # moteur antérieur à 2024 (Chrome 122, Firefox 125, Safari 17.4), `::backdrop`
    # n'hérite pas des propriétés personnalisées de son élément d'origine et
    # `var(--ombre-scrim)` seul y serait invalide — voile totalement transparent, dans
    # les deux thèmes. Littéral égal à la valeur NOCTURNE de --ombre-scrim : un vieux
    # moteur n'aurait de toute façon pas appliqué la palette claire.
    "rgb(4 6 10 / 0.62)",
}


def test_aucune_couleur_en_dur_non_justifiee_dans_admin_css():
    hors_root = ADMIN_CSS.replace(_bloc(":root {"), "")
    hors_root = re.sub(r"/\*.*?\*/", "", hors_root, flags=re.S)   # les commentaires citent des couleurs
    for bloc in ('body[data-theme="auto"]', 'body[data-theme="day"]'):
        hors_root = hors_root.replace(_bloc(bloc), "")
    trouvees = set(re.findall(r"#[0-9A-Fa-f]{3,8}\b|rgba?\([^)]*\)", hors_root))
    surplus = trouvees - LITTERAUX_TOLERES
    assert not surplus, (
        "couleurs en dur non justifiées — les promouvoir en jetons pour "
        "qu'elles suivent le thème, ou les ajouter à LITTERAUX_TOLERES avec "
        f"un commentaire disant pourquoi elles n'en dépendent pas : {sorted(surplus)}")
