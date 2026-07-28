/* ============================================================================
   Encre lisible sur une couleur de groupe.

   Une SEULE implémentation, partagée par l'écran de diffusion (apparence
   « grille », où le groupe est un aplat) et par l'admin (blocs en aplat depuis
   le lot « refonte admin »). Les deux posent du texte sur une couleur choisie
   librement par l'utilisateur : si les deux côtés jugeaient la lisibilité
   différemment, l'aperçu mentirait sur l'écran — et personne ne le verrait,
   puisqu'on ne compare jamais les deux au même instant.

   Règle : luminance relative sRGB (WCAG), seuil 0.179 — le point où le contraste
   sur noir et sur blanc s'équivalent. Au-dessus : encre sombre. En dessous :
   encre claire.

   Chargé avant display.js / admin.js, expose `window.ComRoster.inkFor`. Exporté aussi en
   CommonJS pour les tests Node (Vitest) : le seuil 0.179 et la bascule encre claire /
   encre sombre décident de la lisibilité en salle — ils méritent d'être vérifiés par le
   calcul plutôt qu'à l'œil sur une capture.
   ========================================================================== */
(function (global) {
  "use strict";

  const HEX_COLOR = /^#([0-9a-f]{3}|[0-9a-f]{6}|[0-9a-f]{8})$/i;

  /** @returns {"dark"|"light"|null} — null si ce n'est pas un littéral hex,
   *  auquel cas l'appelant laisse sa feuille de style décider seule. */
  function inkFor(color) {
    const m = HEX_COLOR.exec(String(color || "").trim());
    if (!m) return null;
    const hex = m[1].length === 3 ? m[1].replace(/./g, (c) => c + c) : m[1];
    const lin = [0, 2, 4]
      .map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
      .map((c) => (c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4)));
    const luminance = 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2];
    return luminance > 0.179 ? "dark" : "light";
  }

  if (typeof module === "object" && module.exports) module.exports = { inkFor };   // Vitest
  else {
    global.ComRoster = global.ComRoster || {};
    global.ComRoster.inkFor = inkFor;
  }
})(typeof globalThis !== "undefined" ? globalThis : this);
