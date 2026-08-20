/* Modèle du brouillon côté navigateur — logique pure, testée sans navigateur.

   Le test central est celui de l'import : c'est le chemin qui a perdu, en silence,
   `production_name` et `text_scale` parce qu'il énumérait ses champs à la main. */
import { describe, expect, it } from "vitest";

import Board from "../../static/js/board.js";

describe("draftFromImport", () => {
  it("conserve TOUS les champs du brouillon, pas seulement ceux du jour", () => {
    // Régression directe : l'ancienne reconstruction oubliait ces deux-là. Importer un
    // fichier exporté la minute d'avant effaçait le nom de la production et la taille
    // du texte, sans le moindre message.
    const exported = {
      title: "Affectation Intercom",
      subtitle: "Salle 2",
      production_name: "Carmen",
      theme: "day",
      skin: "grille",
      text_scale: "tres-grand",
      indicators: { online: false, battery: true },
      perf: true,
      columns: 4,
      groups: [{ id: "g1", name: "Son", color: "#3FA6B0", order: 0 }],
      people: [{ id: "p1", role: "HF", beltpack: "12", group_id: "g1" }],
      beltpack_roles: { 12: "HF" },
    };
    const draft = Board.draftFromImport(exported);
    for (const [key, value] of Object.entries(exported)) {
      expect(draft[key], `champ « ${key} » perdu à l'import`).toEqual(value);
    }
  });

  it("couvre exactement les champs déclarés — aucun oubli possible", () => {
    // Garde de structure : si quelqu'un ajoute un champ à DRAFT_FIELDS sans le
    // normaliser, ou en retire un, le brouillon reconstruit change de forme.
    expect(Object.keys(Board.draftFromImport({})).sort())
      .toEqual(Object.keys(Board.DRAFT_FIELDS).sort());
  });

  it("retombe sur des valeurs sûres quand le fichier est incomplet ou aberrant", () => {
    const d = Board.draftFromImport({ skin: "inconnue", text_scale: "gigantesque", columns: 99 });
    expect(d.skin).toBe("basique");          // sinon : feuille de style inexistante = écran nu
    expect(d.text_scale).toBe("original");
    expect(d.columns).toBe(0);               // 0 = automatique
    expect(d.groups).toEqual([]);
    expect(d.beltpack_roles).toEqual({});
  });

  it("n'accepte ni tableau ni scalaire là où un objet est attendu", () => {
    const d = Board.draftFromImport({ indicators: [1, 2], beltpack_roles: "nope", groups: {} });
    expect(d.indicators).toEqual({ online: true, battery: true });
    expect(d.beltpack_roles).toEqual({});
    expect(d.groups).toEqual([]);
  });
});

describe("sanitizeColumns", () => {
  it("borne à [0, 6] et traite tout le reste comme automatique", () => {
    expect(Board.sanitizeColumns(0)).toBe(0);
    expect(Board.sanitizeColumns(6)).toBe(6);
    expect(Board.sanitizeColumns("3")).toBe(3);      // les <select> rendent des chaînes
    expect(Board.sanitizeColumns(7)).toBe(0);
    expect(Board.sanitizeColumns(-1)).toBe(0);
    expect(Board.sanitizeColumns("abc")).toBe(0);
    expect(Board.sanitizeColumns(null)).toBe(0);
  });
});

describe("sanitizeIndicators", () => {
  it("vaut vrai par défaut mais respecte un faux explicite", () => {
    expect(Board.sanitizeIndicators(undefined)).toEqual({ online: true, battery: true });
    expect(Board.sanitizeIndicators({ online: false })).toEqual({ online: false, battery: true });
  });
});

