# ComRoster — Suivi

**Plan détaillé (source de vérité) :** [docs/superpowers/plans/2026-06-19-comroster.md](../docs/superpowers/plans/2026-06-19-comroster.md)

## Lot 2026-07-15 — Colonnes, auto-sync roster, voyant
Demande Nathan (3 features) :
1. **Jusqu'à 6 colonnes** sur le display + **texte homogène qui s'adapte à la taille des cases**.
   Options 5/6 dans `#meta-columns`. Feedback Nathan : taille UNIQUE sur tous les groupes, titres
   sur UNE ligne, alignés (pas décalés), jamais tronqués, et qui GROSSIT quand il y a plus de place.
   → abandon des `cqi` (dimensionnaient chaque bloc indépendamment = hétérogène). Nouvel algo JS
   `fitDisplayText()` : recherche dichotomique de la plus grande taille où le PLUS LONG titre (puis
   le plus long rôle) tient sur une ligne, appliquée à tous via `--title-fs`/`--role-fs`/`--bpn-fs`.
   Badge d'affectations ADAPTATIF (`setBadgeLabels`) : libellé complet « N affectations » par
   défaut, réduit au nombre seul UNIQUEMENT s'il dépasse 40 % de son en-tête (≈ 6 colonnes).
   Pastille beltpack : « BP » repositionné AU-DESSUS du numéro.
   (Hauteur des groupes : gardée en étirement par défaut — cases d'une même ligne alignées,
   choix Nathan après essai de `align-items: start`.) Repli anti-troncature : si même au plancher lisible (13/12px) un texte ne tient
   pas sur une ligne (nom très long en colonne étroite), retour à la ligne (`wrap-titles`/`wrap-roles`)
   — jamais coupé. Recalcul sur rendu, resize, chargement des polices et connexion antenne (batterie).
   Vérifié au rendu (3 scénarios : 3 grp auto, 6 col courts, 6 col longs → homogène, aligné, 0 troncature).
2. **Mise à jour auto du roster depuis l'antenne** (activable/désactivable, en plus du bouton
   « Actualiser »). Décision Nathan : **publie direct sur l'affichage**. Réglage `auto_sync`
   (Settings) exposé via GET/PUT /api/settings. Boucle serveur (live_poller) : si activé +
   antenne connectée, relit le roster toutes les ~10 s ; sur changement réel dans le périmètre
   des plages → `mirror_beltpacks` sur le brouillon (sous `state_lock`, appel réseau hors verrou)
   puis publication (helper `broadcast_published` partagé avec /api/publish). L'admin ouvert se
   resynchronise via SSE (`published`) quand il n'a pas d'édits locaux en attente.
3. **Voyant « Intercom Net »** : passer du rond `.dot` au **carré-signal** du header
   (même langage que « En direct » / « Brouillon synchronisé »), couleurs sémantiques conservées.

## Lot 2026-07-21 — Redémarrage, réseau à chaud, passe de revue
**Bug corrigé :** le bouton « Redémarrer » ne faisait rien, silencieusement (Popen sans
lecture du code retour + droit sudo absent des boîtiers installés avant le 2026-07-15).
Voir [lessons.md](lessons.md). Désormais l'échec remonte à l'écran.

**Nouveau :** « Appliquer maintenant » (POST `/api/network/apply`) rejoue
`comroster-network.service` → nmcli reconfigure **à chaud**, sans redémarrer ni couper
l'affichage. Le redémarrage devient un filet de secours, migré dans la barre latérale
(section « Boîtier »).

**Passe de revue du projet (2026-07-21) — corrigé :**
- [x] `uninstall-pi.sh` ne supprimait pas `/etc/sudoers.d/comroster-reboot` → privilège
      root orphelin après désinstallation.
