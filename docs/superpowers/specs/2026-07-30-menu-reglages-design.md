# Menu « Réglages » — regrouper ce qui concerne le boîtier

**Date :** 2026-07-30
**Demande Nathan :** « déplacer Réseau, Sauvegarde, Mot de passe, Journal et Santé dans un
nouveau menu à part ». Nom retenu : **Réglages**, en **menu déroulant**.

> ⚠️ **Révisé en cours d'implémentation.** Le contenu retenu au moment d'écrire cette spec
> était « les cinq + Redémarrer ». Nathan a tranché autrement une fois le menu à l'écran :
> « on va rebouger le bouton redémarrer à côté du "déconnexion", il y sera mieux ».
> **Redémarrer reste donc au pied de la barre latérale** et le menu compte cinq items avec
> un seul filet séparateur. Les mentions de Redémarrer aux §3, §4 et §7 ci-dessous décrivent
> l'intention initiale, pas le résultat livré ; l'état réel est consigné dans
> [tasks/todo.md](../../../tasks/todo.md), section « LOT 2026-07-30 ».

---

## 1. Constat de départ — la dispersion, pas seulement l'encombrement

Les cinq fonctions visées ne vivent pas au même endroit aujourd'hui :

| Fonction | Emplacement actuel | Nature |
|---|---|---|
| Réseau | onglet d'en-tête → dialogue | configuration du boîtier |
| Journal | onglet d'en-tête → page dédiée | consultation |
| Santé | onglet d'en-tête → page dédiée | consultation |
| Sauvegarde | barre latérale, section « Boîtier » | configuration du boîtier |
| Mot de passe | barre latérale, section « Boîtier » | configuration du boîtier |
| Redémarrer | pied de barre latérale | action machine |

La barre d'onglets mélange donc **trois registres** : panneaux d'édition (Affectations,
Écran), pages de consultation (Journal, Santé), dialogues de configuration (Intercom,
Réseau). Le regroupement corrige cette dispersion et, effet de bord bienvenu, vide la
section « Boîtier » de la latérale : celle-ci ne contient plus que du contenu de plateau.

### Réserve exprimée sur le nom, tranchée par Nathan