describe("pendingLabel — accords français", () => {
  it("accorde « non publié » sur le DERNIER terme énuméré", () => {
    expect(Board.pendingLabel(1, 0)).toBe("+1 groupe non publié");
    expect(Board.pendingLabel(1, 2)).toBe("+1 groupe, +2 beltpacks non publiés");
    expect(Board.pendingLabel(0, 1)).toBe("+1 beltpack non publié");
    expect(Board.pendingLabel(3, 0)).toBe("+3 groupes non publiés");
  });

  it("n'écrit jamais « 1 groupes » — le cas le plus fréquent en début de production", () => {
    expect(Board.pendingLabel(1, 0)).not.toContain("groupes");
    expect(Board.pendingLabel(-1, 0)).not.toContain("groupes");
  });

  it("garde le signe des retraits", () => {
    expect(Board.pendingLabel(-2, 0)).toBe("-2 groupes non publiés");
  });

  it("reste explicite quand les compteurs sont identiques mais le contenu modifié", () => {
    // Renommer un groupe ne change aucun compteur : le libellé doit quand même parler.
    expect(Board.pendingLabel(0, 0)).toBe("modifications non publiées");
  });
});

describe("isDraftAhead", () => {
  const draft = (ts, g = 1, p = 1) => ({
    updated_at: ts, groups: Array(g).fill({}), people: Array(p).fill({}),
  });

  it("croit le drapeau de session même si les horodatages sont identiques", () => {
    const d = draft("2026-07-28T10:00:00Z");
    expect(Board.isDraftAhead(d, { updated_at: "2026-07-28T10:00:00Z" }, true)).toBe(true);
  });

  it("détecte l'avance après RECHARGEMENT, quand le drapeau client est retombé", () => {
    // Le cas que le drapeau seul ne couvre pas : on rouvre l'admin, rien n'a été touché
    // dans cet onglet, mais le brouillon est plus récent que ce qui est à l'antenne.
    const d = draft("2026-07-28T11:00:00Z");
    expect(Board.isDraftAhead(d, { updated_at: "2026-07-28T10:00:00Z" }, false)).toBe(true);
  });

  it("ne signale rien quand le publié est à jour", () => {
    const d = draft("2026-07-28T10:00:00Z");
    expect(Board.isDraftAhead(d, { updated_at: "2026-07-28T10:00:00Z" }, false)).toBe(false);
  });

  it("sans rien de publié, un brouillon non vide est en attente ; un vide ne l'est pas", () => {
    expect(Board.isDraftAhead(draft("x", 1, 0), null, false)).toBe(true);
    expect(Board.isDraftAhead(draft("x", 0, 0), null, false)).toBe(false);
  });
});

describe("rangeIds — balayage MAJ+clic", () => {
  const ids = ["a", "b", "c", "d", "e"];

  it("balaye dans les deux sens", () => {
    expect(Board.rangeIds(ids, "b", "d")).toEqual(["b", "c", "d"]);
    expect(Board.rangeIds(ids, "d", "b")).toEqual(["b", "c", "d"]);
  });

  it("suit l'ordre FOURNI, pas l'ordre d'origine", () => {
    // C'est tout l'enjeu du bug « ça saute » : l'ordre doit être celui de la vue active
    // (tableau trié), jamais celui d'une vue masquée restée dans le DOM.
    expect(Board.rangeIds(["e", "d", "c", "b", "a"], "d", "b")).toEqual(["d", "c", "b"]);
  });

  it("ne retient qu'un élément quand l'ancre a disparu", () => {
    expect(Board.rangeIds(ids, "inconnu", "c")).toEqual(["c"]);
  });

  it("ne rend rien quand la cible elle-même a disparu", () => {
    expect(Board.rangeIds(ids, "a", "inconnu")).toEqual([]);
  });
});

