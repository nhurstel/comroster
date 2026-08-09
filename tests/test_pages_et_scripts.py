"""Chaque script trouve-t-il, dans la page qui le charge, les éléments qu'il adresse ?

Un `getElementById` qui ne trouve rien ne casse pas : le code qui suit est presque
toujours protégé par un `if (el)`, écrit pour être robuste. Cette prudence transforme la
disparition d'un élément en silence — c'est ainsi que `display.js` a écrit cinq messages
d'état dans `#sync-hint` et `#admin-hint` pendant trois semaines après leur retrait
volontaire du template (2026-07-13), sans qu'aucun test ni aucun œil ne le voie.

La garde existait déjà, mais pour deux scripts seulement (`journal.js`, `health.js` face à
`admin.html`), écrite à la fusion des panneaux. Elle vaut pour tous les couples, et elle
les DÉCOUVRE au lieu de les énumérer : une liste tenue à la main dérive au premier script
ajouté — c'est le défaut de fond que ce dépôt a déjà payé trois fois (`skin`,
`production_name`, `text_scale`).
"""
import re
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent
TEMPLATES = RACINE / "templates"
JS = RACINE / "static" / "js"

#: Route servant chaque template PORTEUR DE SCRIPT. Confrontée au dossier `templates/`
#: par `test_aucune_page_a_script_hors_garde` : un template qui gagne un `<script src>`
#: sans entrer ici fait tomber la garde, au lieu d'échapper au contrôle en silence.
PAGES = {
    "display.html": "/display",
    "admin.html": "/admin",
    "print.html": "/admin/print",
    "login.html": "/admin/login",
    "setup.html": "/admin/setup",
}

#: Pages qui n'existent que sur un boîtier SANS administrateur. `/admin/setup` redirige
#: vers la connexion dès qu'un mot de passe est posé : la rendre avec un client
#: authentifié aurait gardé la page de login une deuxième fois en croyant garder setup —
#: un vert qui ne prouve rien.
VIERGE = {"setup.html"}


def _scripts_charges(html):
    """Scripts du dépôt que la page charge, modules importés compris.

    `print.js` est un `type="module"` qui importe `printopts.js` : s'arrêter aux balises
    `<script src>` laisserait ce second fichier hors garde alors qu'il vit dans la page.
    """
    noms = set(re.findall(r"js/([a-z_]+\.js)", html))
    a_suivre = list(noms)
    while a_suivre:
        source = (JS / a_suivre.pop()).read_text(encoding="utf-8")
        for importe in re.findall(r'from\s+"\./([a-z_]+\.js)"', source):
            if importe not in noms:
                noms.add(importe)
                a_suivre.append(importe)
    return sorted(noms)


def _ids_poses_par(source):
    """Identifiants que le script CRÉE lui-même : ils n'ont pas à être dans le template.

    `admin.js` fabrique son conteneur de toasts au premier message (`t.id = "cr-toast"`)
    plutôt que de le laisser dormir dans le balisage de toutes les pages.
    """
    return set(re.findall(r'\.id\s*=\s*"([^"]+)"', source)) | set(
        re.findall(r'id="([^"]+)"', source))


@pytest.mark.parametrize("template,route", sorted(PAGES.items()))
def test_les_scripts_trouvent_ce_quils_adressent(client, template, route):
    """Lu sur la page RENDUE : un id posé dans une branche Jinja jamais prise ne compte pas.

    L'authentification est posée ici plutôt que par la fixture `auth_client` : celle-ci
    partage l'application de `client`, donc demander les deux aurait configuré le boîtier
    pour tout le monde — et `/admin/setup` aurait répondu par une redirection vers la
    connexion, que l'on aurait gardée en croyant garder setup.
    """
    if template not in VIERGE:
        client.post("/admin/setup", data={"password": "motdepasse8"})
    html = client.get(route).get_data(as_text=True)
    scripts = _scripts_charges(html)
    assert scripts, f"{route} ne charge aucun script du dépôt : la découverte est à revoir"

    absents = {}
    for nom in scripts:
        source = (JS / nom).read_text(encoding="utf-8")
        adresses = set(re.findall(r'getElementById\("([^"]+)"\)', source))
        manquants = sorted(i for i in adresses - _ids_poses_par(source)
                           if f'id="{i}"' not in html)
        if manquants:
            absents[nom] = manquants
    assert absents == {}, f"{template} : des scripts écrivent dans le vide → {absents}"


def test_aucune_page_a_script_hors_garde():
    """Un template qui gagne un script doit entrer dans `PAGES`, pas y échapper.

    Sans ce contrôle, la garde ci-dessus resterait figée sur les trois pages du jour et
    ne dirait plus rien de la quatrième — le sort exact de la version « journal.js et
    health.js » qu'elle remplace.
    """
    sources = {f.name: f.read_text(encoding="utf-8") for f in TEMPLATES.glob("*.html")}
    # Un template hérite des scripts de son parent. Sans suivre `extends`, un cadre
    # commun deviendrait un angle mort : il porterait le script, ses enfants seraient
    # les seuls servis, et aucun des trois n'entrerait dans la garde.
    parent = {
        nom: m.group(1)
        for nom, src in sources.items()
        if (m := re.search(r'{%\s*extends\s+"([^"]+)"', src))
    }

    def porte_un_script(nom, vus=()):
        if nom in vus or nom not in sources:
            return False
        if re.search(r'<script[^>]+src="[^"]*js/', sources[nom]):
            return True
        suivant = parent.get(nom)
        return bool(suivant) and porte_un_script(suivant, (*vus, nom))

    # Un cadre étendu par d'autres n'est jamais servi seul : il n'a pas de route propre,
    # c'est l'enfant qui en a une. L'exiger dans PAGES réclamerait une entrée pour une
    # page qui n'existe pas.
    cadres = set(parent.values())
    porteurs = {nom for nom in sources if porte_un_script(nom) and nom not in cadres}
    assert porteurs == set(PAGES), (
        f"templates porteurs de script non gardés : {sorted(porteurs - set(PAGES))} · "
        f"entrées de PAGES sans script : {sorted(set(PAGES) - porteurs)}"
    )
