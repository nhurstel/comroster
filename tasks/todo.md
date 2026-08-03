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

✅ **Outillage — 2026-07-27.** (1) La CI était rouge sur `main` sans qu'une ligne de code ne change :
`pip install ruff` sans version + aucune config ruff au dépôt = jeu de règles hérité de la version du
jour, élargi en 0.16.0. Corrigé à la racine — version épinglée dans `requirements-dev.txt` (source
unique, la CI installe de là) et `select` explicite dans `pyproject.toml`. (2) Jeu de règles élargi
délibérément (13 familles, retenues après COMPTAGE : `S` faisait 568 signalements, `PTH` 94 — écartés),
50 signalements traités dont 25 à la main ; les `except Exception` légitimes portent maintenant leur
raison. (3) `run-dev.sh` fiabilisé : port vérifié AVANT d'annoncer l'URL, interpréteur appelé par son
chemin `.venv/bin/python` et non via le PATH — les deux causes exactes de la soirée du 2026-07-26 —
et le script entre enfin dans le périmètre shellcheck de la CI.

### Contraintes à respecter (issues des leçons)
- [ ] `[hidden]` : ne poser AUCUN `display` inconditionnel sur `#board-subtitle`, `#onboarding`,
      `.bp-batt` (leçon 2026-06-21 — le `[hidden]{display:none!important}` de main.css:156 protège,
      mais on ne s'appuie pas dessus par paresse)
- [ ] Ne pas casser `height:100vh; overflow:hidden` sur `.display-page` ni `#display-scroll`
      (leçon 2026-06-20 — sinon l'auto-scroll meurt silencieusement)
- [ ] CSP stricte : aucun `<style>` inline, feuilles servies depuis `self` (leçon 2026-07-07)
- [x] **Toutes les feuilles d'apparence chargées d'avance** : le `skin` change en direct par SSE
      `published` sans rechargement de page → un `<link>` conditionnel côté serveur ne marcherait pas.
      Tenu par conception (un seul `skins.css` inconditionnel, `data-skin` sur `<body>` sélectionne)
      et désormais GARDÉ par `test_display_precharge_toutes_les_apparences` (2026-07-27), qui vérifie
      aussi que chaque entrée de `SKINS` a des règles : sans ça, ajouter une apparence suffirait à
      produire un `data-skin` que personne ne style, l'écran retombant en silence sur `basique`.
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

- 297 unitaires + 13 e2e verts, ruff propre (chiffre au 2026-07-27 ; le seuil, c'est « tout vert »).
- Capture de l'admin + console navigateur vide (leçon 2026-07-07).
- Contraste mesuré, pas jugé à l'œil, sur les 6 couleurs de groupe (leçon 2026-07-23).

---

# LOT 2026-07-27 — Header resserré + refonte de l'onglet « Écran »

Demande Nathan : (1) rapprocher les onglets du bouton « Publier » ; (2) l'onglet « Écran »
est « chiant et ennuyeux », il mérite un travail de design et de mise en page.

**Mesures de l'existant** (1440 px de large) : onglets 545→996, horloge 996→1074,
état 1074→1256, Publier 1256→1440. Donc **260 px** séparent les onglets de l'action,
et **216 px de vide** traînent entre le fil d'Ariane et les onglets. L'onglet Écran :
3 colonnes de champs en haut à gauche, ~80 % de surface vide, `<select>` au chrome
natif clair (jure avec la DA), et **aucun retour visuel** — changer d'apparence ne
montre rien tant qu'on n'a pas publié.

## A. Header — les onglets se rapprochent de « Publier »  ✅ FAIT

Arbitrage initial (déplacer horloge + état à gauche) **RÉVOQUÉ par Nathan en cours de
lot** : « l'horloge et l'indicateur d'état doivent quand même rester entre "Réseau" et
"Publier" ». L'ordre est donc conservé et c'est leur EMPRISE qu'on réduit.

- [x] A1. Respiration des chips : `padding: 0 12px` → `0 9px` (horloge **78 → 72 px**).
- [x] A2. Libellé d'état raccourci : « 5 modifications en attente » → « **5 en attente** »,
      qui était déjà l'intention de la maquette (cf. commentaire d'`admin.js`) ; le détail
      reste dans la barre d'état (« +2 groupes, +3 beltpacks non publiés »).
- [x] A3. La largeur figée ne retient plus que les états NOMINAUX. Elle était calée sur
      « Échec de l'enregistrement », donc réservait en permanence la place d'un cas
      exceptionnel (chip **182 → 123 px**).
- [x] A4. MESURÉ à 1440 px : écart onglets↔Publier **260 → 195 px (−25 %)**, sans rien
      déplacer ni supprimer.

## A bis. Onglet actif persisté  ✅ FAIT (bug signalé à l'usage)

Rafraîchir la page depuis « Écran » ramenait sur « Affectations » : l'onglet n'était pas
mémorisé (contrairement à la bascule Blocs/Tableau). Clé `comroster.admin.tab`, valeur
relue confrontée aux panneaux existants (jamais réinjectée dans un sélecteur).
Gardé par `test_indicator_toggles_persist`, qui encodait justement l'ancien comportement.

## B. Onglet « Écran » — rail de réglages + aperçu live du brouillon

Arbitrage Nathan : **mise en page + aperçu live du brouillon**.

*(B1 à B4 : livrés, cases relevées le 2026-08-03 après vérification dans le code —
`?draft=1` et son test (`test_api.py:138`), `.screen-layout`, `<select>` restylés,
`fitPreview()` à 1920×1080 rechargé sur `panneau-affiche`.)*

- [x] B1. Serveur : `/admin/preview?draft=1` rend le **brouillon** (`load_draft()`)
      au lieu du publié. C'est ce qui distingue cet aperçu du témoin « Affichage en
      cours » (bas de la latérale), qui montre ce qui est **à l'antenne**. Deux
      fonctions différentes, donc pas de doublon (leçon 2026-07-25 « un bouton par
      fonction »). + test unitaire.
- [x] B2. Template : `.screen-layout` = rail de cartes (Production / Apparence /
      Indicateurs) + panneau d'aperçu. **Tous les ids conservés** (`#skin-select`,
      `#theme-select`, `#meta-columns`…) → `bindSettings`/`syncSettingsInputs` et les
      e2e ne bougent pas.
- [x] B3. CSS : cartes de réglages, `<select>` restylés (`appearance:none` + chevron
      maison), cases à cocher custom, panneau d'aperçu.
- [x] B4. JS : rendu à **1920×1080 puis mis à l'échelle** via le `fitPreview()`
      existant (leçon 2026-07-23 : un aperçu à une autre résolution est faux par
      construction, l'écran étant en `auto-fit`). Rechargement à l'activation de
      l'onglet, après chaque enregistrement du brouillon, et au resize.

## C. Vue Tableau — sélection multiple (bugs signalés à l'usage)  ✅ FAIT

- [x] C1. Libellé « Table » → « **Tableau** ». La VALEUR `table` est conservée : elle est
      persistée en localStorage, la renommer perdrait la préférence de chacun.
- [x] C2. **BUG RACINE — « ça saute »** : passer en Tableau ne démonte pas la vue Blocs,
      elle est seulement `hidden`. `selectRange` interrogeait tout le document, donc
      voyait CHAQUE personne deux fois (carte masquée + rangée visible), et `indexOf`
      trouvait d'abord la carte — dans l'ordre des blocs, pas celui du tri. Nouveau
      `selectableNodes()` : vue active seulement, et exclusion de l'estompé (non
      cliquable). Prouvé : l'ancien code sélectionnait `[40, 20]` là où l'écran montre
      `[40, 30, 20]`.
- [x] C3. **Sélection de texte parasite** : MAJ+clic surlignait les libellés en bleu par
      dessus la sélection. `user-select: none` sur rangées et cartes, `text` conservé
      dans les champs d'édition sur place.
- [x] C4. **Affectation en lot** : barre de sélection « Affecter à », ET le sélecteur de
      groupe d'une rangée agit sur TOUTE la sélection s'il en fait partie (même règle que
      le glisser-déposer d'une sélection).

## D. Raccourcis clavier du plateau  ✅ FAIT

- [x] D1. **⌘Z / Ctrl+Z** (⌘⇧Z rétablit). Portée : le BROUILLON seul — groupes, noms,
      numéros, affectations, réglages d'écran. Réseau / IP / Wi-Fi / antenne / mot de
      passe sont hors d'atteinte **par construction** (endpoints distincts, jamais dans
      `state.data`), pas via une liste d'exclusions à maintenir. Vérifié par un test qui
      enregistre une IP fixe puis annule une édition de roster : l'IP est intacte.
      Frappes regroupées (700 ms) sinon effacer un mot demanderait dix ⌘Z. Historique
      remis à zéro quand le brouillon est REMPLACÉ en bloc (import, restauration,
      resynchro distante).
- [x] D2. **⌘A** = tout sélectionner dans la vue active (affectés + réserve en Blocs) ;
      un filtre en cours restreint naturellement la portée.
- [x] D3. **Échap** = quitter la sélection. Le décompte de publication garde la priorité.
- [x] D4. Les trois sont neutralisés dans un champ de saisie et dans un dialogue
      (`onBoard`) : ⌘Z et ⌘A y gardent leur sens NATIF.

## Vérifications de ce lot
- [x] **298 unitaires + 18 e2e verts, ruff propre.**
- [x] Captures avant/après + console navigateur vide (leçon 2026-07-07).
- [x] Géométrie MESURÉE : header 260 → 195 px ; aperçu ratio 1,778 exact, sans débord.
- [x] **Chaque nouveau test confronté à un cas qui échoue volontairement** (leçon
      2026-07-23) : restauration d'onglet, balayage de sélection, ⌘Z hors champ,
      Échap. Les quatre échouent bien sans leur correctif.

---

# LOT 2026-07-27 (soir) — Sortir Journal / Santé / Écran du registre « template »

Demande Nathan : « les sous menu genre Journal, Écran, Santé font très AI slop ».

**Diagnostic mesuré sur captures (1440×900), pas à l'œil :**
- **Santé** : 6 rectangles arrondis IDENTIQUES, motif « libellé à gauche · valeur à droite »
  répété 14 fois. « Cœurs : 8 » a le même poids visuel que « stockage à 90 % », seule ligne
  capable de faire tomber un show. La page s'appelle Santé et **ne dit jamais si le boîtier
  va bien**. 80 % de surface vide. Sur un poste non-Linux, la moitié des cartes affichent
  « indisponible » comme si c'était une donnée.
- **Journal** : un journal qui **n'encode pas le temps** — date complète réimprimée sur
  chaque ligne au lieu de servir d'axe ; une entrée seule dans une pilule, puis 800 px de
  vide sans état vide rédigé.
- **Écran** : trois boîtes arrondies empilées, même motif « carte + libellé capitales ».

**Ancrage** (le sujet, pas un thème plaqué) : ComRoster est un BOÎTIER DE RÉGIE manipulé
sous pression avant un show. Son vernaculaire est la conduite, le contrôle avant lever de
rideau, le bandeau d'état — pas la grille de tuiles.

## S. Santé — « verdict d'abord, preuves ensuite » (arbitrage Nathan)
- [x] S1. Bandeau de tête répondant à « puis-je lancer le show ? » : un mot (Prêt /
      À surveiller / Attention), la raison en clair, et la ligne de vie (écrans en ligne,
      dernière publication). C'est l'élément signature — tout le reste reste discipliné.
- [x] S2. Les mesures deviennent un RELEVÉ dense en une colonne, **trié par criticité**.
      Réglette uniquement là où un SEUIL existe (stockage, mémoire, température) ; les
      autres valeurs sont des lignes nues.
- [x] S3. Hiérarchie typographique inversée : la VALEUR domine (chiffres tabulaires), le
      libellé s'efface. Aujourd'hui les deux ont le même poids.
- [x] S4. L'indisponible n'occupe plus une carte : une seule ligne en pied
      (« non mesuré ici : … »), au lieu de tuiles vides.

## J. Journal — « conduite chronologique » (arbitrage Nathan)
- [x] J1. L'heure devient une GOUTTIÈRE fixe à gauche, le long d'un filet vertical continu
      qui matérialise l'écoulement. C'est un vrai axe, pas un ornement.
- [x] J2. Groupement par jour (« Aujourd'hui — 27 juillet ») : la date cesse d'être
      réimprimée sur chaque ligne.
- [x] J3. État vide RÉDIGÉ (invitation à agir), pas une page blanche.
- [x] J4. Le volet « Technique » garde son registre dense (c'est un `tail`), mais aligné
      sur la même gouttière de temps.

## E. Écran — aligner sur le même registre
- [x] E1. Sortir du motif « boîte arrondie + libellé capitales » : sections séparées par
      des filets dans une seule colonne, comme le relevé de Santé.

## Vérifications exigées
- [x] Unitaires + e2e verts, ruff propre.
- [x] Captures avant/après + console navigateur VIDE (leçon 2026-07-07).
- [x] Tout nouveau test confronté à un cas qui échoue volontairement (leçon 2026-07-23).
- [x] Contraste des états (Prêt/Surveiller/Attention) MESURÉ, pas jugé à l'œil.

## Retours d'usage sur le lot design (2026-07-28) — FAIT

- [x] **Journal, mise en page** : l'îlot centré à 880 px ne s'accrochait à rien → pleine
      largeur, alignée sur la barre d'outils. Surtout, le **filet vertical continu a été
      retiré** : les lignes étant espacées uniformément quel que soit le temps écoulé, il
      affirmait une échelle proportionnelle qui n'existe pas. La structure temporelle est
      portée par les ruptures de journée, qui, elles, sont vraies. Entête de journée en un
      seul libellé (« aujourd'hui » OU la date, plus les deux).
- [x] **« werkzeug » dans le volet Technique** — CAUSE RACINE : le tampon accroche le
      logger RACINE, donc capte le journal d'ACCÈS HTTP (une ligne par requête, fichiers
      statiques compris). 53 lignes après un seul chargement : les 500 entrées du tampon
      étaient noyées par du bruit, alors qu'il existe pour diagnostiquer sans SSH.
      `ACCESS_LOGGERS` écarte `werkzeug` et `gunicorn.access` **en dessous de WARNING**
      seulement — une vraie erreur du serveur reste visible. Le nom de logger affiché
      devient un nom de composant (`comroster.services.antenna` → `antenna`), complet en
      infobulle. Gardé par `test_logbuffer_ecarte_les_acces_http_mais_garde_leurs_erreurs`.
      Corrigé au passage : le message d'écran vide accusait le filtre alors que le tampon
      était simplement vide (deux causes, deux textes).
- [x] **Sous-titres enfantins supprimés** (les cinq listés par Nathan) + le séparateur
      « / » du fil d'Ariane devenu orphelin sur Journal et Santé.
- [x] **Charge processeur expliquée** : « 3.00 4.64 5.12 » ne se lit qu'en RAPPORT AU
      NOMBRE DE CŒURS. Devient une mesure à seuil — « 55 % de la capacité », réglette,
      alerte à 100 %, surveillance à 70 % — avec le détail brut en légende. Virgule
      décimale française rétablie partout (`toFixed` produisait « 408.1 Go »).
- [x] **Statistiques temporelles** : nouveau service `Lifetime` (carnet de bord).
      Persiste première mise en service, cumul de fonctionnement à travers les
      redémarrages, et nombre de démarrages. Cumul tenu en mémoire sur une origine
      MONOTONE (un réglage NTP ne doit pas créer d'heures de fonctionnement), écrit sur
      disque toutes les 5 min seulement — usure de la carte SD, et une coupure ne coûte
      au pire que l'intervalle. Fail-safe : fichier corrompu → `.bak` + repart à zéro,
      jamais d'exception. 5 tests dédiés (`tests/test_lifetime.py`).
      La page distingue trois horizons : allumé depuis / session en cours / cumulé.
- [x] **Palette des groupes triée** : par famille de teinte (rouge → orange → jaune →
      vert → turquoise → bleu → violet → magenta), du clair au sombre dans chaque
      famille, neutres en fin. Les VALEURS sont inchangées, donc les contrastes ≥ 4,5:1
      validés au banc le restent par construction. Un tri sur la teinte seule faisait
      sauter la luminosité d'une case à l'autre.

---

# LOT 2026-07-28 (audit) — Défauts, structure, ajouts

Origine : audit complet du projet (tout le code lu, couverture backend mesurée à 90 %,
304 unitaires + 18 e2e verts, ruff propre au moment de l'audit). Arbitrage Nathan :
**tout traiter** en section 1 et 2 ; en section 3, les ajouts 1, 3, 4 et 5 — la
découverte d'antenne **sans retirer** la saisie IP directe.

## A. Défauts relevés (preuve à l'appui)

- [x] **A. L'admin se compte comme afficheur.** `subscribeAdmin()` ouvre `/events`, que
      `broker.subscribe()` compte sans distinction → « 1 afficheur » sans aucun écran,
      dans la barre d'état ET dans la ligne de vie de Santé (l'écran censé ne pas mentir).
      Prouvé sur serveur live : 0 abonné → 1 après un seul flux admin.
      Correctif : `Broker.subscribe(kind)` + `display_count` distinct, `/events?role=admin`.
      ⚠️ Le cap `SSE_MAX_CLIENTS` doit rester sur le TOTAL (c'est le pool de threads qui
      est fini), mais un admin ne doit jamais évincer un écran.
- [x] **B. L'import `.rost` perd `production_name` et `text_scale`.** `importConfig`
      reconstruit `state.data` champ par champ et en oublie deux (ajoutés après coup).
      Récidive du piège déjà noté pour `skin`. Correctif de fond : **ne plus énumérer** —
      filtrer sur une allowlist partagée, pour qu'un futur champ ne se reperde pas.
- [x] **C. `.gitignore` incomplet.** 4 fichiers d'état non ignorés (`journal.jsonl`,
      `lifetime.json`, `network.json`, `viewer.json`) + `.bak`/`.tmp`. `lifetime.json`
      est DÉJÀ untracked à la racine. Risque : committer un PSK Wi-Fi en clair.
      Le README affirme le contraire (« Tous listés dans .gitignore ») → à corriger aussi.
- [x] **D. `pytest.ini` rend `[tool.pytest.ini_options]` inerte.** Valeurs identiques
      aujourd'hui, donc rien ne casse — mais toute modif du pyproject sera SANS EFFET,
      en silence. Une seule source.
- [x] **E. shellcheck non épinglé en CI** (`apt-get install shellcheck` + `ubuntu-latest`) :
      exactement la cause racine de la panne ruff du 2026-07-26, non encore éliminée ici.
- [x] **F. `viewer_agent` : reconfiguration réseau sans authentification.** `POST /config`
      (port 8081) écrit `viewer.json` ET `network.json` sans mot de passe ni CSRF, sur un
      `HTTPServer` mono-thread (un client lent le bloque entièrement).
- [x] **G. Pas de changement de mot de passe admin** : seul `recover` change le mot de
      passe, en brûlant le code de récupération. Aucune rotation possible.
- [x] **H. Usure carte SD** : chaque `save_draft` (debounce 500 ms) fait une copie `.bak`
      complète + 2 `fsync`. En tension directe avec le soin porté à `lifetime.py`.

## B. Axes structurels

- [x] **B1. Harnais de test JS.** `admin.js` = 2194 lignes, plus que `api.py` + `model.py`
      réunis, sans aucun test unitaire. C'est le motif dominant de `lessons.md`.
      Approche : extraire la logique PURE en modules `static/js/lib/*.js` sur le patron
      d'`ink.js` (UMD-lite : `window.ComRoster` en navigateur, `module.exports` en Node),
      puis Vitest. **Aucune dépendance JS au runtime** — l'engagement du README tient.
- [x] **B2. Découpage d'`admin.js`** : conséquence de B1, pas un but esthétique.
- [x] **B3. Constantes dupliquées** (`SKINS`, `TEXT_SCALES` en 3 exemplaires) : test de
      cohérence qui échoue si les listes divergent.
- [x] **B4. Couverture outillée** : `coverage` épinglé dans requirements-dev + seuil CI.
- [x] **B5. Rate-limit sur `/api/live`** (public, sans limite).

## C. Ajouts retenus

- [x] **C1. Sauvegarde / restauration complète du boîtier** (ajout n°1). L'export actuel
      ne couvre que le roster : un boîtier mort emporte réseau, antenne, configs, mot de
      passe. Archive unique exportable/réinjectable.
- [x] **C3. Points de repère nommés dans l'historique** (ajout n°3) : nom optionnel à la
      publication, et épinglage qui protège de la purge 30 j / 50 snapshots.
- [x] **C4. Feuille d'affectation imprimable** (ajout n°4) : les régisseurs travaillent sur
      papier, et c'est le filet quand le boîtier tombe.
- [x] **C5. Découverte automatique de l'antenne** (ajout n°5) — **la saisie IP directe
      reste**, exigence Nathan. La découverte PROPOSE, elle ne connecte jamais seule :
      la garde anti-SSRF (littéral IP) doit survivre.

## Vérifications exigées à chaque étape
- Unitaires + e2e verts, ruff propre, shellcheck propre (version de la CI).
- Chaque nouveau test confronté à un cas qui échoue volontairement (leçon 2026-07-23).
- Aucun processus de fond laissé sur un port partagé (leçon 2026-07-26).

## Livré et vérifié (2026-07-28)

**Vérifications, toutes passées :** 407 unitaires · 27 e2e · 30 tests JS (Vitest) ·
ruff propre · shellcheck **0.9.0 (version exacte de la CI, via Docker)** propre ·
couverture 88 % branches comprises, seuil CI posé à 88.

**Chaque garde a été confrontée à un cas qui échoue volontairement** (leçon 2026-07-23) :
- `production_name` retiré de `DRAFT_FIELDS` → le test JS tombe (« champ perdu à l'import ») ;
- une apparence retirée de `board.js` → la garde de cohérence JS/Python tombe ;
- un jeton CSS renommé → `test_css_tokens` tombe ;
- `git check-ignore` discrimine bien (README.md et app.py ressortent « non ignorés »),
  et les 4 fichiers manquants étaient prouvés absents avant correction ;
- épingle retirée d'un instantané vieilli de 90 jours → il est bien purgé (assertion miroir).

**Deux défauts trouvés PENDANT le lot, absents de l'audit initial :**
- **Course brouillon ↔ remplacement en bloc.** Un enregistrement différé parti avec
  l'ancien contenu revenait après une restauration et l'écrasait, silencieusement.
  Corrigé par un compteur de génération ; « Sauvegarder » vide en outre la file
  d'enregistrement avant de lire l'état serveur, comme le fait la publication.
- **`build_payload` collectait les configurations nommées sans les renvoyer** : elles
  n'étaient pas sauvegardées. Masqué par une assertion conditionnelle, signalée par ruff.

**Arbitrages assumés :**
- Le carnet de bord (`lifetime.json`) et `history/` restent HORS sauvegarde — le premier
  est l'identité du boîtier physique, le second est volumineux et dérivé.
- L'agent afficheur est protégé par la PRÉSENCE PHYSIQUE (code affiché à l'écran), pas par
  un compte. La page reste consultable sans code et l'agent parle en HTTP clair : garde
  contre l'accident et le passant, pas contre un attaquant sur le même réseau — c'est écrit
  tel quel dans `deploy/raspberry-pi.md`.
- `POST /api/publish` accepte un `label`, mais l'interface nomme APRÈS COUP (dialogue
  Historique) : on ne sait pas en publiant que cette version-là sera « la bonne ».
- Vitest et coverage sont des dépendances de DÉVELOPPEMENT. `static/js/*.js` reste du
  JavaScript nu chargé par de simples `<script>` : l'engagement « zéro dépendance JS »
  porte sur le runtime et il tient.

---

# LOT 2026-07-28 (soir) — Transition d'arrivée sur l'écran à la publication

Demande Nathan : « une petite animation sur le display quand une nouvelle config lui est
envoyée, au lieu de rafraîchir avec une coupure nette », désactivée en mode performance,
puis « fais-le bien pour les 3 thèmes ».

Spec : [docs/superpowers/specs/2026-07-28-display-transition-publication-design.md](../docs/superpowers/specs/2026-07-28-display-transition-publication-design.md)

- [x] **Déclencheur = l'évènement `published` SEUL.** `snapshot` est réémis à chaque
      ouverture de flux, donc à chaque reconnexion (toutes les 4 s quand le réseau tousse) :
      brancher l'animation sur `render()` l'aurait rejouée en plein show, sans rien de neuf
      à montrer. `apply(eventData, animate)`.
- [x] **Séquence ~450 ms** : sortie en opacité de la grille (160 ms) → `render()` sur une
      grille invisible → arrivée des blocs en cascade (260 ms, pas de 35 ms, **plafonné à
      8 rangs** sinon 20 groupes s'étaleraient sur une seconde).
- [x] **Trois apparences, trois gestes** — une cascade uniforme aurait été fausse :
      `basique` = la carte arrive (fondu + 6 px) ; `lineaire` = fondu PUR, un déplacement
      décalerait les filets et le tableau cesserait d'être un tableau ; `grille` = aplat
      d'abord (160 ms) puis contenu (260 ms), un déplacement ferait fuir le fond dans les
      gouttières de 6 px. Réglé par des jetons `--anim-*` redéfinis par apparence, sur le
      modèle des bornes `--fit-*`.
- [x] **En-tête** : seuls les éléments dont la valeur CHANGE se fondent, la comparaison
      vivant chez `writeText()`, seul écrivain de ces textes. Horloge et voyant « En direct »
      exclus — ce sont les deux repères permanents, les faire clignoter les ferait mentir.
- [x] **Coupure** : garde en JS d'abord (rendu direct, aucun timer armé — sinon l'écran
      paierait 160 ms de latence pour une animation qui ne joue pas), CSS
      `:not([data-perf="on"])` en second filet. Idem `prefers-reduced-motion` via
      `REDUCED_MOTION`. `perf` est lu dans la donnée QUI ARRIVE : activer le mode
      performance ne s'accompagne pas d'une dernière animation d'adieu.
- [x] **Rien côté serveur** : aucun champ, aucun réglage d'admin ajouté.

**Bénéfice non demandé, obtenu gratuitement** : `render()` fait `stopAutoScroll(); setOffset(0)`.
Si l'écran défilait, il SAUTAIT en haut à chaque publication ; ce saut a désormais lieu à
opacité nulle.

**Effet de bord favorable** : ce lot annule la réserve notée plus haut (« le mode performance
devient un no-op sur `lineaire`/`grille` ») — il a maintenant un contenu sur les trois.

**Vérifié :** 409 unitaires · 30 e2e (dont 3 nouveaux) · 30 JS · ruff propre. Captures des
**3 apparences × 2 thèmes en pleine cascade** + console navigateur vide. Les 4 gardes ont
été confrontées à un cas qui échoue volontairement (script de mutation, leçon 2026-07-23) :
retirer la garde perf, animer sur `snapshot`, retirer le geste d'une apparence, retirer le
`:not([data-perf])` d'une règle → les 4 tests tombent bien.

**Limite assumée de la validation** : pour photographier la cascade, elle a été ralentie en
CSSOM, `--anim-in` et `--anim-content-in` étant portés à la même valeur — le décalage
160/260 ms propre à `grille` n'est donc pas visible sur les captures, seulement en mouvement.
Et la fluidité réelle ne se mesure que sur le Pi 3.

**Défaut repéré au passage, NON corrigé (hors périmètre)** : `display.js` référence
`#sync-hint` (« Mises à jour en direct actives », « Tentative de reconnexion… ») mais
l'élément n'existe plus dans `display.html` — `syncHint` est donc toujours `null` et ces
messages ne s'affichent jamais. À trancher : rétablir l'élément ou retirer le code mort.

---

# LOT 2026-07-29 — Écran de démarrage du boîtier (« voyant de face avant »)

Demande Nathan : « on a une animation de démarrage quand le raspberry boot, je ne l'aime
pas, propose moi d'autres alternatives dans notre style » → puis « originales, peut-être
avec le logo ». Quatre directions proposées (voyant de face avant / roster qui se pose /
la poursuite / le noir de salle) ; **retenue : le voyant de face avant**.

**Ce qui n'allait pas dans l'ancien** (`deploy/boot-splash.html`, faux journal vert) :
- Les `[ OK ]` étaient **faux** — le commentaire du code l'avouait : « purement esthétique,
  n'attend rien ». L'écran affirmait un diagnostic qu'il ne faisait pas. Même famille que
  le filet vertical du Journal (leçon 2026-07-28) : *un ornement qui ressemble à une mesure
  doit en être une* — ici, à un diagnostic.
- Registre étranger au projet : vert phosphore, halo, `◤ ComRoster ◢`. Aucune des trois
  apparences ne parle ce langage.
- Le seul état réel — le serveur répond-il ? — n'était jamais montré.

**Le nouveau** : le glyphe ComRoster au centre, immobile, sauf son **disque**, qui respire
comme la LED de veille d'un appareil de scène. Cette respiration EST l'état de la sonde :
gris (démarrage) → ambre + compteur (> 12 s) → rouge + consigne d'action (> 30 s) → vert
(prêt). Identité et état sont le même objet, aucun élément ajouté, aucun texte inventé.

- [x] Glyphe **inline** : la page s'ouvre en `file://` avant le serveur, aucune requête
      n'est possible. Polices lues en relatif sur le disque, repli système si Chromium
      refuse le `file://`.
- [x] Jetons de couleur repris du thème nuit de `display.css` → bascule vers `/display`
      sans changement de fond, aucun flash.
- [x] Plus l'état est grave, plus le battement est rapide ET **moins il est profond**
      (`--creux` 0,28 → 0,5 → 0,62) : au creux de 28 %, un rouge sur fond sombre disparaît
      presque, et une alarme absente la moitié du temps est une mauvaise alarme.
- [x] **Plancher d'affichage de 5 s** (décision Nathan : sinon un kiosk relancé pendant que
      le service tourne ferait clignoter la page moins d'une seconde). La différence avec
      l'ancien `MIN_MS` n'est pas la durée mais ce qu'on montre pendant : dès que `/healthz`
      répond, le disque passe au vert et la page affiche « prêt » jusqu'à la bascule.
- [x] Contrat `?next=` / `?health=` **inchangé** → `kiosk-run.sh` non modifié.
- [x] Doc alignée : `kiosk.md` et `raspberry-pi.md` citaient encore « splash Booting
      ComRoster », titre qui n'existe plus.

**Vérifié au rendu réel** (Playwright, `file://`, 1920×1080) : les quatre états atteints
avec leurs **vrais seuils** — veille, lent à 13 s, mort à 32 s avec la consigne — puis
« prêt » affiché à **0,03 s** et bascule à **5,08 s**. Aucune exception JS ; console vide
sur le chemin nominal (sur le chemin dégradé, chaque sonde vers un serveur éteint
journalise un `ERR_CONNECTION_REFUSED` : l'exiger vide là-bas n'aurait rien prouvé).

**Note de sonde — avertissement d'abord SURÉVALUÉ, puis vérifié.** La page étant ouverte
depuis un fichier, le navigateur lui interdit de LIRE la réponse réseau : elle sait
seulement « quelqu'un a répondu », jamais quoi. J'en avais tiré un risque de bascule vers
une page d'erreur — **inexact dans l'installation standard** : `kiosk-run.sh` interroge
gunicorn en direct sur `127.0.0.1:8080` et un service pas encore démarré ne répond PAS
(connexion refusée), donc aucune confusion possible. Le cas n'existerait qu'avec un reverse
proxy devant ComRoster (`deploy/nginx.conf`, optionnel et non installé) sur lequel on
repointerait le kiosk : le proxy, lui, répond « 502 » avant que gunicorn ne soit levé.
Recadré en commentaire dans le fichier, avec la condition de déclenchement.

---

**Reste ouvert (non demandé, non fait) :** découpage complet d'`admin.js` — trois modules
purs en sont sortis (`board.js`, `netmask.js`, + `ink.js` rendu testable), ce qui donne au
harnais de quoi mordre ; le reste du fichier est du câblage DOM, dont l'extraction
demanderait un jsdom et une refonte que ce lot ne justifie pas.

---

# LOT 2026-07-30 — Menu « Réglages »

Spec : [docs/superpowers/specs/2026-07-30-menu-reglages-design.md](../docs/superpowers/specs/2026-07-30-menu-reglages-design.md)
Plan : [docs/superpowers/plans/2026-07-30-menu-reglages.md](../docs/superpowers/plans/2026-07-30-menu-reglages.md)

Demande Nathan : regrouper Réseau, Sauvegarde, Mot de passe, Journal et Santé dans un menu
à part. Nom retenu **Réglages** (mes réserves — Journal et Santé ne se règlent pas ;
« Système » avait déjà été supprimé le 2026-07-25 — consignées dans la spec puis tranchées),
libellé texte plutôt qu'engrenage.

- [x] Les cinq fonctions vivaient dans DEUX zones (barre d'onglets pour Réseau/Journal/Santé,
      section « Boîtier » de la latérale pour Sauvegarde/Mot de passe). L'en-tête passe de six
      entrées à quatre, et la latérale ne garde plus que du contenu de plateau.
- [x] **Ids conservés** (`#network-btn`, `#backup-btn`, `#password-btn`, `#reboot-btn`) : les
      quatre `addEventListener` d'`admin.js` n'ont pas changé. Le lot est structurel.
- [x] **Sept clics e2e** visaient ces ids en direct et auraient expiré dans un menu fermé
      (Playwright attend `visible`) — repéré AVANT d'écrire le code. Helper unique
      `tests/e2e/helpers.py::open_reglages`.
- [x] Clavier : Échap ferme et rend le focus, ↑↓ parcourent en boucle, et la condition
      « menu ouvert » entre dans le seul prédicat `onBoard` (⌘Z/⌘A gardent leur sens natif).
- [~] **Redémarrer : d'abord mis dans le menu, RAMENÉ au pied de la latérale en cours de lot**
      (« il y sera mieux à côté de Déconnexion »). Se défend mieux que mon choix initial : une
      action destructrice ne traîne pas dans un menu qu'on parcourt, et elle voisine l'autre
      action de sortie. La règle `.side-foot-row .nav-item`, supprimée puis rétablie, et les
      deux tests qui encodaient l'emplacement intermédiaire ont suivi.

**Quatre défauts de MON plan, trouvés à l'exécution :**
- `from .helpers import` échouait : `tests/e2e` n'est pas un package (aucun `__init__.py`),
  pytest insère le dossier dans `sys.path` → import absolu obligatoire.
- `pytest tests/e2e -q` renvoyait « 30 deselected » : le marqueur `e2e` est exclu par défaut,
  il faut `-m e2e`. Un vert qui ne prouvait rien, exactement le piège du 2026-07-28.
- `npx vitest run --dir tests/js` affichait « PASS (0) FAIL (0) » — zéro test exécuté, code
  retour 0. La commande du projet est `npm test` (30 tests, 3 fichiers). Même faux signal.
- Mon test « Échap ferme le menu AVANT de quitter la sélection » **passait dans les deux
  ordres** : `onBoard` excluant déjà le menu ouvert, la sélection est protégée quel que soit
  le rang des branches. Le seul rang qui décide est celui face au décompte de publication,
  qui ne dépend pas d'`onBoard` — le test a été refait là-dessus et il tombe bien sous
  mutation. Le commentaire du code affirmait la même chose fausse, rectifié.

**Vérifié :** 493 unitaires · 36 e2e (dont 6 nouveaux) · 30 JS · ruff propre. Capture 1440×900 du
menu ouvert, console navigateur vide (collecteur prouvé armé par une sonde), hauteur d'en-tête
**mesurée à 53 px exactement** (jeton `--top-h`) et panneau contenu dans la fenêtre (bord droit
1059 sur 1440) — mesuré, pas jugé à l'œil.

**Chaque garde confrontée à un cas qui échoue volontairement :** retirer un item du menu fait
tomber la garde d'unicité d'accès ; faire passer la branche Échap du menu devant le décompte
de publication fait tomber le test de rang ; le test de ⌘Z porte un témoin positif (hors menu,
le même ⌘Z annule bien) sans quoi son assertion négative ne prouverait rien.

**Coût assumé :** Santé passe d'un clic à deux, alors que c'est le contrôle d'avant-show.
Atténuation identifiée et NON faite (point d'alerte sur le menu quand le verdict n'est pas
« Prêt ») : elle demanderait de sonder la santé depuis l'admin, ce qui n'existe pas.

**Arbitrage assumé :** le menu vit dans `admin.html` seul. `journal.html` et `health.html`
n'embarquent ni les dialogues ni `admin.js` ; y porter le menu voudrait dire les dupliquer.
Ces deux pages restent des culs-de-sac avec leur lien de retour.

---

## Lot « Impression » — 2026-07-30

Demande de Nathan : renommer « Feuille imprimable » en « Impression » ; « le menu Impression
est pas très complet et le format d'impression est un peu moche ». Cadrage obtenu en une
salve : usage = **filet quand le boîtier tombe, tiré en A3 la plupart du temps**, menu dans
la barre de la page, quatre familles de réglages, direction « document de production ».

**Point de départ, capturé et non supposé.** Trois défauts que la lecture du CSS ne montrait
pas, révélés en rendant la feuille en média `print` puis en PDF :
- [x] l'en-tête de colonne disait « Nom » et affichait le RÔLE — le champ nom n'existe plus
      dans le modèle ; deuxième occurrence de ce fantôme après le README (leçon 32) ;
- [x] le pied crachait `2026-07-30T13:13:59Z`, de l'ISO UTC dans une interface francophone,
      alors que la route formatait déjà `printed_at` en français ;
- [x] colonne de visa à 3,2 em (~32 px), où l'on ne peut rien signer, et une demi-colonne
      de vide creusée par `break-inside: avoid` posé sans exception.

**Quatre capacités sondées avant d'être promises** (Chromium 148, PDF relu par pdftotext) :
boîtes de marge CSS **OUI**, `position: fixed` répété **OUI**, `@page size` honoré **OUI**,
`insertRule('@page …')` à chaud **OUI**. J'allais écarter le numéro de page en le croyant
impossible ; et la dernière mesure a rendu inutile tout le mécanisme de rechargement prévu.

**Livré :**
- [x] Renommage complet, URL `/admin/print` conservée (l'aide-mémoire terrain la diffuse).
- [x] A3 portrait / 3 colonnes par défaut, en-tête posé, visa à 28 mm, grille aérée.
- [x] Barre de six réglages **mémorisés** — sans persistance, l'A3 serait à re-choisir à
      chaque impression, soit le reproche de départ reconduit.
- [x] Bandeau d'identification répété par page, numéro de page, zébrure en colonne unique.
- [x] Huit tests e2e qui lisent un **vrai PDF**, seuls à prouver quelque chose sur du papier.

**Décision structurelle du lot : le défaut est l'ABSENCE d'attribut.** `print.css` porte
A3 / 3 colonnes / visa dans ses règles de base ; chaque `data-*` n'est qu'un dépassement.
Une seule source pour le défaut, rien à recopier entre Python, JS et CSS, aucun scintillement
au chargement — et le script bloquant en `<head>` que prévoyait la spec devient inutile. Une
garde structurelle relie les deux : chaque valeur de l'allowlist JS doit avoir son sélecteur
dans `print.css`, sinon le réglage serait cliquable sans effet.

**Trois défauts trouvés en regardant le PDF, qu'aucun test sur le DOM n'aurait vus :**
- deux pieds disant la même chose, dont un flottant au milieu du vide ;
- un groupe coupé qui ne se réidentifiait pas — défaut que j'avais introduit moi-même en
  rendant les groupes longs coupables, invisible sur ma première capture à 27 beltpacks
  où aucun groupe n'atteignait le seuil ;
- ce nom, une fois posé, sortait en petites capitales grises : `.sheet-table th` a la même
  spécificité et vient plus bas. Récidive exacte de la leçon 29.

**Défaut de MON exécution :** `perl -0pi` avec un caractère large (☐) a doublement encodé
tout `print.html`. Restauré par `git checkout`, refait à l'outil d'édition, contrôlé.

**Vérifié :** 504 unitaires · 44 e2e (dont 8 nouveaux) · 40 JS · ruff propre. PDF A3 mesuré
à 841,92 × 1191,12 pt, console vide, chaque garde confrontée à une mutation qui la fait
tomber.

**Reste à faire — le seul point qui demande Nathan :** juger le rendu final à l'œil sur un
aperçu d'impression réel. Aucun test ne le fait à ma place.

---

## Lot « Panneaux Journal · Santé · Impression » — 2026-07-30

Demande de Nathan : « les onglets admin journal et santé et impression doivent être intégrés
et pas ouvrir une nouvelle page, il faudrait que ça fasse comme affectations et écran, que le
header reste en place ». Cadrage obtenu en une question : **points d'entrée inchangés** —
Santé et Journal restent dans le menu « Réglages », Impression reste dans la latérale
« Données » ; seul le COMPORTEMENT change (bascule de panneau, plus de navigation).

### Ce qui est en jeu
`selectTab` d'admin.js pilote déjà `.tab-panel[data-panel]`. Trois panneaux à y brancher.
Le point dur n'est pas la bascule, ce sont les effets de bord d'une fusion de documents :
identifiants qui se marchent dessus, sélecteurs à portée document, sondages qui tournent
en permanence, et une feuille d'impression dont le PAPIER est verrouillé par huit tests e2e.

### Plan
- [x] 1. **Collision `.tb-seg .seg-btn`** — admin.js lie la bascule Blocs/Table à TOUS les
      `.seg-btn` du document. Les boutons Événements/Technique du journal en portent la
      classe : fusionnés, ils appelleraient `setViewMode(undefined)`. Sélecteur à borner
      à `.board-toolbar` AVANT d'introduire le panneau (sinon on introduit le défaut).
- [x] 2. **`selectTab` généralisé** : toute entrée `[data-tab]`, où qu'elle vive (onglet,
      item de menu, rangée de latérale), bascule son panneau. Une entrée nichée dans un
      `.tab-menu` allume l'onglet qui porte ce menu — sinon, sur Journal, aucun repère
      dans l'en-tête ne dit où l'on est. Relation LUE DANS LE DOM, pas déclarée deux fois.
- [x] 3. **Événement `panneau-affiche`** émis sur le panneau montré. Remplace le
      `if (name === "screen") reloadScreenPreview()` : un seul mécanisme, et journal.js,
      health.js, la trame d'impression s'y branchent sans qu'admin.js les connaisse.
- [x] 4. **Sondage borné au panneau visible.** journal.js (5 s) et health.js (4 s) tournent
      aujourd'hui parce que leur page ne montre qu'eux. Sur l'admin ils tourneraient en
      permanence pendant qu'on travaille sur le plateau. Condition : panneau affiché.
- [x] 5. **`status-info` renommé** (`journal-status`, `health-status`) et logé dans la barre
      d'outils du panneau : l'identifiant existait dans DEUX documents et le pied de
      l'admin est déjà pris. Le panneau Santé gagne la barre d'outils qu'il n'avait pas —
      le fil d'Ariane ne dit plus « Santé du boîtier », il faut que le panneau le dise.
- [x] 6. **Impression = trame (`<iframe>`) sur `/admin/print?embed=1`.** Le document
      imprimé reste INTACT : les huit tests e2e qui lisent un vrai PDF continuent de
      porter sur lui. `embed=1` retire le lien « ← Administration », qui n'a pas de sens
      dans une trame. Rechargée à CHAQUE affichage (imprimer une conduite périmée est
      précisément le défaut que cette feuille existe pour éviter), en conservant la
      source choisie (publié / brouillon) relue dans l'URL de la trame.
- [x] 7. **Routes `/admin/journal` et `/admin/health` → redirection** vers
      `/admin?panneau=…`. Les signets survivent, les templates dupliqués partent.
      `?panneau=` est lu au chargement puis effacé de l'URL (`replaceState`).
- [x] 8. **Suppression de `journal.html` et `health.html`** : leur contenu vit désormais
      dans les panneaux. Deux documents qui divergent, c'est le défaut de départ.
- [x] 9. **Tests** — garde structurelle (`data-tab` ⇄ `data-panel`, et les identifiants
      qu'attendent journal.js/health.js présents dans admin.html), redirections, `embed`,
      et e2e : l'en-tête RESTE en place et l'admin reste vivante sur chaque panneau.

### Ce que je ne fais pas
Promouvoir ces trois entrées en onglets de plein droit (écarté par Nathan).
Toucher au rendu papier : il est verrouillé et hors sujet.

### Livré et vérifié

**Cadrage tenu :** points d'entrée inchangés (choix de Nathan). Santé et Journal restent
dans le menu « Réglages », Impression dans la latérale « Données » — mais l'onglet
« Réglages » s'allume quand on est sur l'un de ses panneaux, et la rangée « Impression »
se surligne : sans ce repère, on aurait été sur un panneau sans que rien dans l'en-tête
ne dise où.

**En-tête mesuré à 53 px sur les cinq panneaux** — le même jeton `--top-h` qu'avant le lot,
donc il n'a pas bougé d'un pixel. Aucun débordement horizontal à 1440×900, console vide.

**Deux défauts trouvés dans l'ANCIEN code, pas dans le nouveau :**
- `admin.js` liait la bascule Blocs/Table à tous les `.tb-seg .seg-btn` du document. Le
  panneau Journal en apporte deux : cliquer « Technique » aurait appelé
  `setViewMode(undefined)` et fait disparaître les deux vues du plateau. Borné AVANT
  d'ajouter le panneau — sinon j'introduisais le défaut moi-même.
- `status-info` existait à l'identique dans `journal.html` et `health.html` ; réunis, l'un
  des deux devenait introuvable et son panneau serait resté muet sur « serveur injoignable ».

**Une hypothèse porteuse sondée, pas supposée :** dans une trame, « Imprimer » imprime-t-il
la feuille ou l'administration ? Mesuré par les événements `beforeprint` — seule la trame
le reçoit, la fenêtre hôte rien. C'est ce qui autorise à garder la feuille intacte dans son
propre document, et donc à ne pas remettre en jeu les huit tests qui lisent un vrai PDF.

**Un défaut vu seulement à l'écran :** la barre du Journal affichait « 2 événements » puis,
deux centimètres à droite, « 2 événements · 0 ligne technique en mémoire ». Traversé la
conception, l'écriture et 570 tests verts — une redondance est une propriété de la
composition, aucune assertion ne la porte. Corrigé : un seul témoin, qui répond à la seule
question qu'on lui pose (« est-ce à jour ? ») et récupère « hors ligne ».

**Vérifié :** 517 unitaires (+10 gardes structurelles) · 53 e2e (dont 9 nouveaux) · 40 JS ·
ruff propre · trois captures 1440×900 relues. Chaque garde confrontée à une mutation qui la
fait tomber : sélecteur redevenu global → l'e2e du volet Technique tombe ; trame chargée une
seule fois → l'e2e « feuille refaite » tombe ; condition de panneau retirée → l'e2e qui
compte les requêtes tombe ; entrée du menu redevenue un lien → le témoin de non-navigation
tombe.

**Coût assumé :** `admin.html` passe de 640 à ~710 lignes et l'admin charge deux scripts de
plus au démarrage (~21 Ko). En échange, deux documents et leurs deux en-têtes disparaissent.

**Reste à faire — le seul point qui demande Nathan :** juger les trois panneaux à l'œil sur
le boîtier. Les captures disent que rien ne déborde ; elles ne disent pas si ça lui plaît.

---

## Lot « Configurations : le plateau et ses fichiers » — 2026-07-31

**Demande de Nathan :** « déplacer Importer et Exporter directement dans Configurations,
c'est plus logique non ? », puis « sur chaque config enregistrée j'aimerai qu'on puisse
cliquer sur exporter » et « oui, demander confirmation » pour l'import.

**Pourquoi c'est juste :** les trois manipulent le MÊME objet — l'état du plateau. Seule
la destination change : le boîtier (configuration nommée) ou un fichier `.rost`
transportable. La latérale « Données » retombe à trois rangées : Historique,
Configurations, Impression.

### Livré
- [x] **Route `GET /api/configs/<name>/export`** — lecture pure. `/load` était le seul
      autre accès au contenu d'une config, mais il écrase le brouillon ET déconnecte
      l'antenne : y câbler « Exporter » aurait détruit le plan de travail pour un simple
      téléchargement. Pas d'`@exclusive_state` (rien n'est écrit), rien au journal.
- [x] **`Configs.read()` / `Configs.slug()`** — `load()` délègue désormais à `read()`
      (contrat inchangé). Durcissement au passage : un enregistrement sans clé `state`
      lève `KeyError` comme un fichier absent, au lieu de faire remonter un KeyError de
      dictionnaire que le handler n'attrape pas (→ 500).
- [x] **Dialogue élargi** : `[Charger] [Exporter] [Supprimer]` par rangée, et un pied
      « Fichier » séparé par un filet — `[Importer…] [Exporter le plateau]`.
- [x] **`downloadRost(data, nom)`** remplace `exportConfig()` : une seule fabrique de
      fichier pour deux sources — l'écran (brouillon compris) et le disque, relu par
      l'API. Le fichier d'une config porte son nom (`comroster-jour-2.rost`).
- [x] **Confirmation d'import**, après lecture et validation du JSON (le sélecteur de
      fichiers du système s'ouvre en premier ; faire confirmer un fichier illisible
      n'apporterait rien). Le nom du fichier est rappelé dans la question.

### Vérifié
521 unitaires (+4) · 56 e2e (+3) · 40 JS · ruff propre · dialogue rendu et mesuré à
1440×900 (aucun débordement, console vide).

**Trois gardes confrontées à leur mutation**, chacune vue tomber :
confirmation retirée → l'e2e « annuler laisse le plateau intact » tombe ; export de
rangée lisant `state.data` au lieu de l'API → l'assertion de CONTENU tombe (mutation
affinée exprès pour ne pas se contenter du nom de fichier) ; `#export-btn` remis dans la
latérale → la garde structurelle tombe (elle teste l'APPARTENANCE au dialogue, pas la
présence dans la page).

### Trouvé en chemin, hors demande
- **Vestige CSS faux** : `body:has(#import-dialog[open]) #export-btn` surlignait
  « Exporter » quand s'ouvrait le récap d'import des BELTPACKS depuis l'antenne — deux
  choses sans rapport, qui partagent un mot. Supprimé avec le bouton.
- **Collision de noms pytest préexistante** : `tests/test_panneaux.py` et
  `tests/e2e/test_panneaux.py`. Elle interrompait la collecte de la suite ENTIÈRE dès que
  les `__pycache__` étaient nettoyés. E2e renommé `test_panneaux_navigation.py`.
- **`_wait_saved` promue** dans `tests/e2e/helpers.py` (sous le nom `wait_saved`) : tout
  test qui fait relire le brouillon PAR LE SERVEUR doit l'attendre.

### Corrigé ensuite, sur décision de Nathan
« Supprimer » ne se distinguait pas dans la liste : il portait `class="chip-btn danger"`,
mais AUCUNE des deux règles qui utilisent `.danger` ne s'appliquait là — l'une exige
`.dialog-actions` (le pied d'un dialogue), l'autre `.block-actions`. Deux classes
inertes, et un balisage qui faisait croire, à la relecture, que le destructif était
signalé. Trois boutons gris identiques dont un seul détruit.

Le sélecteur est désormais scindé selon ce qu'il porte : l'APPARENCE (couleur, bordure,
survol) s'étend à `.cfg-actions`, le PLACEMENT (`margin-right: auto`, qui repousse le
destructif à l'opposé des boutons de sortie) reste propre au pied — appliqué à une
rangée de liste, il aurait décollé « Supprimer » de ses voisins. `chip-btn`, morte au
même endroit et pour la même raison, est retirée.

Mesuré, pas relu : `getComputedStyle` donne `rgb(240,133,122)` (`--danger`) sur
« Supprimer » et `rgb(238,241,247)` sur ses deux voisins ; les trois restent alignés
(657 / 737 / 821 px). Et le pied du dialogue Historique garde son comportement — marge
résolue à 268 px, destructif collé à gauche, « Fermer » rejeté à droite.

---

## Lot « Ce que l'écran croyait dire » — 2026-08-03

Reprise du seul point technique laissé ouvert au lot du 2026-07-28 (soir) : « `display.js`
référence `#sync-hint` mais l'élément n'existe plus — à trancher : rétablir ou retirer ».

**Tranché : retirer.** L'historique donne la réponse sans avoir à deviner. Le commit
`0156f0d` (2026-07-13, « simplifications display/admin ») retire du pied de l'écran, dans
son propre message, « la partie admin (écrou/adresse) et "mises à jour en direct" ». Les
deux suppressions étaient donc voulues ; c'est le JS qui n'a pas suivi.

**Un second mort trouvé au passage, jamais signalé :** `#admin-hint`, retiré par le MÊME
commit. `loadOnboarding()` continuait d'y écrire « ⚙ Admin : comroster.local » une fois la
box configurée. Deux éléments, cinq écritures, toutes protégées par un `if (el)` qui rendait
la panne parfaitement silencieuse — pendant trois semaines.

- [x] **Le seul message qui portait une information est récupéré.** Sur les cinq, quatre
      doublaient le voyant « En direct » (`setLive` dit déjà « Reconnexion… », « Mise à
      jour »). Le cinquième, lui, n'avait pas d'équivalent : sans `EventSource`, la page
      abandonnait en silence et le voyant restait au vert devant un tableau qui ne serait
      plus jamais mis à jour. `setLive` accepte donc un libellé explicite, et ce cas
      affiche « Temps réel indisponible » avec l'état visuel d'erreur — sans promettre une
      reconnexion qui n'aura pas lieu.
- [x] **Garde structurelle** (`test_display_js_trouve_ce_quil_adresse`) : chaque
      `getElementById` de `display.js` doit exister dans la page `/display` RENDUE. Elle
      existait pour `journal.js` et `health.js` face à `admin.html` depuis la fusion des
      panneaux (leçon 2026-07-30) — l'écran de régie, lui, n'en avait aucune, et c'est
      exactement le trou par lequel ces deux éléments ont survécu.
- [x] **`.person .name` supprimé de `display.css`** : dernier vestige du champ « nom »,
      disparu du modèle bien avant (le README l'affirmait encore à tort en juillet).
      Constat déjà noté au lot des apparences, jamais nettoyé. Vérifié au rendu :
      0 élément `.person .name` dans le document.

**Vérifié :** 522 unitaires (+1) · 55 e2e · 38 JS · ruff propre. Rendu réel à 1920×1080
(6 groupes, 24 beltpacks) : voyant « EN DIRECT » à `data-state=idle`, 24 cartes, console
navigateur vide — collecteur prouvé armé par une sonde, sans quoi l'assertion négative ne
prouverait rien (leçon 2026-07-23).

**Garde confrontée à sa mutation :** réintroduire un `getElementById("sync-hint")` dans
`display.js` fait tomber le test, avec le bon message (`['sync-hint']`), et le fichier est
restauré à l'octet près.

**Relevé au passage :** les cases B1 à B4 du lot du 2026-07-27 (onglet « Écran ») étaient
restées vides alors que tout est livré depuis longtemps. Cochées après vérification dans le
code, pas sur mémoire.
