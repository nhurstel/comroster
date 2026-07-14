# ComRoster — identité & DA

Référence courte. La **source de vérité** reste les CSS (`static/css/`) et les SVG (`static/img/`).

## Logo — « Voyant & fiche »
Un **voyant** (cercle = beltpack actif) au-dessus de **deux barres** (le n° et le rôle d'une fiche de roster). Géométrie sur grille `0 0 64 64`, 3 formes, aucune courbe libre.

- `static/img/comroster-glyph.svg` — glyphe seul (header du /display).
- `static/img/comroster-badge.svg` — glyphe dans un badge carré arrondi (favicon).
- `static/img/comroster-badge-mono.svg` — mono, un ton.

Le logo est **noir & blanc** : blanc `#EEF1F7` sur fond sombre ; en **mode clair** du display il est inversé (`filter: invert(1)`) pour rester visible. Do/Don't : aplat net, pas de dégradé/ombre/rotation.

## Palette
Accent unique **turquoise-signal `#33D6C6`** (bleu/vert), dépensé avec parcimonie.

| Rôle | Sombre | Clair (display) |
|---|---|---|
| Fond | `#0B0D12` | `#EDF0F5` |
| Surface | `#111420` | `#FFFFFF` |
| Texte | `#EEF1F7` | `#171B24` |
| Signal | `#33D6C6` | `#10A093` |
| Alerte | `#F04D3E` | `#D63A2B` |

Admin (registre Linear) : jetons dans `main.css :root` (fond near-black, hairlines `rgba(238,241,247,.18)`, accent turquoise). Statuts sémantiques : succès `#2ECC71`, warning `#E8A13A`.

## Typographie (self-hostée, woff2, offline-first)
- **Inter** — corps / interface.
- **Outfit** — chiffres géométriques du /display.
- Capitales + `letter-spacing` pour les titres et labels.

## Registres de DA
- **/display** : Swiss (grille, capitales, filets) + Bauhaus (pastilles carrées, barres d'accent) + une pointe de verre dépoli ; fond sombre compatible coulisses, mode clair disponible.
- **/admin** : console « Linear » — sidebar de réglages inline, deux/trois zones, lignes denses, accent unique.
- **auth** (setup/login) : carte sombre à-plat, wordmark **COMROSTER**.
