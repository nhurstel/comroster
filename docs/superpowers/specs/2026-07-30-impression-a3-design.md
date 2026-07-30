# « Impression » — barre de réglages et refonte du format papier

**Date** : 2026-07-30
**Origine** : retour de Nathan — « Renommer "feuille imprimable" en "Impression" » et « le menu
Impression est pas très complet et le format d'impression est un peu moche ».

---

## 1. Le point de départ, mesuré

La feuille a été capturée telle qu'elle sort aujourd'hui (`/admin/print`, plateau de six
groupes et 27 beltpacks, rendu en média `print` puis en PDF A4). Trois défauts que la
lecture du CSS ne montrait pas :

1. **L'en-tête de colonne dit « NOM » et affiche le RÔLE.** Une personne, dans le modèle,
   c'est `{id, role, beltpack, group_id}` (`comroster/services/model.py`) — le champ nom
   n'existe plus. C'est la faute déjà relevée dans le README le 2026-07-23 (leçon 32),
   restée en place dans la feuille.
2. **Le pied affiche `dernière modification 2026-07-30T13:13:59Z`** : de l'ISO brut, en UTC,
   dans une interface entièrement francophone (famille de la leçon 56). La route formate
   pourtant déjà `printed_at` en français — la règle n'a pas été appliquée aux deux chemins
   d'affichage de date, corollaire de la leçon du 2026-07-06.
3. **Colonne « Visa » de 3,2 em** (~32 px) : on ne peut rien y signer. Et les deux colonnes
   s'équilibrent mal — ~100 px de vide en bas de la colonne de gauche, conséquence directe
   du `break-inside: avoid` posé sur chaque groupe.

## 2. Ce que la feuille doit être

Réponses de cadrage de Nathan :

- **Usage dominant** : le filet quand le boîtier tombe, **imprimé en A3 la plupart du temps**.
- **Le menu vit dans la barre de la page d'impression**, pas dans un dialogue de l'admin.
- **Quatre familles de réglages** : colonnes, visa/cases à cocher, format et orientation,
  contenu (non affectés, un groupe par page).
- **Direction visuelle** : « document de production » — en-tête posé, grille aérée, pied
  paginé.

Ces deux dernières réponses tirent en sens opposés : « filet si le boîtier tombe » demande de
la densité, « document de production » demande du soin. **L'A3 les réconcilie** : sa surface
permet d'être aéré *et* de tout tenir sur une feuille. C'est le principe qui tranche tous les
arbitrages qui suivent.

## 3. Ce que sait faire Chromium — mesuré, pas supposé

Trois capacités conditionnent l'architecture. Elles ont été sondées (Chromium 148, PDF réel
relu par `pdftotext`/`pdfinfo`), parce que j'allais promettre une fonction que je croyais
inconstructible :

| Capacité | Verdict | Conséquence |
|---|---|---|
| `@page { @bottom-center { content: counter(page) } }` | **OUI** — « page 1 / 2 » puis « page 2 / 2 » extraits du PDF | Le numéro de page est constructible |
| `position: fixed` répété sur chaque page | **OUI** — 2 occurrences pour 2 pages | Bandeau d'identification par page |
| `@page { size: A3 }` honoré | **OUI** — 841,92 × 1191,12 pt | Le format vient de la feuille, pas du dialogue |
| `insertRule('@page { size: A4 landscape }')` **à chaud** | **OUI** — PDF à 841,92 × 594,96 pt | La barre règle le format sans rechargement |

**Limite assumée** : les boîtes de marge sont une spécificité Chromium. Sur Firefox ou Safari,
le numéro de page disparaît en silence et le pied natif du navigateur le fournit — dégradation
acceptable, et le boîtier lui-même est en Chromium.

## 4. Le renommage

`/admin/print` **reste l'URL** : `deploy/aide-memoire-terrain.md` la diffuse sur le terrain, et
rien ne justifie de casser une adresse imprimée.

Sites du libellé, énumérés par grep avant toute modification (leçon 43) :

