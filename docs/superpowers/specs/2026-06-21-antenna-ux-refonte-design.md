# Refonte UX de l'intégration antenne — Design

**Date :** 2026-06-21
**Statut :** validé (en attente de revue finale avant plan d'implémentation)
**Évolution de :** `2026-06-21-bolero-antenna-integration-design.md` et `2026-06-21-bolero-sync-configs-design.md` (intégration fonctionnelle déjà livrée)

## Objectif

Rendre l'intégration antenne **découvrable, claire et professionnelle**. Aujourd'hui elle
est cachée dans un dialog « ⚙ Réglages » avec un interrupteur et un éditeur de plages peu
explicite. Cible : un **point d'entrée dédié à pastille d'état**, un **assistant guidé** à la
première connexion, puis un **tableau de bord structuré**. Ton **pro et concis**, sans textes
condescendants — les libellés et la structure suffisent.

La logique fonctionnelle (connexion Basic Auth, sync miroir, plages, configs nommées) ne
change pas ; c'est une refonte de présentation + une simplification (retrait du flag).

## Décisions actées

| Sujet | Décision |
|-------|----------|
| Point d'entrée | Bouton **« 🛰 Antenne »** dans la barre, zone *données* (près de « Configs »), **toujours visible**, avec **pastille d'état** |
| États de la pastille | ● gris = non connecté · ● vert = connecté · ● orange = configuré mais hors ligne |
| Premier usage | **Assistant guidé** en 3 étapes : Connexion → Beltpacks à charger → Import |
| Ensuite | **Tableau de bord** : État / Filtre (numéros) / Actions |
| Activation | **Retrait du flag `bolero_enabled`** (et de la garde 409). Pas connecté = standalone. Plus d'interrupteur, plus de dialog « Réglages » |
| Ton | Pro, concis, sans « à quoi ça sert » |
| Conservé | Récap d'import (`import-dialog`), gestionnaire de configs (`configs-dialog`), toute la logique backend de sync/plages/configs |

## Composants UI

### Bouton + pastille (barre d'admin)
Remplace le bouton « ⚙ Réglages ». `<button id="antenna-btn">🛰 Antenne <span class="dot"></span></button>`.
La classe de `.dot` (`off` / `online` / `offline`) est posée par `refreshAntennaBadge()` à
partir de `GET /api/antenna/status` : au chargement de la page admin, puis après chaque
connexion / déconnexion / import / chargement de config.

### Panneau dédié — `dialog#antenna-dialog`
Un seul dialog qui affiche **soit l'assistant, soit le tableau de bord**, choisi à l'ouverture
selon `status` :
- `ip == null` (jamais configuré) → **assistant**.
- `ip != null` → **tableau de bord** (connecté ou hors ligne).

#### Assistant (3 étapes, indicateur `●─○─○`)
1. **Connexion** : champs *Adresse IP* + *Mot de passe*, bouton *Connecter*. Sur succès
   (`POST /api/antenna/connect`) → étape 2 ; sur échec → message d'erreur inline, on reste.
2. **Beltpacks à charger** : éditeur d'intervalles (`de [..] à [..]`, ajout/suppression),
   sauvegardés via `PUT /api/settings {antenna_ranges}`. Boutons *Retour* / *Suivant*.
3. **Import** : récap inline (`POST /api/antenna/import/preview`) — *N à ajouter / M rôles
   mis à jour / K inchangés / W à retirer* — boutons *Retour* / *Importer*
   (`POST /api/antenna/import/apply`). À la fin : ferme le dialog, recharge le tableau,
   met à jour la pastille.

#### Tableau de bord (déjà configuré)
Trois blocs :
- **État** : pastille + nom d'antenne + firmware + nombre de beltpacks (depuis `status.info`).
  À l'ouverture, `GET /api/antenna/status` tente déjà une reconnexion silencieuse (les
  identifiants sont persistés). Si hors ligne : bouton *Reconnecter* (rappelle `status`).
  Pour changer d'identifiants, *Déconnecter* (purge) ramène à l'assistant.
- **Filtre (numéros)** : éditeur d'intervalles (même composant qu'à l'étape 2), enregistré
  à la volée.
- **Actions** : *Actualiser depuis l'antenne* (→ `import-dialog`, récap puis apply) ·
  *Déconnecter* (`POST /api/antenna/disconnect`).

### Récap d'import — `import-dialog`
Conservé pour l'action *Actualiser* du tableau de bord (récap modal puis *Appliquer*).
L'étape 3 de l'assistant affiche le même contenu **inline** (pas de modal sur modal).

## Backend (simplification)

- **Retrait de `bolero_enabled`** : `services/settings` ne porte plus que `antenna_ranges`.
- `GET /api/settings` → `{ "antenna_ranges": [...] }` (sans `bolero_enabled`).
- `PUT /api/settings` → ne gère plus que `antenna_ranges` (validation inchangée, 400 si invalide).
- **Suppression de `_guard()`** et de son appel dans tous les `/api/antenna/*` : ces routes
  restent protégées par `login_required` mais ne renvoient plus 409. Le flux fonctionne dès
  qu'on est admin.
- **Factory** : `app.extensions["antenna"].load_persisted()` est appelé **inconditionnellement**
  au démarrage (plus de condition sur le flag) — recharge les identifiants s'ils existent.
- Aucun changement sur `connect/disconnect/status/import/configs/delete-batch` (hors retrait
  de la garde).

## Données / état

Le statut antenne (`{connected, ip, info}`) est la seule source pour : le choix
assistant/dashboard, la pastille, et l'affichage du bloc État. Aucune nouvelle persistance.

## Sécurité

Inchangée : endpoints `login_required` + CSRF ; mot de passe chiffré, jamais renvoyé.
Le retrait du flag n'ouvre rien de plus (les routes étaient déjà réservées à l'admin).

## Tests

- **Backend** : retirer les tests de garde flag (`test_disabled_by_default_returns_409`,
  `test_disable_disconnects`) et les `PUT /api/settings {bolero_enabled:True}` devenus inutiles
  dans les autres tests ; ajouter `GET /api/settings` → `{antenna_ranges}` sans `bolero_enabled` ;
  vérifier que `/api/antenna/status` répond 200 (plus de 409) même sans rien configurer.
- **Rendu** : le bouton `antenna-btn` et le `antenna-dialog` (assistant + dashboard) présents ;
  le bouton `settings-btn` et `settings-dialog` retirés.
- **Manuel** (faux serveur antenne) : 1ʳᵉ connexion via l'assistant (3 étapes) ; pastille qui
  passe au vert ; ré-ouverture → tableau de bord ; *Actualiser* (récap) ; *Déconnecter* →
  pastille grise ; coupe serveur → pastille orange.

## Fichiers touchés

- Modifiés : `comroster/antenna.py` (retrait `_guard`/`bolero_enabled`, `get/put settings`),
  `comroster/__init__.py` (`load_persisted` inconditionnel), `templates/admin.html`
  (bouton + dialog antenne, retrait du dialog Réglages), `static/js/admin.js` (assistant,
  dashboard, pastille, suppression de la logique d'interrupteur), `static/css/admin.css`
  (pastille, assistant, tableau de bord), `tests/test_antenna_api.py` (garde flag retirée).
- Pas de nouveau fichier.
