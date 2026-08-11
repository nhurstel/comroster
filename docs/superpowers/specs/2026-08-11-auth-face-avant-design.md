# Pages d'authentification — la face avant assumée

**Date :** 2026-08-11
**État :** conception validée, plan d'implémentation à écrire
**Périmètre :** les cinq états des deux pages d'authentification (connexion, réinitialisation, code de récupération, configuration initiale, compte créé)

## Objectif

Donner aux pages d'authentification une composition qui occupe le cadre, une identité visible et une lisibilité en pleine lumière comme en régie — sans toucher à ce que la refonte du 2026-08-09 (`ba979b2`) a mis en place de sain : le cadre commun, la feuille autonome, le voyant qui mesure réellement.

## Constat

Relevé sur rendu à 1440×900 et lecture de `static/css/auth.css`.

**Le cadre est vide aux trois quarts.** La colonne de saisie fait 372 px (`--col`), centrée verticalement (`align-content: center`) et plaquée sur la gouttière gauche. À 1440 px de large, 1024 px restent en aplat. La composition se lit comme inachevée, alors que le bandeau et le pied, eux, tiennent leurs bords.

**Le focus porte le signal de l'erreur.** `--accent: #D96253` et `--error: #F04D3E` sont deux rouges voisins. Le champ focalisé prend `--accent` (`auth.css:171`), la boîte d'erreur prend `--error`. Comme le formulaire de connexion porte `autofocus`, **l'écran d'arrivée annonce un problème qui n'existe pas**. Le commentaire ligne 169 assume l'accent au focus ; ce qu'il n'anticipe pas, c'est que cet accent est rouge.

**La police du code n'est pas monospace.** `--f-mono: 'Inter', ui-monospace, monospace` : Inter est proportionnelle et arrive en premier. Elle rend `.auth-code`, c'est-à-dire le seul texte du produit qu'un humain recopie à la main, et dont un caractère faux ferme le boîtier définitivement. En Inter sans réglage, `0`/`O` et `1`/`l`/`I` ne se distinguent pas. La correction précédente a chassé Courier New pour l'auto-hébergement, mais l'a remplacée par une proportionnelle.

**Aucun thème clair n'existe.** `data-theme="night"` est écrit en dur dans `auth_base.html:15` — attribut mort, aucune règle de la feuille ne le lit — et la feuille n'a pas de variante claire. La page est ouverte au bureau en pleine lumière ; un aplat `#141821` plein écran y devient un miroir.

**Les cibles tactiles sont sous la barre.** Champ à 38 px, bouton à 34 px, contre 44 px recommandés. Le seul point média (`max-width: 620px`) ne fait que réduire la gouttière et la taille du code. La page est ouverte sur téléphone et tablette.

## Contraintes

- Aucune nouvelle dépendance, aucun appel CDN : le Pi tourne hors ligne.
- `auth.css` reste **autonome** — ne jamais y recharger `main.css` (c'est l'objet même de la refonte précédente).
- Tout jeton employé doit être défini dans cette feuille (`test_css_tokens`).
- Les huit fichiers e2e visent des classes existantes : **aucune classe n'est renommée**, on n'en ajoute que de nouvelles.
- Contraste minimal 4,5:1, dans les deux thèmes.
- Le mode marque cliente doit rester correct : le logo du client prend la tête, ComRoster passe en mention.

## Composition — deux flancs, aucun élément dupliqué

`body.auth` est déjà une grille. Au-delà de **900 px**, elle passe à deux colonnes et réaffecte ses trois enfants existants par `grid-template-areas` :

```
┌──────────────────────────┬─────────────────────┐
│  header.auth-top         │                     │
│  → glyphe 56 px          │   main.auth-body    │
│    COMROSTER             │   → colonne de      │
│                          │     saisie          │
│  (respiration)           │                     │
│                          │                     │
│  footer.auth-foot        │                     │
│  → voyant · état ·       │                     │
│    version · heure       │                     │
└──────────────────────────┴─────────────────────┘
```

Le voyant, l'état, la version et l'horloge **ne sont pas recopiés** : ce sont les mêmes nœuds, aux mêmes identifiants (`#auth-led`, `#auth-state`, `#auth-ver`, `#auth-clock`), déplacés par la grille. Conséquences directes :

- `static/js/auth.js` n'est pas modifié ;
- la garde script ⇄ page rendue reste verte ;
- aucun risque d'identifiant en double.

Sous 900 px, la grille reprend la forme actuelle bandeau · corps · pied. Le portrait tactile hérite donc de la mise en page d'aujourd'hui, qui lui convient déjà, et n'a rien à revalider.

Le flanc d'identité et la colonne de saisie sont séparés par un filet vertical — le vocabulaire de cette page est fait de filets et d'un champ, pas de cartes (`--rad: 3px`).

## Flanc d'identité

- Glyphe ComRoster à 56 px, coloré à l'accent corail. Le SVG est vectoriel : l'agrandissement est sans coût ni perte.
- Nom du produit en Outfit ~34 px, capitales espacées, dans la continuité du bandeau actuel.
- La plaque d'appareil (état · version · heure) occupe le bas du flanc.

**Marque cliente active.** Le logo du client est un bitmap téléversé, dimensionné aujourd'hui à 132×21 px. Son agrandissement est **plafonné à 40 px de haut** : le monter à 56 px comme le glyphe vectoriel le rendrait flou. La mention « Propulsé par ComRoster » suit, comme sur l'écran de régie et la feuille imprimée.

## Thème clair automatique

