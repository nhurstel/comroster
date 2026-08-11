# Administration — apparence jour · nuit · auto

**Date :** 2026-08-11
**État :** conception validée, plan d'implémentation à écrire
**Périmètre :** l'apparence de l'interface d'administration, et elle seule

## Objectif

Offrir à l'utilisateur de l'administration le choix de son apparence — claire, sombre, ou suivant le système — par un sélecteur à trois positions dans le pied de page, mémorisé d'une visite à l'autre.

## Constat

**L'administration n'a aucun thème clair.** Elle ne charge que `static/css/admin.css` (`admin.html:11`), découplée de `main.css` en juillet, et cette feuille de 1443 lignes ne contient pas une seule règle `data-theme="day"`. La règle présente dans `main.css:120` sert d'autres pages et n'atteint jamais l'administration. Son `<body>` porte `data-theme="night"` en dur — un attribut qu'aucune règle de sa propre feuille ne lit.

**La feuille est en revanche remarquablement tokenisée.** Mesuré : 42 jetons définis dans `:root`, **527 usages de `var(--…)`**, contre **48 couleurs écrites en dur** hors `:root` (33 distinctes, commentaires exclus). Le thème clair est donc principalement une redéfinition de jetons — et un audit borné de 33 valeurs.

**Les couleurs en dur restantes sont majoritairement des voiles.** Les plus fréquentes sont `#ffffff08` (6 fois), `rgb(0 0 0 / 0.5)` (3 fois), `#141005` (3 fois). Un voile blanc à 3 % éclaircit une surface sombre ; sur une surface claire il disparaît. Ce sont exactement les valeurs qui doivent basculer avec le thème.

**Le pied de page existe déjà** : `<footer class="admin-status">` (`admin.html:340`), avec une zone à droite (`.status-right`) disponible.

## Contraintes

- **CSP `default-src 'self'`** (`__init__.py:160`) : les scripts en ligne sont **bloqués**. L'astuce habituelle — un mini-script dans `<head>` lisant `localStorage` avant le premier rendu — est donc impossible. Affaiblir la CSP pour un sélecteur de thème est exclu.
- **CSS nu, aucun préprocesseur.**
- **Aucune nouvelle dépendance**, aucun appel CDN.
- **Tout jeton employé doit être défini dans `admin.css`** (`test_css_tokens`).
- **Français** dans les commentaires, les noms de tests et les libellés.

## Le choix et son transport

Un cookie **`comroster_theme`**, valeurs `auto` · `day` · `night`, durée un an, `SameSite=Lax`, **sans `HttpOnly`** puisque le JavaScript doit l'écrire.

La vue `admin_page` le lit, **le valide contre une liste blanche**, et passe le résultat au gabarit qui rend `data-theme`. La validation n'est pas une précaution de style : une valeur de cookie qui atterrit dans un attribut HTML sans contrôle est une injection. Toute valeur inconnue retombe sur `auto`.

**Changement de comportement à assumer.** Aujourd'hui, tout le monde voit l'administration en sombre, sans exception. Demain, `auto` étant le défaut, un poste dont le système est réglé en clair ouvrira l'administration **en clair** — pour un utilisateur qui n'a rien demandé. C'est l'intention de la fonctionnalité, mais c'est une surprise au premier lancement : elle se corrige en deux clics dans le pied, et le choix est mémorisé.

Le rendu par le serveur supprime l'éclair de thème : la page arrive déjà dans la bonne apparence. Au clic, le JavaScript écrit le cookie et change `document.body.dataset.theme` — la bascule est immédiate, sans rechargement.

## Le CSS, et sa duplication verrouillée

```
:root                                    → palette sombre (l'actuelle, inchangée)
@media (prefers-color-scheme: light)
    body[data-theme="auto"]              → palette claire   ┐ deux copies
body[data-theme="day"]                   → palette claire   ┘ identiques
body[data-theme="night"]                 → rien : c'est déjà la base
```

Aucune construction CSS ne permet de partager un bloc de déclarations entre une media query et un sélecteur. En CSS nu, la palette claire doit donc être **écrite deux fois**. C'est le coût assumé de la contrainte « pas de préprocesseur ».

Deux copies qui divergent étant le mode de panne garanti, une garde exige qu'elles soient **identiques au caractère près**. C'est cette garde qui rend la duplication tenable.

Le mode `auto` ne coûte rien : c'est du CSS pur, sans latence ni JavaScript.

## Les couleurs en dur

Les 33 valeurs distinctes hors `:root` sont auditées une à une et rangées dans l'une des deux catégories :

- **dépendante du thème** — promue en jeton, et redéfinie dans les deux blocs clairs. C'est le cas de tous les voiles (`#ffffff08`, `rgb(0 0 0 / …)`) ;
- **réellement invariante** — conservée telle quelle, avec un commentaire disant pourquoi elle ne bascule pas.

Une garde tient la **liste des littéraux tolérés**. Ajouter une couleur en dur non listée fera échouer le test, ce qui force la décision au moment de l'écriture — au lieu de laisser passer un aplat qui ne se verra que chez l'utilisateur. C'est la réponse directe à la leçon du jour : le thème clair des pages d'authentification a rendu invisible un glyphe dont la couleur était figée, sans qu'aucun des 636 tests ne bronche.

## Le sélecteur

Trois segments plats dans la zone droite du pied, à côté de la mention d'auteur. Le vocabulaire de l'administration, qui a abandonné les pilules pour des segments — pas un composant importé d'ailleurs.

- `role="group"` portant un `aria-label` explicite ;
- trois `<button>` avec `aria-pressed`, donc utilisables au clavier et correctement annoncés ;
- libellés en toutes lettres : **Auto · Clair · Sombre**. Pas de pictogramme seul : un soleil et une lune ne disent pas laquelle est active.

## Tests et gardes

1. **Les deux blocs clairs sont identiques au caractère près.**
2. **Toute couleur définie dans le `:root` sombre est redéfinie dans le bloc clair** — un jeton oublié laisserait un aplat sombre au milieu d'une page claire, sans un bruit.
3. **Un cookie hostile n'atteint jamais l'attribut** : une valeur inconnue retombe sur `auto`.
4. **La liste des littéraux de couleur tolérés hors `:root`** est close.
5. **Un e2e** bascule les trois modes et vérifie que le fond calculé change réellement, en simulant `color_scheme` pour éprouver `auto` — l'attribut seul ne prouve pas que la palette s'applique.

## Hors périmètre

- **L'écran de régie garde son réglage publié** dans Réglages → Écran. Décision prise au cadrage : un réglage local au navigateur n'a pas à modifier ce que voit la salle.
- **L'aperçu en iframe** du coin bas-droit montre `/display` et suit donc le thème **publié**, pas celui de l'administration. C'est correct — c'est un report de l'écran de régie — mais ça surprendra au premier regard. Signalé, non corrigé.
- **La feuille imprimée** et les pages d'authentification ne sont pas touchées.
