/* Conversions préfixe CIDR ↔ masque en octets — les deux écritures du dialogue Réseau.
   Ce sont les cas limites qui comptent : /0, /32, et surtout le masque « qui ressemble
   à un masque » sans en être un (bits à 1 non contigus). */
import { describe, expect, it } from "vitest";

import { maskToPrefix, prefixToMask } from "../../static/js/netmask.js";

describe("prefixToMask", () => {
  it("rend le masque des préfixes courants", () => {
    expect(prefixToMask(24)).toBe("255.255.255.0");
    expect(prefixToMask(16)).toBe("255.255.0.0");
    expect(prefixToMask(8)).toBe("255.0.0.0");
    expect(prefixToMask(30)).toBe("255.255.255.252");
  });

  it("tient aux deux bornes", () => {
    expect(prefixToMask(0)).toBe("0.0.0.0");
    expect(prefixToMask(32)).toBe("255.255.255.255");
  });

  it("refuse plutôt que d'inventer un masque faux", () => {
    for (const bad of [33, -1, 1.5, "abc", null, undefined, NaN]) {
      expect(prefixToMask(bad), String(bad)).toBeNull();
    }
  });
});

describe("maskToPrefix", () => {
  it("retrouve le préfixe", () => {
    expect(maskToPrefix("255.255.255.0")).toBe(24);
    expect(maskToPrefix("  255.255.0.0  ")).toBe(16);
    expect(maskToPrefix("255.255.255.255")).toBe(32);
    expect(maskToPrefix("0.0.0.0")).toBe(0);
  });

  it("rejette un masque aux bits non contigus", () => {
    // 255.0.255.0 a la FORME d'un masque et n'en est pas un : l'accepter produirait un
    // préfixe silencieusement faux, donc une config réseau injoignable.
    expect(maskToPrefix("255.0.255.0")).toBeNull();
    expect(maskToPrefix("0.255.255.255")).toBeNull();
  });

  it("rejette ce qui n'est pas quatre octets valides", () => {
    for (const bad of ["255.255.255", "255.255.255.0.1", "255.255.255.256",
                       "abc", "", "255.-1.0.0", "255.a.0.0", null, undefined]) {
      expect(maskToPrefix(bad), JSON.stringify(bad)).toBeNull();
    }
  });
});

describe("aller-retour", () => {
  it("est stable sur tous les préfixes de 0 à 32", () => {
    for (let p = 0; p <= 32; p++) expect(maskToPrefix(prefixToMask(p))).toBe(p);
  });
});