| Fichier | Ce qui change |
|---|---|
| `templates/admin.html` (l. 95-96) | « Feuille imprimable » → « Impression », et son `title=` |
| `templates/print.html` (l. 6) | `<title>` → « Impression · <production> » |
| `comroster/api.py` (l. 80) | docstring |
| `comroster/display.py` (l. 106) | docstring |
| `README.md` (l. 167, 218) | deux mentions |
| `deploy/aide-memoire-terrain.md` (l. 73) | ligne du tableau |
| `tests/test_css_tokens.py` (l. 28) | clé du dict `GROUPES` |

**Vérifié** : aucun test n'attend le libellé littéral (`test_audit_features.py` ne le porte que
dans un nom de fonction). Le renommage ne casse aucune suite.

## 5. Le format papier

### 5.1 Défauts

**A3 portrait, 3 colonnes.** Aujourd'hui figé à A4 / 2 colonnes.

### 5.2 En-tête

Logo client (déjà géré par le pack de marque), nom de production en grand, sous-titre, puis un
bloc de méta : édité le · source · total de beltpacks · nombre de groupes. L'en-tête cesse de
toucher le bord droit.

### 5.3 Corps

- Lignes plus hautes, filets horizontaux seuls (aucun cadre), numéro en tabulaire gras.
- **En-tête de colonne « RÔLE »**, plus « NOM » — le champ nom n'existe pas.
- **Colonne Visa élargie à ~28 mm**, et optionnelle. Case « Remis » à cocher, optionnelle.
- **Zébrure uniquement en 1 colonne.** Sur 27 cm de large l'œil dérive d'une ligne à l'autre
  et la zébrure sert ; en 3 colonnes les lignes sont courtes et elle ne coûterait que de
  l'encre. C'est un **écart assumé** au principe « aucun aplat de couleur » écrit en tête de
  `static/css/print.css` : ce commentaire est mis à jour dans le même commit, plutôt que laissé
  à contredire le code (leçons 32 et 53).
  **Ce n'est pas un réglage** : elle découle du nombre de colonnes, elle n'apparaît donc pas
  dans la barre. Une case « zébrure » de plus n'apprendrait rien à personne et donnerait le
  moyen de faire un document laid.
- **Les groupes de plus de 12 membres redeviennent coupables.** `break-inside: avoid` est ce
  qui creuse le vide de ~100 px constaté. Le serveur pose une classe sur les groupes longs ;
  eux seuls peuvent se scinder, avec `<thead>` répété. Le seuil vit **côté serveur** parce que
  le CSS ne sait pas compter des lignes.

### 5.4 Pied

- **Bandeau d'identification répété sur chaque page** (`position: fixed`) : production · édité
  le · source · marque. Une conduite qui se sépare garde son identité feuille par feuille —
  c'est tout l'objet d'un document « filet ».
- **Numéro de page** en boîte de marge CSS.
- **Date en français** : `30/07/2026 à 15:13`, formatée côté serveur comme l'est déjà
  `printed_at`, jamais en ISO brut.

**Contrainte de non-régression** : trois tests de `tests/test_branding.py` imposent que
`.sheet-foot` contienne « ComRoster », et « Propulsé par ComRoster » quand un pack est actif.
La refonte du pied doit les garder verts sans les modifier.

## 6. La barre de réglages

Une seule rangée, **tout visible**. Le reproche de départ est que le menu n'est pas complet :
replier les options dans un menu déroulant irait contre la demande.

```
← Administration │ État publié │ Imprimer le brouillon ┃ A3 portrait ▾ │ Colonnes 1 2 3 │
                                   ☑ Visa ☐ Cases │ ☑ Non affectés ☐ 1 groupe/page ┃ [Imprimer]
```

| Réglage | Valeurs | Défaut |
|---|---|---|
| Format | A3 portrait · A3 paysage · A4 portrait · A4 paysage · A5 portrait | A3 portrait |
| Colonnes | 1 · 2 · 3 | 3 |
| Visa | colonne de visa (~28 mm) | activée |
| Cases | case « Remis » à cocher | désactivée |
| Non affectés | inclure la réserve | activée |
| Un groupe par page | saut de page par groupe | désactivée |

**Deux interactions entre réglages, tranchées ici pour qu'elles ne le soient pas au hasard
pendant l'implémentation :**

