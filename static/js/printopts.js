/* Réglages de la feuille d'impression — logique PURE, sans DOM.

   Séparé de print.js parce que le harnais vitest tourne en `environment: "node"` :
   sa config le dit, « le jour où un test réclamerait un DOM, c'est le signe que la
   logique visée doit d'abord en sortir ».

   UNE table décrit chaque réglage. La lecture, l'écriture, la persistance et le
   câblage la PARCOURENT : ajouter un réglage ne demande de le recopier nulle part
   (leçon 2026-07-28 n°58, où deux champs oubliés d'une énumération manuelle
   s'effaçaient en silence).

   LE DÉFAUT N'EST PAS UN ATTRIBUT : c'est son absence. Les règles de base de
   print.css valent A3 portrait / 3 colonnes ; chaque data-* est un
   DÉPASSEMENT. D'où une seule source pour le défaut, aucune duplication entre
   Python et JS, et aucun scintillement au chargement. */

export const REGLAGES = {
  format: {
    attr: "data-format",
    valeurs: ["a3-portrait", "a3-paysage", "a4-portrait", "a4-paysage", "a5-portrait"],
    defaut: "a3-portrait",
  },
  colonnes: { attr: "data-cols", valeurs: ["1", "2", "3", "4"], defaut: "3" },
  /* Monochrome : une laser N&B écrase les teintes de luminance voisine, qui
     deviennent indiscernables ENTRE ELLES. Le choix cesse d'être subi. Défaut
     « couleur » — c'est la demande d'origine (« mettre plus en avant les couleurs »). */
  monochrome: { attr: "data-mono", valeurs: ["oui", "non"], defaut: "non" },
};

export const CLE_STOCKAGE = "comroster.impression";

/** Toutes les clés présentes, toutes les valeurs légales. Une valeur inconnue
 *  retombe sur le défaut sans lever : le stockage est une donnée externe, donc
 *  fail-safe et jamais fail-loud (leçon n°11). */
export function normalise(brut) {
  const source = brut && typeof brut === "object" ? brut : {};
  const opts = {};
  for (const [cle, def] of Object.entries(REGLAGES)) {
    opts[cle] = def.valeurs.includes(source[cle]) ? source[cle] : def.defaut;
  }
  return opts;
}

/** Contraintes ENTRE réglages, appliquées après normalisation.
 *  Un saut de page à l'intérieur d'un conteneur multi-colonnes est mal supporté :
 *  « un groupe par page » impose donc la colonne unique. La barre désactive le
 *  segment Colonnes en conséquence — un contrôle qui ne ferait rien mentirait. */
/** Uniquement les réglages qui S'ÉCARTENT du défaut : le défaut est l'absence. */
export function attributs(opts) {
  const sortie = {};
  for (const [cle, def] of Object.entries(REGLAGES)) {
    if (opts[cle] !== def.defaut) sortie[def.attr] = opts[cle];
  }
  return sortie;
}

export function lire(store) {
  let brut = null;
  try {
    brut = JSON.parse(store.getItem(CLE_STOCKAGE) || "{}");
  } catch {
    brut = null;                        // stockage illisible : on repart des défauts
  }
  return normalise(brut);
}

export function ecrire(store, opts) {
  try {
    store.setItem(CLE_STOCKAGE, JSON.stringify(normalise(opts)));
  } catch {
    /* Quota plein ou stockage refusé (navigation privée) : ne pas perdre l'impression
       en cours pour un réglage non mémorisé. */
  }
}