`@media (prefers-color-scheme: light)` redéfinit le jeu de jetons. Aucun réglage utilisateur : le portable de régie est déjà en sombre, le poste de bureau en clair.

L'attribut mort `data-theme="night"` est retiré de `auth_base.html`.

**Piège traité dès la conception :** les logos clients sont presque toujours des PNG blancs, dessinés pour un fond sombre. En thème clair, un tel logo deviendrait invisible. Le logo client conserve donc **toujours une plaque sombre derrière lui, dans les deux thèmes**. C'est une règle de composition, pas une correction ponctuelle.

## Focus et erreur, deux signaux distincts

Un jeton `--focus` apparaît, franchement neutre (anneau clair de 2 px), et remplace l'accent :

- dans la règle globale `:focus-visible` ;
- sur `.auth-field input:focus`.

L'erreur garde son rouge `--error`, son filet gauche de 2 px et son `!` typographique.

Le focus **n'est pas turquoise** : ce serait ressusciter la direction artistique abandonnée en juillet, celle-là même que la refonte précédente a chassée.

## Code de récupération déchiffrable

Deux voies, par ordre de préférence.

1. **Sans nouvel asset** — activer sur Inter les fonctions OpenType `zero` (zéro barré) et `ss02` (désambiguïsation `l`/`I`/`1`), le code étant déjà en capitales.
2. **Si ces fonctions ont été purgées du sous-ensemble woff2 embarqué** — embarquer une monospace sous-ensemblée aux seuls caractères utiles (majuscules, chiffres, tiret), de l'ordre de 8 Ko.

**À vérifier à l'implémentation, pas à supposer :** que les fichiers `inter-*.woff2` du dépôt aient bien conservé ces fonctions. Le choix entre les deux voies dépend de cette mesure.

Le jeton `--f-mono` garde son nom et cesse de mentir.

## Cibles tactiles

`@media (pointer: coarse)` porte champs et boutons à 46 px et épaissit la zone cliquable du lien « Mot de passe oublié ? ». C'est le **pointeur** qui décide, pas la largeur : la densité du bureau (38 px / 34 px) reste intacte sur une fenêtre étroite pilotée à la souris.

## Chaleur et mouvement

La chaleur vient de la hiérarchie typographique, aujourd'hui plate — tout tient entre 11,5 px et 21 px. Le nom du produit à ~34 px sur le flanc, le titre du formulaire inchangé à 21 px, davantage de respiration entre les blocs. L'accent corail, jusqu'ici réservé aux liens et au survol, colore le glyphe.

Une seule transition ajoutée : l'arrivée du panneau de saisie, 160 ms. Elle passe sous le `prefers-reduced-motion` déjà en place. Pas de dégradé animé, pas d'image de fond — une image détruirait le contraste mesuré à 4,92:1 et demanderait un asset de plus sur un système en lecture seule.

## Ce qui ne change pas

- `static/js/auth.js` — inchangé. C'est le signe que la restructuration est bien une affaire de mise en page.
- Les classes existantes — aucune n'est renommée ; les huit fichiers e2e continuent de viser les mêmes sélecteurs.
- Le principe du voyant : il reste une mesure de `/healthz`, jamais un ornement.

## Tests et gardes

Restent vertes sans modification : les cinq états sans `main.css`, les jetons tous définis dans la feuille, le code de récupération insécable, la garde script ⇄ page.

Trois gardes s'ajoutent, chacune verrouillant un défaut corrigé ici :

1. **Le thème clair définit exactement le même jeu de jetons que le sombre.** Un thème à moitié fait est le mode de panne le plus probable : un jeton oublié laisse une couleur sombre au milieu d'une page claire, et rien ne le signale.
2. **`--focus` et `--error` portent des valeurs différentes.** Le défaut corrigé aujourd'hui est précisément leur confusion ; sans garde, un futur ajustement de palette les rapprocherait de nouveau sans bruit.
3. **Le bloc `pointer: coarse` existe et porte une hauteur ≥ 44 px.**

`tools/captures.py` est étendu aux pages d'authentification. Le générateur existe déjà pour le README, et cette session a montré qu'une capture voit ce que 625 tests ne voient pas : le champ cerclé de rouge au repos ne fait tomber aucun test.

## Fichiers touchés

| Fichier | Nature |
|---|---|
| `templates/auth_base.html` | zones de grille, retrait de `data-theme` mort |
| `static/css/auth.css` | composition, thème clair, jeton `--focus`, tactile, typographie |
| `tests/test_auth_pages.py` | trois gardes ajoutées |
| `tools/captures.py` | captures des pages d'authentification |

`templates/login.html` et `templates/setup.html` ne sont **pas** touchés : ils ne portent que le bloc `corps`, et toute la restructuration vit dans le cadre commun et la feuille. C'est la contrepartie de la décision prise en 2026-08-09 d'écrire le cadre une seule fois — elle se paie ici en dividende.

## Réserves

- **Le contraste du thème clair doit être mesuré, pas supposé.** L'accent corail `#D96253` sur fond clair ne tiendra pas 4,5:1 tel quel et devra être assombri pour cette variante.
- **Le comportement au clavier logiciel en paysage** reste à vérifier : `body.auth` porte `overflow: hidden`, et seul `.auth-body` défile.
- Le choix de la voie pour la police du code dépend d'une mesure sur les fichiers embarqués (voir plus haut).

## Hors périmètre

L'administration, l'écran de régie et la feuille imprimée. Le thème clair introduit ici ne s'y étend pas : ces surfaces ont leur propre feuille et leur propre contexte d'usage.