- [x] `apply-network.sh` : en-tête « jamais depuis le web » devenu faux.
- [x] `deploy/comroster.service` + `nginx.conf` : balisés **modèles de référence** (non
      déployés ; l'unit réel est généré par `setup-pi.sh`). Piège documenté :
      `NoNewPrivileges=true` casse sudo, donc les boutons Redémarrer / Appliquer.
- [x] `kiosk.md` : le lien laissait croire que le modèle était l'unit réel.
- [x] Lint : 7 erreurs ruff résiduelles (E702/F401/E402) → **0**. Note : la CI ne lint que
      `comroster app.py`, ces erreurs étaient donc invisibles en CI.
- [x] Vérifié sains : aucun TODO/FIXME, aucune dérive de vocabulaire dans les fichiers
      suivis, `.gitignore` correct (archives 191 Mo bien exclues, 0 fichier parasite suivi).

## Lot 2026-07-22 — Revue exhaustive du code (tout le projet lu)
Passe de relecture complète (backend + services + front JS + templates + scripts).
Verdict : très bon niveau, aucun bug critique. Corrigés :
- **Mdp min front/back incohérent** : le front annonçait/imposait 8 caractères, le back en
  accepte 4 (décision actée). Front aligné sur 4 (setup.html, login.html). Cf. leçon 2026-07-06.
- **`merge_beltpacks` = code mort** (0 usage, remplacé par `mirror_beltpacks`) → supprimé
  avec son test.
- **Concurrence antenne** : l'état de `AntennaClient` (ip/password/connected/cache) était
  partagé entre le thread poller et les requêtes HTTP sans verrou. Ajout d'un `RLock` ;
  les appels réseau de `live_status` restent HORS verrou (+ re-check `_connected` après le
  réseau → plus de cache repeuplé après une déconnexion).
- **Mineurs** : collision de slug configs (écrasement silencieux → 409 explicite) ;
  passerelle IPv6 + adresse IPv4 (TypeError→500 → 400 propre) ; `delete-batch` valide que
  `ids` est une liste ; `viewer_agent` préfixe non entier → 400 ; garde sur le meta CSRF
  (admin.js) ; **admin.js migré du polling `/api/antenna/live` 5 s vers le push SSE `live`**
  (l'admin était abonné mais ignorait l'évènement) ; `assign()` simplifiée ; garde `grid` null.
- **Non fait (choix)** : 143 couleurs hex en dur dans admin.css → refactor vers tokens à
  fort risque de régression visuelle pour un gain nul (admin mono-thème). À traiter à part
  avec validation par screenshots si un jour un thème clair admin est voulu.

## Lot 2026-07-22 (suite) — Approfondissement revue (CSS + scripts ligne à ligne)
- **admin.css → design tokens** : couleurs sémantiques mappées aux tokens globaux
  (fg/fg-muted/fg-subtle/bg/success/warning) + 13 tokens de surface `--a-*` pour les
  gris récurrents. Pur renommage (valeurs préservées), **validé au screenshot**.
- **UI cohérente** : les 8 `alert()` → `toast()` ; le `prompt()` de renommage de groupe →
  dialog custom (réutilise le dialog de groupe). Les `confirm()` de suppression sont
  **conservés** (gardes de sécurité natives, robustes — pas de risque à convertir).
- **viewer_pages.py** : échappement HTML défensif (`html.escape`) des valeurs réinjectées.
- **BUG CORRIGÉ (important)** : `setup-pi.sh` générait l'unit `comroster.service` avec
  `NoNewPrivileges=true` → **cassait les boutons Redémarrer / Appliquer** (sudo bloqué),
  malgré le fix précédent. Retiré. Modèle `deploy/comroster.service` aligné. Cf. lessons.
- **CSS mort supprimé** : `auth.css` (`.auth-logo`, `.password-strength*`, `.btn-group`) ;
  `main.css` (`.btn-secondary` + tokens `--secondary`/`--accent`, `.badge` défini 2×).
- **Non touché (assumé)** : `will-change` global de main.css (perf Pi discutable mais non
  mesurable ici) ; quelques couleurs d'état en dur dans display.css (DA distincte).

## Lot 2026-07-22 (suite) — Apparences du display (`skin`) — PLAN, À VALIDER

**Origine :** retour extérieur « ça fait projet fait par l'IA ». Diagnostic : le fond est sain,
c'est la DA de `/display` qui trahit (auréoles turquoise en `radial-gradient`, verre dépoli +
reflet `inset 0 1px 0`, accent teal `#33D6C6`, 13 niveaux de capitales tracées, tuiles de stats
dans le header, échelle `--gray-*` Tailwind morte, Inter+Outfit). Maquettes hors dépôt validées
par Nathan → **2 apparences en plus de l'actuelle : B et F** (C, D, E, G, H écartés).
Décision revue en cours de lot : d'abord B/E/F/H, puis resserré à A+B+F avant d'écrire la moindre
feuille de style — donc aucun travail jeté. Rejoint la réserve émise au plan (3 valeurs, pas 6) :
moins de dette CSS, et moins de façons de se tromper d'apparence avant un show.

