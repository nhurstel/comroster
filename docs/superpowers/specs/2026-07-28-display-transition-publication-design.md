# Transition d'arrivée sur `/display` à la publication

**Date :** 2026-07-28 · **Demande :** Nathan — « une petite animation sur le display quand
une nouvelle config lui est envoyée, au lieu de rafraîchir avec une coupure nette », et
« désactiver cette animation quand on active le mode performance ».

**Arbitrages validés :** cascade d'arrivée · grille **et** en-tête · ~450 ms · **les trois
apparences traitées chacune selon sa structure**.

---

## 1. Le déclencheur

L'animation se branche sur l'évènement SSE **`published`**, jamais sur `render()`.

`GET /events` ([comroster/display.py:113-128](../../../comroster/display.py)) émet
`snapshot` **une seule fois**, à l'ouverture du flux, puis `published` uniquement lors
d'une publication réelle. Or `display.js` reconnecte toutes les 4 s dès que le flux tombe :
animer sur `render()` rejouerait donc la transition à chaque hoquet réseau, en plein show.

| Appel de `render()` | Animé ? |
|---|---|
| Rendu initial (display.js:410) | non |
| `snapshot` — ouverture du flux, **et chaque reconnexion** | non |
| `published` — publication depuis l'admin | **oui** |

Mise en œuvre : `apply(eventData, { animate })`, vrai pour le seul écouteur `published`.

Aucun changement côté serveur : pas de nouveau champ, pas de nouveau réglage d'admin.

## 2. La séquence

| Phase | Durée | Ce qui se passe |
|---|---|---|
| Sortie | 160 ms | `data-anim="out"` sur `.display-grid` → `opacity: 1 → 0`. Le DOM reste en place. |
| Bascule | — | `render(json)` reconstruit la grille pendant qu'elle est invisible. |
| Arrivée | 260 ms | `data-anim="in"` ; chaque bloc porte son rang `--anim-i` → délai `calc(min(var(--anim-i), 8) * var(--anim-stagger))`. |
| Nettoyage | — | `data-anim` retiré à la fin. |

Le décalage de cascade est **plafonné à 8 rangs**. Sans ce plafond, un plateau à 20 groupes
étalerait l'arrivée sur près d'une seconde, à l'opposé du « discret » demandé.

**Bénéfice gratuit :** `render()` fait aujourd'hui `stopAutoScroll(); setOffset(0)` — si
l'écran défilait au moment de la publication, il **saute** en haut. Avec la sortie en
fondu, ce saut a lieu à opacité nulle. La coupure la plus violente disparaît sans une
ligne de plus.

## 3. Les trois apparences

Une seule mécanique (l'état `data-anim` + le rang `--anim-i`), **trois expressions**
réglées par des jetons redéfinis dans `skins.css` — exactement le procédé déjà employé
pour les bornes `--fit-*`. Une cascade uniforme serait fausse : les trois apparences ne
posent pas les groupes de la même façon.

| Apparence | Ce qui est animé | Déplacement | Raison |
|---|---|---|---|
| `basique` | le bloc entier | opacité + **6 px** vers le haut | Le groupe est une **carte posée sur un fond** (cadre, rayon, ombre) : elle arrive. |
| `lineaire` | le bloc entier | opacité seule, **0 px** | Le groupe est la **case d'un tableau réglé** (`gap: 0`, filets droite/bas fermés par la grille). Un déplacement décalerait les filets les uns par rapport aux autres : pendant 260 ms la grille cesserait d'être une grille. En fondu pur, le tableau **s'imprime case par case** — juste pour une feuille de service. |
| `grille` | l'aplat **puis** son contenu | **0 px** | Le groupe **est** la surface, en mosaïque bord à bord avec 6 px de gouttière. Un déplacement ou un `scale` ferait **fuir le fond dans les gouttières**. L'aplat monte donc vite (160 ms), le titre et les lignes suivent (260 ms), tous deux en cascade : la mosaïque se recompose, les couleurs claquent, le texte se pose. |

Jetons par apparence, déclarés dans `display.css` (valeurs de `basique`) et redéfinis sous
`body.display-page[data-skin="…"]` :

```
--anim-out      160ms    durée de la sortie (commune)
--anim-in       260ms    durée de l'arrivée
--anim-stagger   35ms    pas de la cascade
--anim-lift       6px    déplacement d'arrivée   (lineaire: 0 · grille: 0)
```

`--anim-i` est posé par le JS (CSSOM) : il doit rejoindre l'allowlist de
`tests/test_css_tokens.py`, sans quoi la garde des jetons le signalerait comme orphelin.

Chaque apparence est déclinée en thème **jour et nuit** sans règle supplémentaire :
l'animation ne porte que sur `opacity` et `transform`, jamais sur une couleur.

## 4. En-tête

Se fondent **uniquement s'ils changent** (comparaison avec le texte déjà en place avant
écriture) : `#board-title`, `#board-subtitle`, `#board-center`, `#total-groups`,
`#total-people`.

