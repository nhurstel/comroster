"""Garde : les boutons PLEINS de l'admin portent une encre lisible, dans les DEUX thèmes.

Pourquoi ce fichier existe. Le 2026-08-13, la revue du thème jour/nuit a relevé deux
boutons rouges sous le seuil AA : `.confirm-danger` à 3,60:1 en nuit, et
`.selection-bar .danger-btn` à 3,18:1 en nuit comme en jour. Aucun test ne les a vus.

La garde anti-couleurs-en-dur ne POUVAIT pas les voir : elle cherche des LITTÉRAUX, et la
couleur de ces boutons passe par un jeton (`var(--error)`, `var(--fg)`). Un contraste ne
se contrôle pas en cherchant une chaîne — il se CALCULE. C'est ce que fait ce fichier.

La règle appliquée n'est pas un goût, elle est déjà écrite dans `admin.css` (décision du
2026-07-25) et dans `ink.js` pour l'écran : **luminance > 0,179 ⇒ encre sombre sur fond
plein**. `--error` en nuit vaut 0,242 — la même que `--accent`, qui lui obéit depuis
toujours. Les deux boutons rouges étaient simplement les seuls hors-règle.
"""
import os
import re

import pytest

ADMIN_CSS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "css", "admin.css"
)

#: Seuil AA pour du texte courant. Les libellés de ces boutons sont en taille normale :
#: le palier « texte large » (3:1) ne leur est pas ouvert.
SEUIL_AA = 4.5

#: Seuil de la règle d'encre du projet — la même constante que `static/js/ink.js`.
SEUIL_ENCRE = 0.179

#: Les boutons pleins de l'administration : (libellé, jeton de FOND, jeton d'ENCRE).
#: Le fond au survol compte autant que le fond au repos : un bouton illisible sous le
#: doigt reste illisible.
BOUTONS = [
    ("Confirmer un redémarrage", "--error", "--on-error"),
    ("Confirmer un redémarrage, survol", "--error-lt", "--on-error"),
    ("Supprimer la sélection", "--error", "--on-error"),
    ("Redémarrer", "--warning", "--on-accent"),
    ("Redémarrer, survol", "--warning-lt", "--on-accent"),
]

#: Le thème nuit est le socle : ses jetons vivent dans `:root`. Le thème jour est déclaré
#: deux fois — choix explicite et `prefers-color-scheme` pour « auto ». On mesure la
#: déclaration explicite ; `test_ui.test_les_deux_palettes_claires_sont_identiques` prouve
#: par ailleurs que les deux blocs clairs ne divergent pas.
THEMES = {
    "nuit": r":root\s*\{(.*?)\n\}",
    "jour": r'body\[data-theme="day"\]\s*\{(.*?)\n\}',
}


def _luminance(hexa):
    """Luminance relative WCAG — même formule que `inkFor()` dans ink.js."""
    hexa = hexa.lstrip("#")
    canaux = []
    for i in (0, 2, 4):
        c = int(hexa[i:i + 2], 16) / 255
        canaux.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    rouge, vert, bleu = canaux
    return 0.2126 * rouge + 0.7152 * vert + 0.0722 * bleu


def _contraste(encre, fond):
    a, b = _luminance(encre), _luminance(fond)
    haut, bas = max(a, b), min(a, b)
    return (haut + 0.05) / (bas + 0.05)


def _jetons(theme):
    """Les jetons hexadécimaux d'un thème, lus dans SON bloc et lui seul."""
    with open(ADMIN_CSS, encoding="utf-8") as fh:
        css = fh.read()
    # DOTALL, pas son alias `re.S` : la leçon du dépôt sur ce drapeau mérite qu'il se
    # lise. Le motif reste NON gourmand (`.*?`) et borné à `\n}` — un point gourmand ici
    # avalerait les blocs suivants et le test mesurerait le mauvais thème.
    bloc = re.search(THEMES[theme], css, re.DOTALL)
    assert bloc, f"bloc de thème « {theme} » introuvable — le test ne prouverait rien"
    return dict(re.findall(r"(--[a-zA-Z0-9-]+)\s*:\s*(#[0-9A-Fa-f]{6})\s*;", bloc.group(1)))


@pytest.mark.parametrize("theme", sorted(THEMES))
@pytest.mark.parametrize("libelle,fond,encre", BOUTONS, ids=[b[0] for b in BOUTONS])
def test_les_boutons_pleins_tiennent_le_seuil_aa(theme, libelle, fond, encre):
    jetons = _jetons(theme)
    for nom in (fond, encre):
        assert nom in jetons, f"[{theme}] le jeton {nom} n'est pas défini dans ce thème"
    mesure = _contraste(jetons[encre], jetons[fond])
    assert mesure >= SEUIL_AA, (
        f"[{theme}] « {libelle} » : {jetons[encre]} sur {jetons[fond]} = {mesure:.2f}:1, "
        f"sous le seuil AA de {SEUIL_AA}:1. Appliquer la règle d'encre du projet "
        f"(luminance > {SEUIL_ENCRE} ⇒ encre sombre) plutôt que de chercher une teinte."
    )


@pytest.mark.parametrize("theme", sorted(THEMES))
def test_l_encre_des_boutons_rouges_suit_la_regle_de_luminance(theme):
    """Le seuil peut être franchi par chance ; la règle, elle, se vérifie.

    Pendant du test précédent : celui-là ne demande pas « est-ce lisible ? » mais
    « l'encre est-elle celle que la règle impose ? ». C'est lui qui empêchera de rattraper
    un jour un contraste en bricolant une teinte au lieu de retourner l'encre.
    """
    jetons = _jetons(theme)
    encre_claire = _luminance(jetons["--on-error"]) > 0.5
    fond_vif = _luminance(jetons["--error"]) > SEUIL_ENCRE
    assert fond_vif != encre_claire, (
        f"[{theme}] --error vaut {jetons['--error']} "
        f"(luminance {_luminance(jetons['--error']):.3f}) : la règle impose une encre "
        f"{'SOMBRE' if fond_vif else 'CLAIRE'}, or --on-error vaut {jetons['--on-error']}."
    )