- **Colonnes et format sont indépendants.** Choisir A5 ne ramène pas les colonnes à 1 :
  coupler les deux reviendrait à défaire en silence un choix explicite de l'utilisateur.
  Trois colonnes sur un A5 sont illisibles, mais c'est une décision qui lui appartient et
  qu'il voit immédiatement à l'écran.
- **« Un groupe par page » force la colonne unique.** Un saut de page à l'intérieur d'un
  conteneur multi-colonnes est mal supporté et donnerait un résultat imprévisible. Quand le
  réglage est actif, le segment « Colonnes » est donc désactivé (`disabled`) plutôt que
  silencieusement ignoré — un contrôle qui ne fait rien ment.

## 7. Architecture

Tout est client, instantané, sans rechargement — et sans attribut `style`, que la CSP interdit
et qu'un test verrouille (`assert 'style="' not in html`).

- **Chaque réglage est un `data-*` sur `<html>`**, lu par des sélecteurs d'attribut dans
  `print.css` (`[data-cols="3"] .sheet-groups { column-count: 3 }`). Aucune valeur calculée,
  aucune règle générée : le CSS contient tous les cas d'avance.
- **Le format est la seule exception** : il exige une règle `@page`, insérée en CSSOM par
  `print.js` — même précédent que les filets de couleur, déjà posés en CSSOM et jamais en
  attribut.
- **Les choix sont mémorisés** (`localStorage`). Sans persistance, Nathan re-choisirait l'A3 à
  chaque impression : ce serait reconduire exactement le reproche de départ.
- **L'état est posé par un script bloquant dans `<head>`**, sinon la feuille s'affiche en
  A4 / 2 colonnes avant de sauter en A3 / 3. Nuance de la leçon 64 : dans un script de
  `<head>`, `document.documentElement` existe déjà — c'est `document.body` qui n'existe pas
  encore. Les attributs vont donc sur `<html>`, jamais sur `<body>`.
- **Une seule table de réglages, partagée.** La liste (nom, valeurs permises, défaut) vit à un
  seul endroit dans `print.js` ; la lecture au démarrage, l'écriture au clic et la persistance
  la parcourent. Ajouter un réglage ne doit pas demander de « penser à » le recopier dans trois
  fonctions — c'est le remède structurel de la leçon 58.
- **Valeurs inconnues rejetées** : une valeur de `localStorage` hors allowlist retombe sur le
  défaut, sans lever. Le `localStorage` est une donnée externe, donc fail-safe (leçon 11).

## 8. Écarté volontairement

- **Dialogue de préréglages dans l'admin** — choix explicite de Nathan pour la barre. Et deux
  accès à la même fonction contrediraient la règle « un bouton par fonction » (leçon 37).
- **Génération PDF côté serveur** (weasyprint) : dépendance lourde sur un Pi 3 pour ce que le
  navigateur fait déjà.
- **Tri par rôle, QR code, choix de police** : personne ne les a demandés.

## 9. Vérification

| Ce qui est vérifié | Comment |
|---|---|
| Renommage complet | grep du libellé sur tout le dépôt, doc comprise |
| Colonne « RÔLE », date française | tests serveur sur le HTML rendu |
| Groupe long coupable | test serveur : la classe apparaît au-delà du seuil, pas en deçà |
| Défauts, persistance, allowlist | tests JS (vitest) sur la table de réglages |
| Réglages appliqués sans violer la CSP | e2e : cliquer chaque réglage, console vide, `style=` absent |
| Jetons CSS tous définis | `tests/test_css_tokens.py` — `print.css` est autonome, les nouveaux jetons doivent y être déclarés, sinon ils retombent en silence sur leur repli (leçon 62) |
| **Le rendu papier** | **PDF réel** : dimensions A3, nombre de pages, bandeau présent sur chaque page, numéro de page |

Le dernier point est le seul qui prouve quelque chose sur du papier. Les leçons 42 et 55 disent
la même chose autrement : un rendu ne se juge pas à l'œil sur une capture, et un ornement qui
ressemble à une échelle doit en être une — ici, un pied qui annonce « page 1 / 2 » doit être lu
dans un PDF à deux pages, pas supposé.

**Chaque assertion négative sera confrontée à un cas qui échoue volontairement** (leçons 33, 48,
64) : retirer la persistance doit faire tomber le test de mémorisation, et le contrôle « aucune
erreur console » doit être prouvé armé.