**Décision d'architecture :** un seul champ `skin`, orthogonal à `theme`. Chaque apparence porte
sa STRUCTURE une seule fois + DEUX jeux de jetons de couleur (nuit/jour). On ne crée pas un axe
`apparence × luminosité` à 10 combinaisons à dessiner : `theme` reste le commutateur de luminosité
et garde sa sémantique actuelle.

| Valeur | Nom UI | Réf. | Luminosité |
|---|---|---|---|
| `basique` | Basique | l'existant, **défaut** | jour + nuit |
| `lineaire` | Linéaire | Swiss, filets, Helvetica | jour + nuit |
| `grille` | Grille | Bauhaus/De Stijl, le groupe = une surface | jour + nuit |

**Constat à acter :** `/display` n'affiche PAS le nom des personnes
(`createPersonCard` display.js:66-71 ne pose que le rôle ; `.person .name` est un sélecteur mort
dans display.css). Les apparences seront donc plus aérées que les maquettes.

### Chemins d'écriture de `skin` (leçon 2026-07-06 : TOUS les chemins)
- [x] `model.empty_state()` → `"skin": "base"`
- [x] `model.build_draft()` → `state["skin"] = sanitize_skin(...)`
- [x] `model.sanitize_skin()` : allowlist, toute valeur inconnue → `"base"`
- [x] `admin.js` reconstruction à l'import → `skin: SKINS.includes(...)` ⚠️ sinon perdu
- [x] `admin.js` `syncSettingsInputs` + `bindSettings` (calqué sur `theme-select`)

### Étapes (chacune mergeable seule)
- [x] **1. Mécanisme seul** — `skin` de bout en bout, seule valeur `basique`. `data-skin` sur `<body>`
      (display.html) + `bodyEl.dataset.skin` dans `render()` à côté de la l.85. `<select>` Apparence
      dans le panneau Réglages écran. **Aucun changement visuel.** Tests unitaires du sanitize.
- [x] **2. Deux points de blocage JS** (toujours aucun changement visuel sur `basique`) :
      - `fitDisplayText()` : bornes 13/24 et 12/19 **en dur** (display.js:180-181) → lues depuis des
        variables CSS (`--fit-title-min/max`, `--fit-role-min/max`), défauts = valeurs actuelles.
        ⚠️ Contrat négocié avec Nathan au lot 2026-07-15 (taille unique, une ligne, alignée, jamais
        tronquée, qui grossit) — à préserver à l'identique.
      - `--block-ink` : luminance relative sRGB de `group.color` → encre noire ou blanche, posée à
        côté du `--block-accent` existant (l.111). Requis par `grille`, inerte ailleurs.
