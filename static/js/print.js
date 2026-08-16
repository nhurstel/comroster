/* Feuille d'affectation — câblage DOM des réglages.

   Toute la logique (allowlist, défauts, contraintes, persistance) vit dans
   printopts.js, qui est PUR et testé sous Node. Ce fichier-ci ne fait que brancher
   des contrôles dessus.

   Pas d'`onclick` inline ni d'attribut `style` : la CSP stricte l'interdit
   (leçon 2026-07-07) et un test serveur le verrouille. Les data-* passent par
   setAttribute, la règle @page par insertRule — jamais par un attribut de style.

   Pas d'impression automatique au chargement : ouvrir la feuille pour la RELIRE est
   le cas le plus fréquent, et une boîte d'impression surgissante serait une décision
   prise à la place de l'utilisateur. */
import { attributs, ecrire, lire, REGLAGES } from "./printopts.js";

const TAILLES = {
  "a3-portrait": "A3 portrait",
  "a3-paysage": "A3 landscape",
  "a4-portrait": "A4 portrait",
  "a4-paysage": "A4 landscape",
  "a5-portrait": "A5 portrait",
};

const CASES = [["monochrome", "opt-mono"]];

let opts = lire(window.localStorage);

/** Une @page ne peut pas être conditionnée par un sélecteur : la règle du format
 *  retenu est INSÉRÉE, et écrase celle de base par ordre de cascade. */
function poserFormat(format) {
  const feuille = document.styleSheets[0];
  try {
    feuille.insertRule(`@page { size: ${TAILLES[format]}; }`, feuille.cssRules.length);
  } catch {
    /* Feuille pas encore chargée ou d'une autre origine : le défaut A3 du CSS tient. */
  }
}

function appliquer() {
  const vue = { ...opts };
  const poses = attributs(vue);
  for (const def of Object.values(REGLAGES)) {
    const valeur = poses[def.attr];
    if (valeur === undefined) document.documentElement.removeAttribute(def.attr);
    else document.documentElement.setAttribute(def.attr, valeur);
  }
  poserFormat(vue.format);

  // Reflet des contrôles, y compris la contrainte : « 1 groupe/page » impose la
  // colonne unique, donc le segment Colonnes est DÉSACTIVÉ — un contrôle qui
  // resterait actif sans effet mentirait.
  document.getElementById("opt-format").value = opts.format;
  for (const btn of document.querySelectorAll("#opt-cols button")) {
    btn.setAttribute("aria-pressed", String(btn.dataset.valeur === vue.colonnes));
    btn.disabled = opts.parPage === "oui";
  }
  for (const [cle, id] of CASES) {
    document.getElementById(id).checked = opts[cle] === "oui";
  }
  ecrire(window.localStorage, opts);
}

function regler(cle, valeur) {
  opts = { ...opts, [cle]: valeur };
  appliquer();
}

document.getElementById("opt-format")
  .addEventListener("change", (e) => regler("format", e.target.value));
document.getElementById("opt-cols").addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-valeur]");
  if (btn) regler("colonnes", btn.dataset.valeur);
});
for (const [cle, id] of CASES) {
  document.getElementById(id)
    .addEventListener("change", (e) => regler(cle, e.target.checked ? "oui" : "non"));
}
document.getElementById("print-now").addEventListener("click", () => window.print());

// Couleurs de groupe : posées en CSSOM, jamais en attribut `style` (CSP).
//
// Le bandeau prend l'APLAT de la couleur du groupe (demande Nathan, 2026-08-05 : « mettre
// plus en avant les couleurs, rappeler l'interface du soft ») — c'est le langage de
// l'apparence « grille » de l'affichage, où le bloc EST la couleur.
//
// Poser du texte sur une couleur choisie par l'utilisateur n'est sûr que parce que DEUX
// garde-fous existent déjà : le nuancier des groupes est borné à 12 teintes calibrées
// (≥ 4,5:1), et `inkFor` décide de l'encre par la luminance. On réutilise cette règle,
// on ne la réécrit pas : deux implémentations finiraient par juger différemment.
const inkFor = window.ComRoster && window.ComRoster.inkFor;
document.querySelectorAll(".sheet-rule[data-color]").forEach((el) => {
  el.style.background = el.dataset.color;
  const bandeau = el.closest(".sheet-group-name") || el.closest("th");
  if (bandeau) {
    // Variable CSS, PAS un fond inline : en monochrome, la feuille doit pouvoir
    // ignorer la couleur. Un `style.background` posé ici gagnerait sur toute règle et
    // rendrait le mode impossible sans repasser par le JS.
    bandeau.style.setProperty("--gel", el.dataset.color);
    // `inkFor` rend null si la couleur n'est pas un littéral hex : la feuille garde
    // alors son encre par défaut plutôt que de parier.
    const encre = inkFor ? inkFor(el.dataset.color) : null;
    if (encre) bandeau.dataset.ink = encre;
  }
});

appliquer();
