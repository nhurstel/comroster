/* Feuille d'affectation — le strict nécessaire.
   Pas d'`onclick` inline : la CSP stricte l'interdit (leçon 2026-07-07).
   Pas d'impression automatique au chargement non plus : ouvrir la feuille pour la
   RELIRE est le cas le plus fréquent, et une boîte d'impression surgissante serait
   une décision prise à la place de l'utilisateur. */
(() => {
  const btn = document.getElementById("print-now");
  if (btn) btn.addEventListener("click", () => window.print());

  // Filets de couleur : posés en CSSOM, jamais en attribut `style` (CSP).
  document.querySelectorAll(".sheet-rule[data-color]").forEach((el) => {
    el.style.background = el.dataset.color;
  });
})();
