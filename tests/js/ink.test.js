/* Encre lisible sur un aplat de couleur.

   La règle décide de la lisibilité de l'écran depuis le fond de la salle, et elle est
   partagée par l'admin et l'écran de régie — une divergence serait invisible, puisqu'on
   ne compare jamais les deux au même instant. Elle se vérifie par le CALCUL, jamais à
   l'œil sur une capture (leçon 2026-07-23). */
import { describe, expect, it } from "vitest";

import { inkFor } from "../../static/js/ink.js";

/** Contraste WCAG entre la couleur et l'encre retenue — recalculé indépendamment de
 *  l'implémentation, pour ne pas se contenter de vérifier que le code s'accorde à
 *  lui-même. */
function contrast(hex, ink) {
  const lum = (h) => {
    const c = [0, 2, 4]
      .map((i) => parseInt(h.slice(1 + i, 3 + i), 16) / 255)
      .map((v) => (v <= 0.04045 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4)));
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
  };
  const a = lum(hex);
  const b = ink === "dark" ? 0 : 1;               // encre sombre ≈ noir, claire ≈ blanc
  const [hi, lo] = a > b ? [a, b] : [b, a];
  return (hi + 0.05) / (lo + 0.05);
}

/* La palette bornée de l'admin (admin.js, GROUP_PALETTE). Recopiée volontairement :
   ce test doit échouer si quelqu'un ajoute une teinte SANS la faire passer au banc. */
const GROUP_PALETTE = [
  "#C77E6A", "#E1554C", "#9B2F2F", "#F4A259", "#E8863B", "#7A5230",
  "#E4B93C", "#C9A227", "#8FBF52", "#6B8E23", "#2E6B34", "#7FC8D6",
  "#3FA6B0", "#2A6E60", "#5C6BC0", "#4F86C6", "#2C4C8E", "#8B7CC8",
  "#6A4FA3", "#D98CB3", "#C062A6", "#8E3B6B", "#B0B7C0", "#55606E",
];

describe("inkFor", () => {
  it("choisit l'encre sombre sur clair, l'encre claire sur sombre", () => {
    expect(inkFor("#FFFFFF")).toBe("dark");
    expect(inkFor("#000000")).toBe("light");
  });

  it("accepte les formes courtes et la casse", () => {
    expect(inkFor("#fff")).toBe("dark");
    expect(inkFor("  #FFF  ")).toBe("dark");
    expect(inkFor("#ffffffff")).toBe("dark");        // avec canal alpha
  });

  it("s'abstient sur ce qui n'est pas un littéral hex", () => {
    // null = « je ne tranche pas » : la feuille de style garde alors son fond sombre.
    for (const v of ["var(--primary)", "rgb(0,0,0)", "", null, undefined, "#12345"]) {
      expect(inkFor(v), JSON.stringify(v)).toBeNull();
    }
  });
});

describe("palette bornée des groupes", () => {
  it("tient le contraste AA (4.5:1) sur les 24 teintes", () => {
    const faibles = GROUP_PALETTE
      .map((hex) => ({ hex, ratio: contrast(hex, inkFor(hex)) }))
      .filter(({ ratio }) => ratio < 4.5);
    expect(faibles, "teintes sous 4.5:1 — illisibles sur l'écran de régie").toEqual([]);
  });

  it("ne contient que des littéraux hex sur lesquels inkFor tranche", () => {
    for (const hex of GROUP_PALETTE) expect(inkFor(hex), hex).not.toBeNull();
  });
});
