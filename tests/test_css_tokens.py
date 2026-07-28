"""Garde : toute variable CSS utilisée doit être DÉFINIE quelque part.

Une `var(--x)` sans `--x` ne casse pas bruyamment — elle retombe en silence sur son
fallback, ou sur rien. C'est ce qui avait fait rendre toute l'admin en police système
(`var(--font-mono, monospace)` sans `--font-mono` défini) sans qu'aucun test ne bronche,
et je viens de le refaire en écrivant `--a-line` là où le jeton s'appelle `--border`
(audit 2026-07-28, leçon 2026-07-25).

Le contrôle est purement textuel : c'est suffisant, parce que le défaut est précisément
une faute de FRAPPE dans un nom, pas une subtilité de cascade.
"""
import os
import re

import pytest

STATIC_CSS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "css"
)

#: Feuilles chargées ensemble : une variable définie dans main.css est légitimement
#: utilisable dans display.css ou skins.css. admin.css et print.css sont AUTONOMES —
#: elles ne chargent pas main.css, elles doivent donc se suffire.
GROUPES = {
    "écran de régie": ["main.css", "display.css", "skins.css"],
    "administration": ["admin.css"],
    "connexion": ["main.css", "auth.css"],
    "feuille imprimable": ["print.css"],
}

DEFINITION = re.compile(r"(--[a-zA-Z0-9_-]+)\s*:")
USAGE = re.compile(r"var\(\s*(--[a-zA-Z0-9_-]+)")


def _lire(noms):
    texte = []
    for nom in noms:
        chemin = os.path.join(STATIC_CSS, nom)
        if os.path.exists(chemin):
            with open(chemin, encoding="utf-8") as fh:
                texte.append(fh.read())
    return "\n".join(texte)


@pytest.mark.parametrize("groupe", sorted(GROUPES))
def test_aucune_variable_css_utilisee_sans_etre_definie(groupe):
    css = _lire(GROUPES[groupe])
    assert css, f"aucune feuille lue pour « {groupe} » — le test ne prouverait rien"
    definies = set(DEFINITION.findall(css))
    # Les variables posées par le JS (CSSOM) ne peuvent pas être vues ici.
    definies |= {"--block-accent", "--block-ink", "--gel", "--swatch-color",
                 "--title-fs", "--role-fs", "--bpn-fs",
                 "--anim-i"}   # rang du bloc, posé par render() (display.js)
    utilisees = set(USAGE.findall(css))
    orphelines = sorted(utilisees - definies)
    assert not orphelines, (
        f"[{groupe}] variables utilisées mais jamais définies : {orphelines} — "
        "elles retombent en silence sur leur fallback"
    )