« Réglages » décrit mal Journal et Santé, qui ne règlent rien — on les consulte. Deux
alternatives ont été proposées et écartées : « Boîtier » (nomme l'objet plutôt que
l'action, et réutilise le vocabulaire déjà présent dans `admin.html`), et « Système »
(**déjà supprimé** lors de la revue du 2026-07-25 parce qu'il ouvrait le même dialogue que
« Réseau »). **Décision de Nathan : « Réglages ». Actée, on n'y revient pas.**

### Réserve exprimée sur l'engrenage, tranchée aussi

Tous les CONTRÔLES de l'en-tête sont textuels — le bouton « Publier » lui-même est en texte
nu (décision du 2026-07-23) ; la seule image est le glyphe de marque, qui n'est pas une
commande. Un engrenage y serait donc le seul pictogramme cliquable, et le plus
génériquement « interface de template » de tous, registre que Nathan a explicitement
rejeté (« ça fait très AI slop », 2026-07-27). **Retenu : un mot, plus un chevron `▾`
comme seul marqueur d'ouverture.**

---

## 2. En-tête cible

Six entrées deviennent quatre :

```
ComRoster   Production / Acte II

  Affectations   Écran   ● Intercom   Réglages ▾      12:04:31 · À jour · Publier ⌘↵
```

`Réglages ▾` se place **en fin de `nav.admin-tabs`**, jamais dans `.top-right` : cette zone
est l'axe « état de synchronisation + action de publication », y glisser un menu de
configuration la brouillerait.

**Intercom reste hors du menu** : il porte le voyant d'état en direct (`#antenna-dot`), et
un voyant enfermé dans un menu fermé n'informe de rien.

---

## 3. Contenu du menu

```
┌──────────────────────┐
│ Santé                │  consultation
│ Journal              │
│ ──────────────────── │
│ Réseau               │  configuration du boîtier
│ Sauvegarde           │
│ Mot de passe         │
│ ──────────────────── │
│ Redémarrer           │  action machine (registre danger)
└──────────────────────┘
```

Trois blocs séparés par des filets, dans l'ordre consultation → configuration → action
destructrice. Redémarrer conserve sa classe `nav-danger` et son `confirm()` natif (les
`confirm()` de garde sont conservés par décision du 2026-07-22 : ce sont des garde-fous
natifs robustes).

**Santé et Journal sont des liens `<a>`** — ce sont des pages (`api.health_page`,
`api.journal_page`). **Réseau, Sauvegarde, Mot de passe, Redémarrer sont des boutons** qui
ouvrent leur dialogue ou déclenchent leur action.

### Contrainte forte : les ids sont conservés

Les quatre boutons sont câblés par id dans `admin.js` :

- `#network-btn` → `openNetwork` (l. 1941)
- `#reboot-btn` → confirmation + POST reboot (l. 2014)
- `#backup-btn` → dialogue sauvegarde (l. 2147)
- `#password-btn` → dialogue mot de passe (l. 2259)

En conservant ces ids dans le menu, **aucun de ces quatre câblages ne change**. C'est ce
qui rend ce lot peu risqué côté logique : il est presque entièrement structurel.

---

## 4. Suppression des anciens accès

Règle « un accès par fonction » (leçon 2026-07-25) : déplacer sans supprimer créerait deux
accès par fonction, exactement le défaut relevé à cette revue-là.

À retirer :

- les onglets `Journal`, `Santé` et `#network-btn` de `nav.admin-tabs` ;
- la section `<nav class="side-nav">` « Boîtier » entière de la latérale (Sauvegarde, Mot
  de passe) ;
- `#reboot-btn` de `.side-foot-row`, qui ne garde plus que `Déconnexion`.

**Contrôle de sortie :** chaque fonction déplacée doit finir à exactement **un** accès —
ni zéro (fonction perdue), ni deux (doublon). Vérification par test structurel, pas à l'œil.

---

## 5. Interaction et accessibilité

**Balisage :** `<button id="settings-btn" aria-haspopup="true" aria-expanded="false"
aria-controls="settings-menu">` et `<div id="settings-menu" role="menu" hidden>`.

**Ouverture / fermeture :** clic sur le bouton bascule. Se ferme sur choix d'un item, sur
clic extérieur, et sur Échap — Échap **rend le focus au bouton**, sans quoi la navigation
clavier repart du début du document.

**Navigation clavier :** ↑ / ↓ entre les items, Entrée ou Espace active.

### Deux collisions clavier à traiter dans `admin.js` (handler global l. 1447)

1. **Échap.** L'ordre actuel est : annulation du décompte de publication (`publishTimer`)
   d'abord, puis sortie de sélection multiple. La fermeture du menu s'insère **entre les
   deux** : le décompte de publication garde la priorité (c'est l'action la plus
   conséquente à pouvoir rattraper, décision du 2026-07-27), mais un menu ouvert doit se
   fermer avant que la sélection de beltpacks ne soit abandonnée.

2. **⌘Z / ⌘A.** Le prédicat partagé `onBoard` (l. 1453) vaut aujourd'hui
   `!/INPUT|TEXTAREA|SELECT/.test(tag) && !document.querySelector("dialog[open]")`. Un menu
   ouvert doit y compter comme « pas sur le plateau ». La condition s'ajoute **dans ce seul
   prédicat**, jamais recopiée dans les branches — c'est la règle posée à la leçon
   2026-07-27 sur ⌘Z.

### Contrainte CSS

Le panneau est piloté par l'attribut `hidden`. **Aucun `display` inconditionnel** ne doit
lui être appliqué : c'est l'erreur commise deux fois (leçon 2026-06-21), où une règle
`display:flex` écrasait `hidden` et laissait l'élément visible. Le
`[hidden]{display:none!important}` du reset protège, mais on ne s'appuie pas dessus par
paresse — la règle d'affichage cible `#settings-menu:not([hidden])`.

Aucun `<style>` inline (CSP stricte, leçon 2026-07-07).

---

## 6. Portée : le menu n'existe que dans l'admin

`journal.html` et `health.html` ont un en-tête réduit dont la barre d'onglets ne contient
qu'un retour `← Affectations`. Elles ne chargent ni les quatre dialogues ni `admin.js` :
y porter le menu exigerait de dupliquer ces dialogues et leur câblage.

**Arbitrage assumé :** ces deux pages restent des culs-de-sac avec leur lien de retour,
comme aujourd'hui. Le menu vit dans `admin.html` seul.

---

## 7. Tests

### Le point de rupture connu : les e2e existants

**Sept appels e2e cliquent directement des éléments qui passeront dans un menu fermé :**

- `tests/e2e/test_e2e.py` : `#network-btn` aux lignes 442, 562, 586
- `tests/e2e/test_audit_features.py` : `#password-btn` l. 91, `#backup-btn` l. 121, 136, 162

Playwright attend `visible` par défaut : dans un menu fermé, ces sept clics échoueraient.
C'est le piège du 2026-07-26 (changer l'UI casse les tests qui l'attendent) — repéré
**avant** d'écrire la moindre ligne. Ils passent par un helper qui ouvre d'abord le menu.

### Tests à ajouter

- ouverture au clic, fermeture au choix d'un item, au clic extérieur, à Échap ;
- Échap rend bien le focus à `#settings-btn` ;
- les six items sont présents et dans l'ordre prévu ;
- **garde structurelle d'unicité d'accès** : l'en-tête ne contient plus d'onglet Journal /
  Santé / Réseau, et la latérale plus de section « Boîtier » ni de `#reboot-btn`. Cette
  garde est ce qui empêche un futur lot de réintroduire un doublon.

**Chaque nouveau test est confronté à un cas qui échoue volontairement** (leçon
2026-07-23) : sans le correctif, il doit tomber. En particulier les assertions négatives
(« plus d'onglet Réseau dans l'en-tête »), qui sont creuses si on ne les voit jamais échouer.

Attente d'un panneau `hidden` : `state="attached"` ou `state="hidden"` explicite, jamais le
`visible` implicite (leçons 2026-07-23 et 2026-07-27, la même erreur commise deux fois).

### Vérification de rendu

Capture de l'en-tête et du menu ouvert, console navigateur vide (leçon 2026-07-07 : un
changement structurel ne se valide pas par des tests DOM seuls).

---

## 8. Coût assumé

**Santé passe d'un clic à deux**, alors que c'est l'écran du contrôle d'avant-show — celui
qui répond à « puis-je lancer le show ? » (lot du 2026-07-27). C'est la seule perte réelle
du regroupement, et elle est acceptée par Nathan.

Une atténuation existe — un point d'alerte sur `Réglages ▾` quand le verdict de santé n'est
pas « Prêt » — **hors périmètre de ce lot** : elle demanderait de sonder la santé depuis
l'admin, ce qui n'existe pas aujourd'hui. Notée ici pour ne pas être réinventée.

---

## 9. Hors périmètre

- Aucun changement serveur : pas de route, pas de champ de modèle, pas de réglage persisté.
- Le contenu des quatre dialogues n'est pas retouché.
- L'onglet actif persisté (`comroster.admin.tab`) n'est pas concerné : le menu n'est pas un
  panneau, il ne participe pas à cette mémoire.
