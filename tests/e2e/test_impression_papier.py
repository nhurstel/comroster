"""Le rendu PAPIER de la feuille d'impression, lu dans un vrai PDF.

Tous les autres tests portent sur le DOM. Aucun ne dit si une A3 sort correctement, et
les trois défauts corrigés en cours de lot (double pied, groupe coupé non réidentifié,
titre en petites capitales) n'ont été vus qu'en regardant le PDF — aucun n'aurait été
attrapé par une assertion sur le HTML.

Les capacités exercées ici (taille de page honorée, `position: fixed` répété par page,
numéro de page en boîte de marge) ont été MESURÉES avant d'être promises. Elles sont
spécifiques à Chromium, ce qui est acceptable : le boîtier en est un.
"""
import shutil
import subprocess

import pytest

pytestmark = pytest.mark.e2e

besoin_poppler = pytest.mark.skipif(
    shutil.which("pdftotext") is None or shutil.which("pdfinfo") is None,
    reason="poppler absent — seul moyen de LIRE le PDF plutôt que de le supposer",
)

#: Au-delà de `SEUIL_GROUPE_LONG` (12), un groupe devient coupable. Il en faut un ici,
#: sinon le test de réidentification ne mordrait sur rien.
GROUPE_LONG = 14


#: Composition du plateau : un groupe au-delà du seuil, les autres en deçà.
PLATEAU = (("Régie", 4), ("Lumière", GROUPE_LONG), ("Son", 6), ("Plateau", 5))


def _plateau_publie(page, live_server):
    """Un plateau RÉALISTE : plusieurs groupes dont un au-delà du seuil de coupure.

    Le défaut de réidentification d'un groupe coupé est passé inaperçu sur une première
    capture à 27 beltpacks, où aucun groupe n'atteignait le seuil. Juger une mise en page
    sur un jeu non représentatif ne prouve rien (leçon n°35).

    Le plateau est monté par l'API et non à la souris : ces tests portent sur le RENDU
    PAPIER, pas sur la saisie, et 29 créations à la souris répétées huit fois coûtaient
    plusieurs minutes sans rien vérifier de plus. Le CSRF reste actif — le jeton est lu
    dans la page comme le fait admin.js, donc on passe bien par le vrai chemin HTTP.
    """
    page.goto(live_server + "/admin/setup")
    page.fill("input[name=password]", "motdepasse8")
    page.click("button[type=submit]")
    # Écran de code de récupération : il s'intercale entre le setup et l'admin.
    page.click("a.auth-submit")
    page.wait_for_selector("#add-block-btn")

    jeton = page.get_attribute('meta[name="csrf-token"]', "content")
    entetes = {"X-CSRFToken": jeton, "Content-Type": "application/json"}

    numero = 1
    for nom, effectif in PLATEAU:
        reponse = page.request.post(f"{live_server}/api/groups",
                                    headers=entetes, data={"name": nom})
        gid = reponse.json()["id"]
        for _ in range(effectif):
            page.request.post(f"{live_server}/api/people", headers=entetes,
                              data={"beltpack": str(numero), "role": f"Poste {numero}",
                                    "group_id": gid})
            numero += 1
    assert page.request.post(f"{live_server}/api/publish", headers=entetes).ok

    page.reload()
    page.wait_for_selector("#add-block-btn")


def _feuille(page, live_server):
    feuille = page.context.new_page()
    feuille.goto(live_server + "/admin/print")
    feuille.wait_for_selector(".sheet-table")
    return feuille


def _texte_pdf(chemin):
    """`check=True` volontaire : si l'outil échoue, on veut le savoir bruyamment. Sinon
    la sortie vide ferait échouer l'assertion suivante sur un diagnostic FAUX
    (« bandeau absent » au lieu de « pdftotext a planté »)."""
    return subprocess.run(["pdftotext", str(chemin), "-"],
                          capture_output=True, text=True, check=True).stdout


def _dimensions(chemin):
    infos = subprocess.run(["pdfinfo", str(chemin)],
                           capture_output=True, text=True, check=True).stdout
    return next(ligne for ligne in infos.splitlines() if "Page size" in ligne)


@besoin_poppler
def test_la_feuille_sort_en_a3_avec_bandeau_et_numero_de_page(page, live_server, tmp_path):
    _plateau_publie(page, live_server)
    feuille = _feuille(page, live_server)

    pdf = tmp_path / "conduite.pdf"
    feuille.pdf(path=str(pdf), prefer_css_page_size=True)

    # A3 portrait = 841,92 × 1191,12 pt. C'est le `@page size` de la feuille qui décide,
    # pas le dialogue d'impression : `prefer_css_page_size` le prouve.
    assert "841.92 x 1191.12" in _dimensions(pdf)

    texte = _texte_pdf(pdf)
    assert "édité le" in texte, "bandeau d'identification absent du papier"
    assert "page 1 / 1" in texte, "numéro de page absent"
    feuille.close()


