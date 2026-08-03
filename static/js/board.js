/* ============================================================================
   Modèle du brouillon, côté navigateur — logique PURE, sans DOM.

   Deux raisons d'exister, toutes deux nées de bugs réels :

   1. LA LISTE DES CHAMPS DU BROUILLON VIT ICI, ET NULLE PART AILLEURS.
      L'import de fichier reconstruisait `state.data` en énumérant les clés à la main.
      Deux champs ajoutés après coup — `production_name` et `text_scale` — n'y avaient
      jamais été reportés : importer un fichier exporté la minute d'avant effaçait
      silencieusement le nom de la production et la taille du texte. Le même piège avait
      déjà été relevé pour `skin`. Tant qu'un humain doit « penser à » recopier un champ,
      il l'oubliera : `DRAFT_FIELDS` est donc la source unique, et un test Python la
      confronte à `model.empty_state()` pour qu'un champ ajouté au serveur ne puisse pas
      rester orphelin ici.

   2. C'EST DU CODE TESTABLE SANS NAVIGATEUR. `admin.js` faisait 2200 lignes sans un seul
      test unitaire : toute cette famille de défauts ne se découvrait qu'à l'usage.

   Chargé avant admin.js, expose `window.ComRoster.Board`. Exporté aussi en CommonJS
   pour les tests Node (Vitest) — aucune dépendance JS n'est ajoutée au RUNTIME.
   ========================================================================== */
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;   // Vitest
  else {
    root.ComRoster = root.ComRoster || {};
    root.ComRoster.Board = api;
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  /* ---------- Allowlists — miroirs de comroster/services/model.py ----------
     La divergence est gardée par tests/test_js_constants.py, qui lit CE fichier :
     une valeur ajoutée d'un seul côté fait échouer la suite au lieu de produire un
     écran nu (apparence inconnue = feuille de style inexistante). */
  const SKINS = ["basique", "lineaire", "grille"];
  const TEXT_SCALES = ["original", "grand", "tres-grand", "auto"];
  const MAX_COLUMNS = 6;
  const DEFAULT_INDICATORS = { online: true, battery: true };

  const str = (v) => (typeof v === "string" ? v : v == null ? "" : String(v));
  const isPlainObject = (v) => !!v && typeof v === "object" && !Array.isArray(v);

  const sanitizeTheme = (v) => (v === "day" ? "day" : "night");
  const sanitizeSkin = (v) => (SKINS.includes(v) ? v : "basique");
  const sanitizeTextScale = (v) => (TEXT_SCALES.includes(v) ? v : "original");

  function sanitizeColumns(v) {
    const n = parseInt(v, 10);
    if (!Number.isFinite(n) || n < 0 || n > MAX_COLUMNS) return 0;
    return n;
  }

  function sanitizeIndicators(v) {
    const src = isPlainObject(v) ? v : {};
    const out = {};
    for (const key of Object.keys(DEFAULT_INDICATORS)) {
      out[key] = src[key] === undefined ? true : !!src[key];
    }
    return out;
  }

  /* La forme du brouillon. Chaque champ porte sa propre normalisation : ajouter un champ
     au modèle serveur, c'est ajouter UNE ligne ici — et le test de cohérence le rappelle
     si on l'oublie. `version` et `updated_at` sont volontairement absents : ils
     appartiennent au serveur, qui les repose à chaque écriture. */
  const DRAFT_FIELDS = {
    title: str,
    subtitle: str,
    production_name: str,
    theme: sanitizeTheme,
    skin: sanitizeSkin,
    text_scale: sanitizeTextScale,
    indicators: sanitizeIndicators,
    perf: (v) => v === true,
    columns: sanitizeColumns,
    groups: (v) => (Array.isArray(v) ? v : []),
    people: (v) => (Array.isArray(v) ? v : []),
    beltpack_roles: (v) => (isPlainObject(v) ? v : {}),
  };

  /** Brouillon reconstruit depuis un fichier importé (.rost) ou un état partiel.
   *  Tolérant : un champ absent ou aberrant prend sa valeur par défaut, jamais une
   *  exception — le serveur revalide de toute façon via build_draft(). */
  function draftFromImport(payload) {
    const src = isPlainObject(payload) ? payload : {};
    const out = {};
    for (const key of Object.keys(DRAFT_FIELDS)) out[key] = DRAFT_FIELDS[key](src[key]);
    return out;
  }

  function emptyDraft() {
    return draftFromImport({});
  }

  /* ---------- Accords en français ----------
     « 1 groupes » trahit la machine plus sûrement qu'une faute de goût (leçon
     2026-07-28). Centralisé pour que chaque libellé généré s'accorde pareil. */
  function plural(n, singular, pluralForm) {
    return Math.abs(n) > 1 ? (pluralForm || singular + "s") : singular;
  }

  /** Libellé de l'écart brouillon ↔ publié : « +1 groupe, +2 beltpacks non publiés ».
   *  « non publié » s'accorde avec le DERNIER terme énuméré. */
  function pendingLabel(deltaGroups, deltaPeople) {
    const parts = [];
    let last = 1;
    if (deltaGroups) {
      last = Math.abs(deltaGroups);
      parts.push((deltaGroups > 0 ? "+" : "") + deltaGroups + " " + plural(deltaGroups, "groupe"));
    }
    if (deltaPeople) {
      last = Math.abs(deltaPeople);
      parts.push((deltaPeople > 0 ? "+" : "") + deltaPeople + " " + plural(deltaPeople, "beltpack"));
    }
    if (!parts.length) return "modifications non publiées";
    return parts.join(", ") + " non publié" + (last > 1 ? "s" : "");
  }

  /** Le brouillon est-il en avance sur ce qui est à l'antenne ?
   *  `unpublished` couvre la session en cours (toute édition le lève) ; la comparaison
   *  d'horodatages couvre le RECHARGEMENT de la page, où le drapeau client est retombé
   *  à faux alors que le brouillon reste en avance. Les horodatages sont en ISO 8601
   *  UTC à zéro décalage : l'ordre lexical y vaut l'ordre chronologique. */
  function isDraftAhead(draft, published, unpublished) {
    if (unpublished) return true;
    if (!published) return (draft.groups || []).length > 0 || (draft.people || []).length > 0;
    return (draft.updated_at || "") > (published.updated_at || "");
  }

  /** Identifiants balayés par un MAJ+clic, dans l'ordre VISUEL fourni.
   *  Rendue pure — l'ordre vient de l'appelant, qui seul connaît la vue active. */
  function rangeIds(orderedIds, fromId, toId) {
    let i = orderedIds.indexOf(fromId);
    let j = orderedIds.indexOf(toId);
    if (i < 0 || j < 0) return orderedIds.includes(toId) ? [toId] : [];
    if (i > j) { const t = i; i = j; j = t; }
    return orderedIds.slice(i, j + 1);
  }

  /* ---------- Ordre d'affichage des beltpacks ----------
     Deux régimes, décidés GROUPE PAR GROUPE (choix de Nathan, 2026-08-03) :

       • par défaut, TRI PAR NUMÉRO — un plateau se lit comme une liste d'appel, et
         chercher le 12 entre le 47 et le 3 est une charge que rien ne justifie ;
       • dès qu'on range un membre à la main, CE groupe passe en `manual_order` et garde
         l'ordre posé, jusqu'à ce qu'on demande « Trier par n° ».

     La règle vit ici parce qu'elle a DEUX lecteurs : l'administration et l'écran de
     régie. Elle n'en avait qu'un jusqu'ici (admin.js), et c'était un défaut silencieux —
     la salle voyait l'ordre brut du fichier pendant que le régisseur voyait un ordre trié.

     En manuel, l'ordre est celui du tableau `people` : c'est la seule donnée d'ordre qui
     existe côté serveur, et elle est déjà persistée telle quelle. Aucun champ d'ordre à
     ajouter, donc aucun à oublier dans un chemin d'écriture (leçon du 2026-07-28). */
  function parNumero(a, b) {
    const aTexte = str(a && a.beltpack).trim(), bTexte = str(b && b.beltpack).trim();
    const na = Number(aTexte), nb = Number(bTexte);
    const aNum = aTexte !== "" && Number.isFinite(na);
    const bNum = bTexte !== "" && Number.isFinite(nb);
    if (aNum && bNum) return na - nb;
    if (aNum !== bNum) return aNum ? -1 : 1;      // les numéros avant les libellés
    return aTexte.localeCompare(bTexte, "fr", { numeric: true });
  }

  function ordonnerMembres(membres, groupe) {
    const liste = Array.isArray(membres) ? membres.slice() : [];
    if (groupe && groupe.manual_order) return liste;   // l'ordre du tableau fait foi
    return liste.sort(parNumero);
  }

  return {
    SKINS, TEXT_SCALES, MAX_COLUMNS, DEFAULT_INDICATORS, DRAFT_FIELDS,
    sanitizeTheme, sanitizeSkin, sanitizeTextScale, sanitizeColumns, sanitizeIndicators,
    draftFromImport, emptyDraft,
    plural, pendingLabel, isDraftAhead, rangeIds,
    parNumero, ordonnerMembres,
  };
});