- [x] **3.** Apparence `lineaire` → `static/css/skins.css` (~230 l.), chargée en permanence.
      Tableau réglé : `gap: 0` + filet droit/bas sur chaque case, fermé en haut/à gauche par la
      grille (pas de double trait, pas de cellule vide colorée). Bandeau de groupe = seul aplat de
      couleur et seul niveau de capitales ; numéro sorti de sa pastille, aligné sur les unités.
      Plafonds d'ajustement relevés (rôles 26 px contre 19) : sans cadre ni pastille, il reste de la place.
      **Trouvé au rendu** : `main.css` pose un voile radial turquoise (`body::before`) qui traverse
      tout — neutralisé pour toute apparence ≠ `basique` via `:not([data-skin="basique"])::before`.
      Idem la pilule arrondie + le halo animé de `.status-badge` (main.css), remplacés par un
      carré-signal et un clignotement d'opacité.
- [x] **4.** Apparence `grille` : mosaïque pleine bord à bord, gouttières de 6 px, blocs en
      `1fr` + `min-height: 100%` (remplit l'écran quand tout tient, grandit et laisse l'auto-scroll
      reprendre au-delà). Le bloc EST la couleur du groupe → `data-ink` sert enfin.
      Deux arbitrages notés : le voyant temps réel passe par l'encre (pleine/effacée) au lieu du
      vert, qui jurerait avec la teinte ; la batterie faible s'affiche en encre inversée plutôt
      qu'en ambre, invisible sur un groupe ambre.
      Factorisation : ce que TOUTE alternative neutralise (voile `body::before`, pilule + halo du
      badge live, pastille `BP`, tuiles de stats) est regroupé sous `:not([data-skin="basique"])`.
      Branche encre claire vérifiée séparément sur 4 couleurs (marine/crème/rouge/bleu) : bascule
      correcte dans les deux sens.
- [x] **5.** Aperçu dans l'admin (demande Nathan) : item « Aperçu » → dialog avec iframe sur
      `GET /admin/preview`, qui rend `display.html` avec le **brouillon** et `data-preview="on"`.
      Le JS y coupe SSE / sondages / anti-veille / auto-scroll — sans quoi un aperçu laissé ouvert
      brûlerait un créneau `SSE_MAX_CLIENTS` et un thread en permanence (leçon 2026-07-06).
      Iframe rendue à 1280×720 puis mise à l'échelle : rendu fidèle, pas une page rétrécie.
      Le clic vide d'abord les édits en attente (`savePending`) — l'aperçu lit le brouillon SERVEUR.
      Vérifié : `X-Frame-Options: SAMEORIGIN` + `frame-ancestors 'self'` autorisent l'iframe même
      origine sans toucher à la CSP.
- [x] **6.** Passe de doc — README : section « Apparences de l'écran », route `/admin/preview`,
      pile technique. **Deux périmés corrigés au passage** : le mot de passe annoncé à 8 caractères
      (le code impose 4 depuis le 2026-07-06) et « ajouter les personnes (nom + …) » alors que le
      champ nom n'existe plus ni dans l'admin ni dans le modèle.
- [ ] **7.** Reste : captures dans la doc si souhaité ; cahier des charges (D1) non retouché.

**Étapes 1 et 2 vérifiées :** 254 tests unitaires + 10 e2e verts, ruff propre. 3 e2e ajoutés
(bornes historiques d'ajustement respectées + 0 troncature sur `basique` ; `data-ink` calculé ;
**console navigateur sans erreur** — collecteur `console`/`pageerror` branché avant le chargement,
et vérifié non creux sur une page qui échoue volontairement).

✅ **Environnement — réparé le 2026-07-26.** Le déplacement du projet dans `INTERCOM/` avait laissé
l'ancien chemin (`/Users/nathan/Desktop/CODA/COMROSTER/…`) figé à deux endroits, un venv n'étant pas
déplaçable : (1) `activate` + `pyvenv.cfg` → `source .venv/bin/activate` préfixait au PATH un dossier
inexistant, d'où `./run-dev.sh: exec: python: not found` alors que le prompt affichait bien `(.venv)` ;
(2) le shebang des 14 scripts console (`pytest`, `pip`, `gunicorn`, `flask`, `playwright`…) → `bad
interpreter`. Réparation : `python3.12 -m venv .venv` (réécrit les scripts, préserve site-packages)
**puis** réécriture des shebangs — `venv --upgrade` seul ne les touche pas, c'est le piège.