@besoin_poppler
def test_le_pied_ordinaire_ne_double_pas_le_bandeau_sur_le_papier(page, live_server, tmp_path):
    """Deux pieds disant la même chose, dont un flottant au milieu du vide : le pied
    ordinaire est masqué à l'impression, et le bandeau reprend la marque — sinon le
    co-branding disparaîtrait du papier."""
    _plateau_publie(page, live_server)
    feuille = _feuille(page, live_server)
    pdf = tmp_path / "pied.pdf"
    feuille.pdf(path=str(pdf), prefer_css_page_size=True)

    texte = _texte_pdf(pdf)
    assert "dernière modification" not in texte, "le pied ordinaire est encore imprimé"
    assert "ComRoster" in texte, "la marque doit survivre dans le bandeau"
    feuille.close()


@besoin_poppler
def test_un_groupe_coupe_se_reidentifie_en_tete_de_colonne(page, live_server, tmp_path):
    """Sans cela, la suite d'un groupe n'est qu'une liste de numéros orpheline — ce que
    le code lui-même décrit comme faisant rater une affectation. Le nom vit dans le
    `<thead>`, seul élément que le navigateur répète.

    Défaut RÉEL, trouvé en regardant le PDF : aucune assertion sur le DOM ne l'aurait vu,
    puisque le balisage était déjà correct — c'est la répétition qui manquait.
    """
    _plateau_publie(page, live_server)
    feuille = _feuille(page, live_server)
    pdf = tmp_path / "coupe.pdf"
    feuille.pdf(path=str(pdf), prefer_css_page_size=True)

    texte = _texte_pdf(pdf)
    # Le groupe long est le SEUL à dépasser le seuil : son nom doit donc apparaître deux
    # fois (en tête, puis à la reprise), là où un groupe court n'apparaît qu'une fois.
    assert texte.count("Lumière") >= 2, "le groupe coupé ne se réidentifie pas"
    assert texte.count("Régie") == 1, "un groupe court ne doit pas se répéter"
    feuille.close()


@besoin_poppler
def test_le_reglage_de_format_change_vraiment_le_papier(page, live_server, tmp_path):
    """Un réglage qui ne changerait rien au PDF serait un contrôle décoratif — c'est
    exactement le défaut des <kbd> non câblés du 2026-07-25 (leçon n°38)."""
    _plateau_publie(page, live_server)
    feuille = _feuille(page, live_server)

    feuille.select_option("#opt-format", "a4-paysage")
    pdf = tmp_path / "paysage.pdf"
    feuille.pdf(path=str(pdf), prefer_css_page_size=True)
    assert "841.92 x 594.96" in _dimensions(pdf), "A4 paysage attendu"
    feuille.close()


def test_les_reglages_sont_memorises_d_une_ouverture_a_l_autre(page, live_server):
    _plateau_publie(page, live_server)
    feuille = _feuille(page, live_server)
    feuille.click("#opt-cols button[data-valeur='1']")
    # `state="attached"` obligatoire : <html> n'a pas de géométrie propre et le `visible`
    # implicite de Playwright expirerait (leçons n°33 et n°50).
    feuille.wait_for_selector("html[data-cols='1']", state="attached")

    feuille.reload()
    feuille.wait_for_selector("html[data-cols='1']", state="attached")
    assert feuille.get_attribute("html", "data-cols") == "1"
    feuille.close()


def test_le_defaut_ne_pose_aucun_attribut(page, live_server):
    """Le défaut est l'ABSENCE d'attribut : A3 / 3 colonnes / visa vivent dans les règles
    de base de print.css. Si un attribut apparaissait au chargement, la valeur par défaut
    serait dupliquée entre le CSS et le JS — et l'une des deux dériverait (leçon n°58)."""
    _plateau_publie(page, live_server)
    feuille = _feuille(page, live_server)
    poses = feuille.evaluate(
        "() => [...document.documentElement.attributes]"
        ".map(a => a.name).filter(n => n.startsWith('data-'))")
    assert poses == [], f"attributs posés alors que tout est au défaut : {poses}"
    feuille.close()


def test_actionner_chaque_reglage_ne_produit_aucune_erreur_console(page, live_server):
    """Une violation de CSP n'apparaît QUE dans la console : le test serveur vérifie
    l'absence de `style=` dans le HTML, il ne voit pas ce que le JS fait ensuite.

    Le témoin POSITIF (`journal`) est indispensable : sans lui, `erreurs == []` passerait
    au vert même si le collecteur ne s'était jamais armé — l'assertion creuse de la
    leçon n°33.
    """
    _plateau_publie(page, live_server)
    feuille = page.context.new_page()
    erreurs, journal = [], []
    feuille.on("console", lambda m: (journal.append(m.type),
                                     erreurs.append(m.text) if m.type == "error" else None))
    feuille.on("pageerror", lambda e: erreurs.append(str(e)))
    feuille.goto(live_server + "/admin/print")
    feuille.wait_for_selector(".sheet-table")

    feuille.select_option("#opt-format", "a4-portrait")
    feuille.click("#opt-cols button[data-valeur='1']")
    for case in ("#opt-visa", "#opt-cases"):
        feuille.click(case)
    # Le dernier réglage actionné doit avoir ATTERRI avant de conclure : sans cette
    # attente, on lirait la console d'une page qui n'a pas fini d'appliquer.
    feuille.wait_for_selector("html[data-cases='oui']", state="attached")

    feuille.evaluate("console.debug('sonde')")      # prouve que le collecteur est armé
    assert journal, "collecteur console jamais armé — l'assertion suivante ne prouverait rien"
    assert erreurs == []
    feuille.close()