describe("ordonnerMembres — tri automatique, sauf si on a rangé à la main", () => {
  const membres = [
    { id: "c", beltpack: "10" },
    { id: "a", beltpack: "9" },
    { id: "b", beltpack: "47" },
  ];

  it("trie par NUMÉRO, pas par texte, quand le groupe n'a pas été rangé", () => {
    // « 9 » avant « 10 » : l'ordre alphabétique les inverserait, et c'est précisément ce
    // qu'on lit sur un plateau dont les numéros dépassent la dizaine.
    const ordre = Board.ordonnerMembres(membres, { manual_order: false });
    expect(ordre.map((p) => p.beltpack)).toEqual(["9", "10", "47"]);
  });

  it("respecte l'ordre posé dès que le groupe est en manuel", () => {
    const ordre = Board.ordonnerMembres(membres, { manual_order: true });
    expect(ordre.map((p) => p.id)).toEqual(["c", "a", "b"]);
  });

  it("trie aussi sans groupe (réserve) ou sans régime déclaré", () => {
    expect(Board.ordonnerMembres(membres, null).map((p) => p.beltpack))
      .toEqual(["9", "10", "47"]);
    expect(Board.ordonnerMembres(membres, {}).map((p) => p.beltpack))
      .toEqual(["9", "10", "47"]);
  });

  it("ne modifie jamais le tableau reçu", () => {
    const copie = membres.slice();
    Board.ordonnerMembres(membres, { manual_order: false });
    expect(membres).toEqual(copie);
  });

  it("range les numéros avant les libellés, et les libellés entre eux", () => {
    // Rien n'interdit un beltpack nommé « A1 » ou « HF-2 » : il ne doit pas s'intercaler
    // au hasard entre deux chiffres.
    const mixte = [{ beltpack: "HF-2" }, { beltpack: "3" }, { beltpack: "A1" }];
    expect(Board.ordonnerMembres(mixte, {}).map((p) => p.beltpack))
      .toEqual(["3", "A1", "HF-2"]);
  });
});

describe("correspond — le début d'un mot, pas n'importe où dedans", () => {
  // Le défaut signalé par Nathan le 2026-08-20 : taper « i » mettait en avant tout ce
  // qui contient un i, où qu'il soit. C'est LE cas à ne jamais laisser revenir.
  it("ne retient pas une lettre trouvée en plein milieu d'un mot", () => {
    for (const role of ["Régie", "Lumière", "Micro", "Plateau"]) {
      expect(Board.correspond(role, "i"), `« i » ne doit pas retenir « ${role} »`)
        .toBe(false);
    }
  });

  it("retient ce que la requête AMORCE", () => {
    expect(Board.correspond("Régie", "r")).toBe(true);
    expect(Board.correspond("Régie", "rég")).toBe(true);
    expect(Board.correspond("Régie", "régie")).toBe(true);
  });

  // Sans repli des accents, la règle du début casserait la recherche sur le vocabulaire
  // même du produit : « re » ne trouverait plus « Régie ». C'est la raison d'être de
  // `sansAccents`, pas un raffinement.
  it("replie les accents dans les DEUX sens", () => {
    expect(Board.correspond("Régie", "re")).toBe(true);
    expect(Board.correspond("Éclairage", "ec")).toBe(true);
    expect(Board.correspond("Regie", "ré")).toBe(true);
  });

  it("amorce n'importe quel mot, pas seulement le premier", () => {
    expect(Board.correspond("Régie son", "son")).toBe(true);
    expect(Board.correspond("Régie son", "on")).toBe(false);   // « on » n'amorce rien
  });

  it("exige que chaque mot de la requête amorce un mot, dans n'importe quel ordre", () => {
    expect(Board.correspond("Régie son", "regie son")).toBe(true);
    expect(Board.correspond("Régie son", "son regie")).toBe(true);
    expect(Board.correspond("Régie son", "regie image")).toBe(false);
  });

  it("traite les numéros par la même règle", () => {
    expect(Board.correspond("10", "1")).toBe(true);
    expect(Board.correspond("10", "0")).toBe(false);   // 0 est au milieu, pas au début
    expect(Board.correspond("21", "2")).toBe(true);
  });

  // Une requête vide est l'ABSENCE de filtre. La confondre avec « rien ne correspond »
  // viderait le plateau au premier effacement du champ.
  it("laisse tout passer quand la requête est vide ou sans lettre", () => {
    for (const vide of ["", "   ", "  -- ", null, undefined]) {
      expect(Board.correspond("Régie", vide)).toBe(true);
    }
  });

  it("ne casse pas sur un texte absent", () => {
    expect(Board.correspond(null, "r")).toBe(false);
    expect(Board.correspond(undefined, "")).toBe(true);
  });
});