### Contraintes à respecter (issues des leçons)
- [ ] `[hidden]` : ne poser AUCUN `display` inconditionnel sur `#board-subtitle`, `#onboarding`,
      `.bp-batt` (leçon 2026-06-21 — le `[hidden]{display:none!important}` de main.css:156 protège,
      mais on ne s'appuie pas dessus par paresse)
- [ ] Ne pas casser `height:100vh; overflow:hidden` sur `.display-page` ni `#display-scroll`
      (leçon 2026-06-20 — sinon l'auto-scroll meurt silencieusement)
- [ ] CSP stricte : aucun `<style>` inline, feuilles servies depuis `self` (leçon 2026-07-07)
- [ ] **Toutes les feuilles d'apparence chargées d'avance** : le `skin` change en direct par SSE
      `published` sans rechargement de page → un `<link>` conditionnel côté serveur ne marcherait pas
- [ ] Validation par **rendu réel** (screenshot + console navigateur), pas par tests DOM
      (leçon 2026-07-07)

### Risques assumés / à trancher
- **Dette de maintenance** : ~+600 lignes de CSS ; toute évolution future du display devra être
  restylée 5 fois. C'est le vrai coût, pas l'implémentation.
- **`grille` impose de contraindre le nuancier des groupes** : poser du texte sur la couleur saisie
  par l'utilisateur exige un contraste minimal. `--block-ink` gère noir/blanc, mais une couleur très
  saturée restera mauvaise → travail produit (borner le sélecteur de couleur), pas seulement du CSS.
- **`grille` en mosaïque pleine** n'a de sens que si tout tient sans défilement ; au-delà il faut
  qu'il dégrade proprement en blocs normaux (`grid-auto-rows: minmax(min-content, 1fr)`).
- **Mode performance** devient un no-op sur les 4 nouvelles apparences (aucune n'utilise
  `backdrop-filter`) — bénéfice net pour le Pi 3, mais la case reste utile pour `basique`.
- **Onboarding** (`#onboarding`) non décliné par apparence : il ne s'affiche que sur une box non
  configurée, donc toujours en `basique`. À confirmer.
- **5 choix dans l'admin** = 5 façons de se tromper avant un show. Alternative écartée par Nathan :
  n'en garder que 2 ou 3.

## Décisions techniques actées
- Python 3.12, Flask
- CSRF : Flask-WTF · Rate-limit login : Flask-Limiter
- Persistance : JSON plats + écriture atomique sous lock · IDs UUID4
- SSE broker mémoire → **1 seul worker gunicorn** en prod
- **Mot de passe admin : 4 caractères minimum** (setup ET recover) — décision 2026-07-06
- **Plages beltpack = périmètre du miroir** : un beltpack hors plage n'est jamais retiré par l'import antenne

## État des phases — TERMINÉ
- [x] P0 → P8 (voir historique git)

## Durcissement post-revue (2026-07-06) — TERMINÉ (191 tests unitaires + 8 e2e verts)
Correctifs approuvés par Nathan :
- [x] 1. Mdp min 4 caractères sur setup + recover (recover acceptait un mdp vide)
- [x] 2. ProxyFix opt-in (`COMROSTER_BEHIND_PROXY`) — rate-limit voyait 127.0.0.1 derrière nginx
- [x] 3. MAX_CONTENT_LENGTH 1 Mo → 413 (DoS mémoire en Pi autonome)
- [x] 4. Cap connexions SSE (`COMROSTER_SSE_MAX`, défaut 12) + gunicorn threads 8→16
- [x] 5. Lock global read-modify-write (`exclusive_state` / `state_lock`) sur toutes les mutations
- [x] 6. Suppression du `except Exception: return "DISPLAY OK"` de display_page
- [x] 7. Setup premier boot : INCHANGÉ (décision Nathan)

Carte blanche — réalisé :
- [x] Validation IP antenne (littéral ipaddress uniquement, anti-SSRF)
- [x] Session admin : expiration 12 h (`PERMANENT_SESSION_LIFETIME`)
- [x] 400 (pas 500) sur payloads JSON invalides/incomplets (`json_body()`)
- [x] Miroir antenne borné aux plages (préview + apply cohérents)
- [x] Slug configs : translittération des accents (Éclairage → eclairage)
- [x] _valid_ranges : rejet des booléens
- [x] CSP stricte `default-src 'self'` (initial_data → `<script type="application/json">`,
      onclick logout → addEventListener) + HSTS nginx
- [x] apply-network.sh : revalidation des IP en root (défense en profondeur)
- [x] setup-pi.sh : avertissement explicite sur COMROSTER_INSECURE_COOKIE

## Vérifié en réel
- Smoke test serveur : CSP présente, bloc initial-data OK, aucun script inline, body 2 Mo → 413.
- 8 tests e2e Playwright verts (vrai navigateur) après le passage CSP/initial-data.

## Réseau Filaire/Wi-Fi (2026-07-06) — TERMINÉ côté code, À VALIDER SUR PI
Spec validée : [docs/superpowers/specs/2026-07-06-network-wifi-ethernet-design.md](../docs/superpowers/specs/2026-07-06-network-wifi-ethernet-design.md)
- [x] netconfig : schéma `link` ethernet/wifi, validation SSID/PSK, rétro-compat, psk conservé si omis
- [x] API : psk write-only (`psk_set` en lecture, jamais dans les réponses)
- [x] UI admin : sélecteur Liaison, champs SSID/mdp, option link-local masquée en Wi-Fi, DHCP ajouté
- [x] apply-network.sh : branche wifi (connexion `comroster-wifi`, radio off en filaire,
      RJ45 port de service link-local en Wi-Fi), revalidation root SSID/PSK/IP
- [x] Doc raspberry-pi.md : section Filaire/Wi-Fi + procédure port de service
- [x] **Validé sur vrai Pi (2026-07-22)** : branche nmcli wifi OK — association AP,
      bascule radio Wi-Fi on/off, port de service RJ45 (câble direct), IP statique et DHCP.

## Non traité (choix assumés)
- ~~`venv/` (Python 3.14, 44 Mo) coexiste avec `.venv/`~~ → **supprimé le 2026-07-21**
  (aucune référence dans le dépôt ; `.venv/` en 3.12 reste le seul environnement utilisé).
- `beltpack_roles` jamais purgé (croissance négligeable).
- Compteurs rate-limit en mémoire (reset au restart) : acceptable appliance mono-process.

---

# LOT « REFONTE ADMIN » — plan (2026-07-23)

Base : maquette 7 du scratchpad, valeurs retenues par Nathan (reportées en A1).
Principe : chaque phase est livrable seule, tests verts, sans casser la précédente.

## A. Jetons et typographie — CSS seul, risque nul  ✅ FAIT (d18be95)

- [x] A1. Poser les jetons retenus en tête de `.admin-page` :
      `--ui:12.5px` `--track:.02em` `--mono:15px` `--role:15px` `--role-w:600`
      `--row:31px` `--pad:12px` `--gap:7px` `--rad:7px` `--card-min:300px`
      `--side-w:204px` `--pool-w:242px` `--top-h:53px`
      Police = **Base** (Outfit + Inter) → rien à auto-héberger, les .woff2 sont déjà là.
- [x] A2. Règle typographique : capitales réservées aux TITRES (nom de groupe,
      en-têtes de section). Tout ce qui se clique passe en bas-de-casse 12,5 px,
      interlettrage .02em. C'est le défaut signalé par Nathan (illisibilité des
      boutons en 10 px capitales très espacées).
- [x] A3. Purger les tailles en dur (`0.82rem`, `0.66rem`…) au profit des jetons.

## B. Blocs-groupes en aplat plein — CSS + un peu de JS  ✅ FAIT (9398bd8)

- [x] B1. Extraire `inkFor()` de `display.js` vers `static/js/ink.js`, chargé par
      display.html ET admin.html. NE PAS dupliquer : c'est la même règle de
      luminance (seuil .179) des deux côtés, une divergence serait invisible.
- [x] B2. `renderBlocks()` pose `--gel` (couleur du groupe) et `data-ink` sur le
      bloc ; le CSS en déduit l'encre. Séparateurs = filets, trait d'union `·`
      entre n° et rôle (miroir de `skins.css`, cf. `--tie`).
- [x] B3. Voyants d'état : point, masqué au survol au profit des actions.

## C. Mise en page — template + CSS  ✅ FAIT (C1 972808e · C2 085ea4d · C3 fd371c5)

- [x] C1. « Beltpacks disponibles » quitte `.admin-layout` et devient une colonne
      de droite (`--pool-w:242px`). Le plan de travail devient une grille
      `repeat(auto-fill, minmax(300px, 1fr))`, gap 7.
- [x] C2. En-tête à 53 px : fil d'Ariane + onglets nommés + horloge + état + action.
- [x] C3. Barre latérale → INVENTAIRE : groupes avec effectif, puis vues
      (« Hors ligne », « Batterie < 30 % »), puis Données. Les réglages d'écran
      partent dans l'onglet « Écran ». ⚠️ Garder les MÊMES ids d'inputs
      (`#skin-select`, `#theme-select`, `#meta-columns`…) : `bindSettings` et
      `syncSettingsInputs` continuent de fonctionner sans y toucher.

## D. Barre d'état — complète le témoin d'aperçu  ✅ FAIT (83ba5b8)

- [x] D1. Réutiliser `.admin-foot` (déjà présent, 2,3 rem). Contenu : flux SSE +
      nombre de clients, heure de la dernière publication, apparence + résolution,
      « aperçu écran ↗ » (rouvre le grand aperçu), export.
- [x] D2. Écart brouillon ↔ publié (« +1 groupe, +2 beltpacks non envoyés »).
      Nouveau calcul côté client entre `state.data` et l'état publié. À faire
      APRÈS D1 : D1 seul remplace déjà la vignette.
- [~] D3. ANNULÉ (décision Nathan : l'aperçu reste ouvert par défaut). Le témoin
      cohabite avec la barre d'état ; « aperçu écran ↗ » ouvre le grand aperçu.

## Décisions de Nathan (2026-07-23)

- **Bouton d'action : « texte » confirmé.** Réserve exprimée (publier est
  l'action la plus conséquente, sans fond ni contour elle perd son affordance),
  réponse : non. Appliqué tel quel, on n'y revient pas.
- **L'aperçu reste ouvert par défaut.** D3 est donc REVU : on ne supprime pas le
  témoin, il cohabite avec la barre d'état et s'affiche déplié au chargement.
- **Voyant de beltpack connecté en vert.** `.bp-dot.on` l'est déjà (--success) ;
  le point est de ne PAS le passer en `currentColor` dans les blocs en aplat,
  comme le faisait la maquette. Le vert doit survivre au fond coloré.

## E. À trancher

- [x] E2. Palette bornée de 12 teintes calibrées (≥ 4.5:1). Fait (031084b).

## Vérifications exigées à chaque phase

- 256 unitaires + 13 e2e verts, ruff propre.
- Capture de l'admin + console navigateur vide (leçon 2026-07-07).
- Contraste mesuré, pas jugé à l'œil, sur les 6 couleurs de groupe (leçon 2026-07-23).
