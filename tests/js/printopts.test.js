/* Réglages de la feuille d'impression — logique pure.

   Le point non évident que ces tests verrouillent : le DÉFAUT est l'ABSENCE
   d'attribut. `print.css` porte A3 / 3 colonnes / visa dans ses règles de base,
   chaque data-* n'étant qu'un dépassement. Une seule source pour le défaut, et
   rien à recopier entre Python et JS (leçon 2026-07-28 n°58). */
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

import { attributs, CLE_STOCKAGE, ecrire, effectif, lire, normalise, REGLAGES }
  from "../../static/js/printopts.js";

/** Faux Storage : le module ne doit dépendre que de getItem/setItem. */
function fauxStore(initial = {}) {
  const donnees = { ...initial };
  return {
    getItem: (k) => (k in donnees ? donnees[k] : null),
    setItem: (k, v) => { donnees[k] = String(v); },
  };
}

describe("normalise", () => {
  it("rend tous les réglages à leur défaut quand on ne lui donne rien", () => {
    const opts = normalise({});
    for (const [cle, def] of Object.entries(REGLAGES)) {
      expect(opts[cle]).toBe(def.defaut);
    }
  });

  it("rejette une valeur hors allowlist au lieu de la propager", () => {
    // localStorage est une donnée EXTERNE : fail-safe, jamais fail-loud (leçon n°11).
    expect(normalise({ colonnes: "12" }).colonnes).toBe(REGLAGES.colonnes.defaut);
    expect(normalise({ format: "<script>" }).format).toBe(REGLAGES.format.defaut);
    expect(normalise({ colonnes: null }).colonnes).toBe(REGLAGES.colonnes.defaut);
  });

  it("conserve une valeur légale", () => {
    expect(normalise({ colonnes: "1" }).colonnes).toBe("1");
  });
});

describe("effectif", () => {
  it("force la colonne unique quand « un groupe par page » est actif", () => {
    // Un saut de page DANS un conteneur multi-colonnes est mal supporté : plutôt que
    // de rendre un résultat imprévisible, la contrainte est explicite et testée.
    expect(effectif(normalise({ parPage: "oui", colonnes: "3" })).colonnes).toBe("1");
  });

  it("laisse les colonnes tranquilles sinon", () => {
    expect(effectif(normalise({ parPage: "non", colonnes: "3" })).colonnes).toBe("3");
  });
});

describe("attributs", () => {
  it("n'émet AUCUN attribut pour les valeurs par défaut", () => {
    expect(attributs(normalise({}))).toEqual({});
  });

  it("n'émet que les réglages qui s'écartent du défaut", () => {
    expect(attributs(normalise({ colonnes: "1" }))).toEqual({ "data-cols": "1" });
  });
});

describe("persistance", () => {
  it("relit ce qu'elle a écrit", () => {
    const store = fauxStore();
    ecrire(store, normalise({ colonnes: "2", visa: "non" }));
    const relu = lire(store);
    expect(relu.colonnes).toBe("2");
    expect(relu.visa).toBe("non");
  });

  it("retombe sur les défauts si le stockage est vide ou illisible", () => {
    expect(lire(fauxStore()).colonnes).toBe(REGLAGES.colonnes.defaut);
    expect(lire(fauxStore({ [CLE_STOCKAGE]: "{ pas du json" })).colonnes)
      .toBe(REGLAGES.colonnes.defaut);
  });
});

describe("garde structurelle", () => {
  // Réactivé en Task 4, une fois les sélecteurs écrits dans print.css.
  it.skip("chaque valeur non-défaut a un sélecteur correspondant dans print.css", () => {
    /* Sans cette garde, ajouter une valeur à l'allowlist donnerait un réglage
       cliquable SANS effet — un contrôle qui ne fait rien ment. Même famille que
       le test des jetons CSS (leçon n°62) : on vérifie l'inclusion. */
    const css = readFileSync(new URL("../../static/css/print.css", import.meta.url), "utf8");
    const manquants = [];
    for (const def of Object.values(REGLAGES)) {
      for (const valeur of def.valeurs) {
        if (valeur === def.defaut) continue;       // le défaut vit dans les règles de base
        if (!css.includes(`[${def.attr}="${valeur}"]`)) manquants.push(`${def.attr}="${valeur}"`);
      }
    }
    expect(manquants).toEqual([]);
  });
});