Explicitement **exclus** : `#board-clock` et `#live-indicator`. L'horloge a son rythme à la
seconde et le voyant porte déjà son propre signal « Mise à jour » pendant 2,5 s — les faire
clignoter ferait mentir les deux seuls repères permanents de l'écran.

Sur `lineaire`, l'en-tête est une barre réglée dont les filets verticaux appartiennent aux
conteneurs (`.board-meta`, `.status-badge`, `.board-clock`) : n'animer que les éléments de
**texte** laisse le réglage intact, par construction. Sur `lineaire` et `grille`,
`.stats-container` est masqué — les compteurs n'y sont donc pas concernés.

## 5. Coupure

**En JS d'abord, la CSS en second filet.**

- `data-perf="on"` → `apply()` appelle `render()` directement, exactement comme aujourd'hui.
  La garde ne peut pas être seulement en CSS : les `setTimeout` de séquencement resteraient
  armés et l'écran paierait 160 ms de latence pour une animation qui ne joue pas.
- `prefers-reduced-motion` → même chemin, via la constante `REDUCED_MOTION` déjà présente
  (display.js:30), comme le fait déjà `startAutoScroll()`. La neutralisation globale de
  `main.css:715` ramène les durées à 0,01 ms mais ne dit rien aux `setTimeout` : sans cette
  garde, l'écran resterait à opacité nulle pendant 160 ms sans rien montrer.
- Les règles CSS ne sont déclarées que sous `:not([data-perf="on"])`.
- Mode aperçu (`data-preview="on"`) : aucun SSE, donc `render()` n'est appelé qu'à l'init —
  jamais animé, rien à faire.

Effet de bord favorable : `todo.md` notait que « le mode performance devient un no-op sur
les apparences `lineaire`/`grille` » (aucune n'utilise `backdrop-filter`). Cette animation
lui **redonne un contenu sur les trois apparences**.

## 6. Publications rapprochées

Un seul handle de timer, `clearTimeout` à l'entrée. Si une transition est déjà en cours, la
nouvelle donnée **remplace** celle en attente au lieu d'empiler une seconde séquence : le
tableau affiché est toujours le dernier publié.

## 7. Invariants à ne pas casser

- **Aucun `transform` sur `.display-grid`** : c'est le canal de l'auto-scroll
  (`grid.style.transform`, display.js:283). D'où la cascade portée par les **blocs**,
  enfants de la grille, et une sortie en **opacité** seule.
- **Aucun `display:none` / `visibility:hidden`** pendant la transition : `fitDisplayText()`
  mesure `scrollWidth`/`clientWidth`, un conteneur masqué mesurerait 0 (leçons 2026-06-20
  et 2026-07-23). Opacité et `translateY` laissent les métriques de mise en page intactes.
- **Aucun `<style>` inline** (CSP stricte, leçon 2026-07-07) : tout dans `display.css` et
  `skins.css`.
- **Aucun `display` inconditionnel** sur un élément piloté par `[hidden]` — `#board-subtitle`
  et `#board-center` en sont (leçon 2026-06-21).
- `height: 100vh; overflow: hidden` de `.display-page` et `#display-scroll` : non touchés.

## 8. Vérifications

Les 27 e2e existants ouvrent `/display` **après** avoir publié : ils reçoivent un `snapshot`
et ne verront donc jamais l'animation — aucun risque de régression.

Nouveaux tests :

1. **e2e** — écran ouvert **avant** publication, apparence `basique` : après le `published`,
   la grille porte bien l'état d'animation, puis ne le porte plus.
2. **e2e** — même scénario avec `perf: true` : l'état n'apparaît **jamais**.
3. **e2e** — reconnexion (`snapshot`) : pas d'animation.
4. **test CSS** — les jetons `--anim-*` sont définis pour les trois apparences
   (`test_css_tokens.py` couvre déjà l'orphelinat ; on ajoute la présence par apparence).

Toute attente Playwright portant sur un élément à opacité nulle utilise `state="attached"` —
la leçon a été commise deux fois (2026-07-23 puis 2026-07-27).

**Chaque garde sera confrontée à un cas qui échoue volontairement** (leçon 2026-07-23) :
retirer la garde `perf` doit faire tomber le test 2 ; brancher l'animation sur `snapshot`
doit faire tomber le test 3.

Validation finale par **rendu réel** : capture des trois apparences × deux thèmes en cours
de cascade, et console navigateur vide (leçon 2026-07-07).

## 9. Réserve assumée

`opacity` et `translateY` sont composés par le GPU et devraient rester fluides sur un
Raspberry Pi 3, où le coût réel est le `backdrop-filter` de `basique`. Cela ne peut être
mesuré que sur le boîtier, pas ici. C'est précisément ce que la soupape « mode
performance » couvre.
