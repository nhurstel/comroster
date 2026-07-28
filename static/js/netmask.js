/* ============================================================================
   Masque de sous-réseau : préfixe CIDR ↔ écriture en octets. Logique PURE.

   Deux écritures du même masque cohabitent dans le dialogue Réseau (« /24 » et
   « 255.255.255.0 ») et doivent rester synchronisées dans les deux sens. C'est
   typiquement la conversion qu'on croit évidente et qui casse sur les cas limites —
   /0, /32, masque non contigu (255.0.255.0), et surtout les coercitions silencieuses de
   JavaScript : `Number(null)` vaut 0, donc un préfixe absent produisait « 0.0.0.0 », un
   masque parfaitement valide en apparence. Défaut trouvé par le harnais de test, pas à
   l'usage — c'est précisément ce pour quoi il existe.

   Exporté en CommonJS pour Vitest ; posé sur `window.ComRoster.Netmask` en navigateur.
   ========================================================================== */
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else {
    root.ComRoster = root.ComRoster || {};
    root.ComRoster.Netmask = api;
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  /** Un entier, ou NaN. Ne se laisse PAS convertir : `null`, `""`, `true` et `[]` valent
   *  tous 0 pour `Number()`, ce qui transformait « pas de valeur » en « préfixe 0 ». */
  function asInteger(value) {
    if (typeof value === "number") return Number.isInteger(value) ? value : NaN;
    if (typeof value === "string" && /^\s*\d{1,3}\s*$/.test(value)) return Number(value);
    return NaN;
  }

  /** Préfixe (0-32) → « 255.255.255.0 ». null si le préfixe est aberrant : rendre un
   *  masque faux serait pire que ne rien rendre — il partirait en configuration réseau. */
  function prefixToMask(prefix) {
    const p = asInteger(prefix);
    if (!Number.isInteger(p) || p < 0 || p > 32) return null;
    const octets = [0, 0, 0, 0];
    for (let i = 0; i < p; i++) octets[i >> 3] |= 1 << (7 - (i & 7));
    return octets.join(".");
  }

  /** « 255.255.255.0 » → 24. null si ce n'est pas un masque VALIDE.
   *  Un masque n'est valide que si ses bits à 1 sont CONTIGUS en tête : 255.0.255.0
   *  s'écrit comme un masque et n'en est pas un. */
  function maskToPrefix(text) {
    if (typeof text !== "string" && typeof text !== "number") return null;
    const parts = String(text).trim().split(".");
    if (parts.length !== 4) return null;
    let bits = "";
    for (const part of parts) {
      const n = asInteger(part);
      if (!Number.isInteger(n) || n < 0 || n > 255) return null;
      bits += n.toString(2).padStart(8, "0");
    }
    if (!/^1*0*$/.test(bits)) return null;                   // bits à 1 non contigus
    const firstZero = bits.indexOf("0");
    return firstZero === -1 ? 32 : firstZero;
  }

  return { prefixToMask, maskToPrefix };
});
