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

---

# LOT 2026-08-02/03 — Retours d'usage de Nathan (13 points)

⚠️ **Consigné le 2026-08-03, en retard.** Cette liste a été donnée le 2026-08-02 et le
travail a commencé (commits `4a67048` et `6d1d3c6`) SANS être écrite ici. Un `/clear` a
suivi : la session d'après a repris sur un todo.md qui n'en portait pas un mot, et Nathan a
dû redonner la liste. La leçon est déjà écrite ailleurs sous une autre forme (« tant qu'un
humain doit penser à recopier, il oubliera ») ; ici le remède est simple et sans excuse :
**une demande s'écrit dans todo.md AVANT la première ligne de code**, pas après le lot.

Pointage établi dans le CODE, pas d'après les messages de commit.

### Livré (à vérifier une fois à l'écran)
- [x] Double-clic sur le nom d'un groupe pour le renommer (`6d1d3c6`).
- [x] Beltpacks triés par numéro croissant par défaut — Blocs et Disponibles (`6d1d3c6`).
      Tri numérique quand les deux en sont, alphabétique sinon (« A1 », « HF-2 »).
- [x] « Déposer un beltpack » → « **Ajouter** un beltpack ».
- [x] « Non affectés » → « **Disponibles** ».
- [x] « Visa » → « **Signature** » (une case où l'on signe doit le dire).
- [x] Impression : « 1 groupe/page » et « Non affectés » retirés, avec toute leur chaîne ;
      « État publié — ce que la salle voit » → « État publié » ; « Brouillon en
      préparation » → « Brouillon ».
- [x] Configurations : « Exporter le plateau » → « **Exporter** » ; « le tableau actuel »
      → « le **Roster** actuel ».
- [x] Sauvegarde : « boîtier neuf » → « autre ComRoster » ; « Phrase de passe » → « Mot de
      passe » ; « Télécharger la sauvegarde » → « **Générer** la sauvegarde » ; « Examiner
      le contenu » → « **Charger une sauvegarde** ».
- [x] Panneau Écran : sous-titre « PRODUCTION » → « **TEXTE** ».
- [x] « boîtier » → « **ComRoster** » : le produit se nomme lui-même, plus de terme
      intermédiaire à apprendre. **TERMINÉ (2026-08-04).** Les 33 occurrences passées en
      revue : **4 seulement étaient du texte LU par l'utilisateur**, les 29 autres sont des
      commentaires de code (Jinja `{# #}`, CSS, JS). Traitées :
      « Votre boîtier est prêt. » → « Votre **ComRoster** est prêt. » (onboarding écran) ;
      « boîtier surveillé en direct » → « **ComRoster** surveillé en direct » (Santé) ;
      « Les messages techniques du boîtier » → « du **ComRoster** » (état vide du Journal) ;
      et « Redémarrage du boîtier » → « **Redémarrage** » tout court — aucun libellé voisin
      de cette table ne nomme la machine (« Réglages réseau enregistrés », « Antenne
      connectée »), parce que le journal EST celui du ComRoster : le complément n'apprenait
      rien et rompait la série.
      **Les commentaires gardent « boîtier » à dessein** : ils désignent l'appliance
      physique (carte SD, redémarrage, réseau, « un boîtier prêté d'une production à
      l'autre »), et y substituer le nom du produit appauvrirait le sens pour le prochain
      lecteur. C'est la distinction que le lot demandait de trancher au cas par cas.
      Contrôlé par analyse des chaînes littérales, commentaires retirés : 0 occurrence
      visible restante dans `templates/` et `static/`.

### Reste à faire
- [x] **1. Densité de la vue Blocs : 4 colonnes au lieu de 3.** `--card-min` 300 → 232 px,
      valeur MESURÉE : la grille fait 994 px à 1440, mais 24 px de rembourrage et 7 px de
      gouttière par colonne s'en retranchent — 240 px y tenait encore 3 colonnes, à cinq
      pixels près. Résultat : 1280 → 3, 1440 → **4**, 1920 → 6.
      **Défaut de fond trouvé en chemin** : à 237 px les noms de groupe tombaient en
      « M… ». La cause n'était pas la largeur mais `.block-actions` (Renommer/Supprimer),
      qui restait DANS LE FLUX en `opacity: 0` et mangeait ~133 px d'en-tête en
      permanence — la leçon du 2026-07-23 rejouée. Repliée pour de bon (`max-width: 0`),
      elle ne reprend sa place qu'au survol. L'opacité seule est animée : faire glisser
      `max-width` déplaçait les boutons sous le curseur pendant 120 ms (on vise
      « Renommer », on relâche sur « Supprimer ») — c'est ce qui a fait tomber un e2e,
      qui cliquait jusque-là grâce à la place occupée par des boutons invisibles.
- [x] **2. Réordonner les beltpacks à la main dans la vue Blocs.**
      **Règle tranchée par Nathan (2026-08-03) :** tri automatique par numéro **par
      défaut** ; dès qu'on touche à l'ordre d'un groupe, CE groupe passe en **manuel** et
      garde l'ordre posé ; une action **« Trier par n° »** existe **groupe par groupe**
      pour y revenir. Le mode est donc porté par le GROUPE, pas par un réglage global —
      deux groupes peuvent vivre dans deux régimes différents, ce qui est le sens de
      « au choix ».
      **LIVRÉ (2026-08-03).** Un seul champ ajouté, `manual_order` sur le groupe : l'ordre
      lui-même est celui du tableau `people`, seule donnée d'ordre qui existe déjà et qui
      est déjà persistée — aucun champ d'ordre à ajouter, donc aucun à oublier dans un
      chemin d'écriture. `is True` et non `bool()` : une valeur farfelue venue d'un fichier
      importé retombe sur le tri, jamais sur un ordre figé que personne n'a demandé.
      Glisser-déposer interne avec trait d'insertion (sans repère, on dépose à l'aveugle),
      et « Trier par n° » n'apparaît que sur un groupe en manuel.
      **Défaut trouvé en chemin, plus grave que la demande** : le tri par numéro ne vivait
      que dans `admin.js`. L'écran de régie affichait l'ordre BRUT du fichier — deux
      vérités pour un seul plateau, et celle qui compte devant public était la mauvaise.
      La règle est passée dans `board.js`, que les deux pages chargent, et la feuille
      imprimée (troisième lecteur, côté serveur) suit le même régime.
      Une simple affectation depuis la réserve ne bascule PAS le groupe en manuel : ce
      n'est pas « toucher à l'ordre ».
      Vérifié : 526 unitaires · 59 e2e (dont 4 nouveaux — les premiers du dépôt à faire un
      vrai glisser-déposer) · 43 JS · ruff propre. Cinq mutations, une propriété chacune,
      chacune vue tomber.
- [x] **3. « Historique » — CONSERVÉ** (décision de Nathan, 2026-08-03). Ce n'est pas un
      doublon de Configurations : l'un garde AUTOMATIQUEMENT les 50 dernières
      publications, l'autre ne garde que ce qu'on a nommé soi-même. Aucun renommage
      demandé, rien à faire.
- [x] **4. Impression : « Imprimer le brouillon » seulement s'il existe un brouillon**
      distinct du publié (2026-08-03). La comparaison ignore `updated_at` : toute mutation
      ré-horodate le brouillon, y compris celles qui le ramènent à son point de départ.
      **Deux enseignements de la mutation de contrôle**, qui a d'abord PASSÉ (donc ne
      prouvait rien) : (a) `now_iso()` a une granularité d'une seconde, un test qui
      s'exécute en millisecondes réécrit la même valeur — l'horodatage est désormais forcé
      par `monkeypatch`, avec un témoin positif qui vérifie qu'il a réellement bougé ;
      (b) en cherchant pourquoi, un **défaut du lot précédent** est apparu : `add_group`
      posait le groupe à la main, sans `manual_order`, alors que `build_draft` l'ajoute —
      deux formes de groupe selon le chemin de création, dont l'une fabriquait un faux
      écart entre brouillon et publié. Corrigé à la source.
- [ ] **5. Impression : mise en page « plus sympa »** — **DIAGNOSTIC POSÉ SUR PLATEAU
      RÉALISTE (2026-08-05)**, exécution à faire. Rendu en A3 depuis un vrai PDF, sur
      **62 beltpacks / 9 groupes** — le jeu que la leçon n°35 exige, et non l'échantillon
      de 27 qui avait laissé passer le groupe coupé le 2026-07-30.
      **Premier fait mesuré, qui recadre la demande : tout tient sur UNE SEULE page A3**
      (841,92 × 1191,12 pt). Le seuil multi-pages n'est donc pas atteint à 62 beltpacks —
      les défauts de RÉPÉTITION (bandeau, numéro de page) ne se rejugeront qu'au-delà, et
      il faudra fabriquer ce cas exprès plutôt que l'attendre.
      **Ce qui rend la feuille ingrate, par ordre d'importance :**
      1. **~30 % de la hauteur inutilisée.** 62 lignes réparties en 3 colonnes donnent
         ~21 lignes par colonne, là où l'A3 en tient bien plus : le tableau s'arrête aux
         deux tiers et le bas est vide. C'est le vrai sujet « plus sympa » — soit moins de
         colonnes (lignes plus larges, texte plus grand, lisible à distance sur un pupitre),
         soit une typographie qui occupe la page. **Décision produit, à trancher avec
         Nathan** : une feuille de régie se lit souvent à bout de bras.
      2. **La zone de signature ne se voit pas.** Le libellé « SIGNATURE » est là, l'espace
         de 28 mm aussi, mais RIEN n'indique où signer — ni trait, ni case. On a réservé la
         place sans dessiner la cible.
      3. **L'en-tête de colonnes (N° · RÔLE · SIGNATURE) est répété neuf fois**, une fois
         par groupe. Sur un document dense c'est du bruit qui hache la lecture ; il ne se
         justifie qu'en tête de colonne PHYSIQUE, pas en tête de chaque groupe.
      4. **L'effectif du groupe est illisible** — chiffre très clair, rejeté à droite, sans
         rapport visuel avec le nom du groupe qu'il qualifie.
      5. **Le pied redit l'en-tête** (« Affectation Intercom · Publié · édité le … ») alors
         que le bandeau de tête porte déjà les quatre mêmes informations. Sur un document
         d'une page, c'est la redondance de composition de la leçon du 2026-07-30 : décider
         lequel des deux répond à une question qu'on se pose vraiment.
      **⚠️ Contrainte du lot** : huit tests e2e lisent un VRAI PDF et verrouillent le
      papier (format, bandeau répété, réidentification d'un groupe coupé, numéro de page).
      Toute refonte doit les faire évoluer sciemment, jamais les contourner.

      **ARBITRAGES DE NATHAN (2026-08-05), à exécuter :**
      1. **Jusqu'à 4 colonnes** (le sélecteur s'arrête à 3 aujourd'hui).
      2. **40 beltpacks par page au MAXIMUM** — « c'est souvent moins ». Donc une règle de
         pagination par le NOMBRE de lignes, pas par le remplissage naturel des colonnes :
         c'est ce qui répond au bas de page vide, et c'est aussi ce qui fabriquera enfin
         le cas multi-pages que 62 beltpacks n'atteignaient pas.
      3. **Le pied reste** (mon option « le supprimer » est écartée).
      4. **Le troisième titre entre dans l'en-tête.** Défaut de fond confirmé dans le
         code : `print.html` écrit `production_name or title`, un OU exclusif — si le nom
         de production existe, le TITRE disparaît purement et simplement de la feuille.
         Les trois (`production_name`, `title`, `subtitle`) doivent coexister.

      **LIVRÉ (2026-08-05) — les quatre points.**
      - **4 colonnes** : allowlist `printopts.js`, sélecteur `[data-cols="4"]`
        (`column-gap` resserré à 6 mm — à quatre colonnes, 8 mm mangeait la largeur utile)
        et bouton dans la barre. Vérifié au PDF : 4 colonnes, et un groupe coupé se
        réidentifie bien en tête de colonne.
      - **Pagination à 40** : faite CÔTÉ SERVEUR (`_paginer`, api.py), pas en CSS. Deux
        raisons, aucune esthétique — une règle en NOMBRE DE LIGNES ne s'exprime pas en
        hauteur de boîte, et un saut de page dans un conteneur multi-colonnes est mal
        supporté (c'est déjà ce qui imposait la colonne unique à « un groupe par page »).
        Chaque page a son propre conteneur, donc ses propres colonnes.
        Règle en trois cas : le groupe tient dans la place restante → on le pose ; il
        tiendrait entier sur une page neuve → on ouvre une page **plutôt que de le couper
        pour rien** ; il dépasse 40 à lui seul → il est coupé et se réidentifie.
        Le plateau réel (62) donne **2 pages : 36 + 26**.
      - **Pied conservé**, inchangé.
      - **Les trois titres coexistent** : sur-titre `production_name`, `h1` `title`,
        sous-titre `subtitle`. Le repli ne porte plus que sur le titre principal.

      **Vérifié :** 550 unitaires (+10) · 62 e2e · 43 JS · ruff propre. Les huit tests qui
      lisent un vrai PDF passent SANS modification — la pagination ne remet pas en jeu le
      papier qu'ils verrouillent. PDF relu en 3 et en 4 colonnes.
      **Trois mutations, chacune vue tomber** : plafond porté à 60 → la borne exacte
      tombe ; suppression du cas « tiendrait entier ailleurs » → le groupe est coupé pour
      rien ET une page dépasse 40 ; retour au OU exclusif → le test des trois titres tombe.
      Une garde de CONSERVATION a été ajoutée exprès : aucune assertion sur les tailles de
      page ne verrait une pagination qui PERD une ligne — `[40, 40, 15]` reste plausible
      même si trois beltpacks ont disparu en route.

      **Restent ouverts, non demandés** (du diagnostic ci-dessus) : la zone de signature
      qui ne se voit pas (2), l'en-tête de colonnes répété par groupe (3), l'effectif
      illisible (4).

      **NOUVEAUX ARBITRAGES DE NATHAN (2026-08-05, suite) :**
      5. **La fonction Signature est SUPPRIMÉE** — « le design n'est pas bon ». Toute la
         chaîne part : colonne du tableau, réglage `visa` de l'allowlist, sélecteurs CSS,
         case de la barre, et les tests qui l'encodent. Cela règle par le vide le point (2)
         du diagnostic : plus de zone à signer, donc plus de zone invisible à dessiner.
      6. **« On doit pouvoir lire la page de loin. »** C'est le critère de conception, et
         il prime : une conduite de régie se consulte à bout de bras, posée sur un pupitre.
         La colonne libérée par la signature est précisément la place qui manquait pour
         agrandir. À MESURER en points, pas à juger à l'œil.

      **LIVRÉ (2026-08-05) — direction « LE NUMÉRO D'ABORD », choisie par Nathan.**
      - **Signature supprimée de bout en bout** : colonne, réglage `visa` de l'allowlist,
        sélecteurs CSS, case de la barre, et les tests qui l'encodaient (JS et e2e). Cela
        règle par le VIDE le point (2) du diagnostic — plus de zone à signer, donc plus de
        zone invisible à dessiner.
      - **L'en-tête « N° · RÔLE » disparaît** (point 3). Répété une fois par groupe, il
        était lu neuf fois pour n'apprendre qu'une évidence : un nombre est un numéro. Le
        `<thead>` RESTE : il est le seul élément que le navigateur répète en tête de
        colonne, donc le seul moyen de réidentifier un groupe coupé.
      - **Le numéro porte la lisibilité** : 15 pt gras tabulaire, contre 11 pt hérités.
        C'est lui qu'on cherche sur le terrain (« à qui est le 34 ? »). Rôle à 11,5 pt,
        qui hérite des 28 mm rendus par la colonne de signature.
      - **Bandeau de groupe plein**, à l'encre, nom et effectif en blanc (point 4 réglé :
        l'effectif partage enfin le poids du nom qu'il qualifie). **Le fond n'est JAMAIS
        la couleur du groupe** : poser du texte sur une teinte saisie par l'utilisateur ne
        garantit aucun contraste, et la même feuille sortie d'une laser monochrome
        deviendrait illisible. La couleur reste portée par le filet.
      - La reprise d'un groupe coupé porte le MÊME bandeau : sinon la suite ressemblerait
        à un titre d'un autre registre.

      **Vérifié :** 550 unitaires · 62 e2e · 43 JS · ruff propre. PDF relu sur le plateau
      réaliste, avec de VRAIS libellés de métier (« Régisseur général », « Poursuite
      cour ») et non des « Poste 12 » qui ne disent rien de la lisibilité réelle.

      **Deux e2e sont tombés, et ils avaient raison** : `text-transform: uppercase` est
      RÉALISÉ par Chromium dans le PDF, donc `pdftotext` lit « LUMIÈRE » et non
      « Lumière ». Les assertions comparent désormais en casse normalisée — récidive
      exacte de la leçon n°73. Le fond gardé (réidentification d'un groupe coupé) était
      intact ; c'est la MESURE qui était devenue fausse, pas le produit.

      **Un test reformulé plutôt que supprimé** : `test_la_colonne_annonce_le_role_et_non_
      le_nom` gardait l'en-tête qui vient de disparaître. Ce qu'il protège n'est pas
      l'en-tête mais le VOCABULAIRE — la feuille ne doit jamais promettre un « nom »
      qu'elle est incapable d'imprimer (leçon n°32). Il porte donc sur le contenu rendu.

      **DEMANDE SUIVANTE DE NATHAN (2026-08-05) :** « mettre plus en avant les couleurs.
      Rappeler l'interface du soft. Mettre un p'tit logo dans le footer peut-être ? »
      Ceci LÈVE l'objection que j'avais posée deux heures plus tôt (« le fond n'est jamais
      la couleur du groupe, faute de contraste garanti ») — et le produit contient déjà de
      quoi la lever proprement :
      - `ink.js` porte la règle de LUMINANCE (seuil .179) qui choisit l'encre noire ou
        blanche selon la couleur du fond. Elle est partagée par l'écran de régie et
        l'admin depuis le lot B1, précisément pour ne pas exister en deux exemplaires.
        La feuille doit la RÉUTILISER, jamais la réimplémenter en Python.
      - Le nuancier des groupes est borné à **12 teintes calibrées ≥ 4,5:1** (point E2,
        031084b) : le contraste est donc garanti par construction, pas par espoir.
      Réserve à consigner, pas à taire : sur une laser MONOCHROME les aplats deviennent
      des gris. L'encre calculée garde un contraste correct, mais deux teintes de
      luminance voisine deviendront indiscernables entre elles — le NOM du groupe reste
      donc l'information, la couleur reste un renfort.

      **LIVRÉ (2026-08-05).**
      - **Le bandeau de groupe prend l'APLAT de sa couleur**, avec l'encre décidée par
        `inkFor` — la règle de luminance du produit, RÉUTILISÉE et non réécrite : `ink.js`
        est chargé avant le module dans `print.html`, comme il l'est déjà par l'écran et
        par l'admin. Deux implémentations auraient fini par juger différemment, et
        personne ne l'aurait vu (on ne compare jamais les deux supports au même instant).
      - **Sur un bandeau devenu couleur, le filet disparaît** : il annonçait précisément
        la teinte que le bandeau porte désormais en entier.
      - **Repli conservé** : sans JS, ou pour un groupe sans couleur, le bandeau reste à
        l'encre pleine. Il ne retombe jamais en texte noir sur blanc.
      - **Petit logo au pied**, dans le bandeau répété : la variante ENCRE du pack client
        s'il y en a un, sinon le glyphe ComRoster. Le pied nommait déjà la marque, il en
        porte maintenant la forme.

      **Un défaut de MON jeu d'essai, pas du code** : la première feuille est sortie avec
      des bandeaux GRIS. Les groupes de test étaient créés sans couleur, donc le template
      retombait sur son défaut `#555555`. Un jeu d'essai qui n'exerce pas la propriété
      qu'on veut juger ne prouve rien — les couleurs sont désormais prises dans
      `GROUP_PALETTE` (admin.js), et choisies claires ET sombres exprès pour exercer les
      DEUX branches de `inkFor` sur la même page. Vérifié au PDF : « LUMIÈRE » (jaune)
      reçoit une encre noire, « RÉGIE » (rouge) une encre blanche.

      **Vérifié :** 550 unitaires · 62 e2e · 43 JS · ruff propre.

      **DEMANDES SUIVANTES DE NATHAN (2026-08-05) :**
      1. **Retirer « cases »** (réglage `cases` + colonne « Remis »), avec toute sa chaîne.
      2. **Ajouter un mode monochrome / couleur.** Répond directement à la réserve écrite
         plus haut : une laser N&B écrase les teintes voisines. Le choix cesse d'être subi.
      3. **« Je ne vois pas le logo »** — posé à 3,6 mm, il est invisible à l'usage.
      4. **Rapprocher le design de la DA du soft.**
      5. **« Les groupes devraient être alignés, là c'est peu lisible. »** C'est le point
         STRUCTURANT : `column-count` fait COULER les groupes d'une colonne à l'autre, donc
         aucun bandeau ne s'aligne avec son voisin et l'œil ne trouve pas de rangée. Il
         faut passer en GRILLE (`display: grid`), où chaque groupe occupe une cellule.
         **Contrepartie à assumer** : en grille, un groupe ne se coupe plus d'une colonne à
         l'autre, donc les rangées se calent sur le groupe le plus haut et le blanc
         augmente. C'est le prix de l'alignement demandé, et la pagination à 40 le borne.

      **LIVRÉ (2026-08-05/06).**
      - **`column-count` → `display: grid`.** Chaque groupe occupe une cellule, les
        bandeaux d'une même rangée sont alignés. `align-items: start` évite que les
        groupes courts s'étirent à la hauteur du plus haut de leur rangée.
      - **« cases » supprimé** de bout en bout (réglage, colonne « Remis », CSS, tests).
      - **Mode monochrome** (`data-mono`), défaut « couleur ». Il répond à la réserve
        écrite au lot précédent : sur une laser N&B, deux teintes de luminance voisine
        deviennent le même gris — le choix cesse d'être subi.
      - **DA rapprochée du soft** : Outfit (la police d'INTERFACE du produit) sur les
        titres, les bandeaux et les rôles ; Inter conservé sur les NUMÉROS, dont les
        chiffres tabulaires alignent les unités en colonne. Coins arrondis à 3 px.
      - **Logo enfin visible.**

      **Deux défauts trouvés au rendu, qu'aucun test n'aurait vus :**
      - **Le logo était invisible par construction** : `comroster-glyph.svg` est peint en
        `#EEF1F7`, un blanc cassé fait pour le fond SOMBRE de l'écran — donc invisible sur
        du papier blanc. L'agrandir n'y changeait rien. Il est désormais posé en SVG
        INLINE, hérite de `currentColor` et prend l'encre intermédiaire du pied. Même
        procédé que l'écran de démarrage. (`comroster-badge-mono.svg` existe mais est
        peint de la même couleur et n'est utilisé nulle part : ce n'était pas la variante
        encre que son nom laisse croire.)
      - **Le mode monochrome ne faisait rien** à la première tentative : ma règle
        neutralisait `--gel`, or le JS pose cette variable en style INLINE, et une
        propriété personnalisée inline l'emporte sur toute règle de feuille, si spécifique
        soit-elle. La surcharge porte donc sur `background`, jamais posé inline.

      **Réserve assumée** : en grille, une rangée se cale sur son groupe le plus haut
      (« Lumière », 14) et le blanc augmente en bas des colonnes voisines. C'est le prix
      de l'alignement demandé — l'ancien remplissage coulant était plus dense mais
      n'alignait rien.

      **DEMANDE (2026-08-09) :** « depuis le menu impression, un retour à la page
      principale quand on clique sur le logo ComRoster ».
      **Ce n'était pas un manque, c'était un DÉFAUT** : le logo EST déjà un lien
      (`<a class="brand" href="/admin">`, admin.html l.20, titre « Retour aux
      affectations »). Il ne fonctionne pas parce qu'il RECHARGE la page, et que l'onglet
      actif est restauré depuis `localStorage` au chargement (`TAB_KEY`, admin.js l.2731,
      ajouté au lot « A bis » du 2026-07-27 pour qu'un rafraîchissement ne perde pas
      l'onglet). Les deux comportements sont justes séparément ; ensemble, ils font que
      cliquer sur le logo depuis Impression ramène… sur Impression.
      Correctif : le clic bascule sur le panneau du plateau sans recharger. Le `href` est
      CONSERVÉ — clic milieu, ⌘-clic et « ouvrir dans un nouvel onglet » doivent continuer
      de marcher, et le lien reste valide si le JS ne tourne pas.
      **LIVRÉ (2026-08-09).** Test e2e ajouté, avec le témoin qui compte : il vérifie
      d'abord que `comroster.admin.tab` vaut bien « print » AVANT de cliquer — sans cela,
      un simple rechargement suffirait et le test passerait correctif retiré. Confronté à
      sa mutation (clic redevenu simple lien) : il tombe, seul.
      **Trouvé au passage, non demandé** : le pied VISIBLE À L'ÉCRAN (`.sheet-foot`) ne
      portait pas le logo — seul le bandeau d'impression (`.sheet-band`, en `display:none`
      hors impression) l'avait. Le glyphe est désormais défini une seule fois (macro
      Jinja) et employé aux deux endroits.
- [x] **6. Sauvegarde : remise en page** (« pas tout à fait clean »). **LIVRÉ (2026-08-05).**
      Diagnostic fait sur le dialogue RENDU, pas sur le balisage — quatre défauts, dont un
      qu'aucune relecture de code ne montre :
      - **Le sélecteur de fichier était le contrôle NATIF** : bouton blanc système et
        « Choose File / No file chosen » **en anglais**, au milieu d'une interface
        francophone sombre. Ni son bouton ni son texte ne sont stylables ou traduisibles —
        ils suivent la locale du navigateur. Remplacé par un sélecteur maison (bouton
        « Choisir un fichier… » + nom du fichier retenu), l'`input` restant DANS le
        document — masqué à l'œil mais focusable, avec relais du `:focus-visible` sur
        l'étiquette. `display:none` l'aurait sorti de l'ordre de tabulation. Même parti
        que les `<select>` restylés le 2026-07-27 ; `input[type=file]` avait été oublié.
      - **L'aide s'intercalait entre le champ et son bouton** : trois lignes de prose
        coupaient la séquence saisir → valider. Passée APRÈS l'action.
      - **Deux boutons de poids inégal** (« Générer » plein, « Charger » neutre) alors que
        chacun est l'action principale de son bloc. Égalisés. Les LIBELLÉS sont conservés :
        « Générer la sauvegarde » et « Charger une sauvegarde » sont ceux choisis par
        Nathan au lot des 13 retours, on ne les raccourcit pas.
      - **Défaut INTRODUIT par le déplacement de l'aide, vu à l'écran** : `.field` n'a
        aucune marge verticale (admin.css l.815) — c'étaient les marges du paragraphe qui
        espaçaient tout. Une fois déplacé, le bouton collait à son champ. Corrigé à la
        source : `.bk-block` porte son propre rythme (pile en `grid`, `gap`), plutôt que
        des marges recollées élément par élément. Mesuré : 10 px champ→bouton,
        18 px bouton→aide.
      Contrepartie obligatoire du rendu natif remplacé : le nom du fichier choisi est
      désormais affiché par `admin.js` — sans quoi on cliquerait « Charger » sans savoir
      sur quoi. Vérifié au rendu avec un fichier réellement sélectionné
      (`comroster-2026-08-04.rostbak`), pas seulement à vide.
- [x] **7. Panneau Écran : repli automatique du témoin « Affichage en cours »** (2026-08-03).
      Repli CONTEXTUEL : il ne mémorise rien, et l'état d'avant est rendu en quittant
      l'onglet — sinon un simple passage par Écran effacerait en silence une préférence
      posée exprès, et le témoin ne reviendrait jamais. Un panneau n'a pas à décider des
      réglages des autres. Mécanique : `panneau-cache`, symétrique du `panneau-affiche`
      existant — ce qu'un panneau allume en arrivant doit pouvoir s'éteindre en partant,
      plutôt qu'une liste de cas particuliers dans `selectTab`.
- [x] **8. Header : rapprocher les menus du bouton d'envoi** — **LIVRÉ (2026-08-04)**,
      après que la capture de Nathan a montré que ma mesure de juillet répondait à côté.
      **Cause racine, mesurée sur les GLYPHES et non sur les boîtes** : les segments
      étaient bien contigus (0 px entre eux), mais deux d'entre eux portaient une largeur
      figée sur leur pire cas et laissaient leur réserve en vide INTERNE — 69 px dans la
      chip d'état (figée pour « 88 en attente », affichant « À jour », contenu calé à
      gauche) + 48 px dans le bouton (figé pour « Annuler la publication · 5 », contenu
      centré). Soit **117 px de creux** entre le mot d'état et le mot « Publier », que la
      mesure des rectangles ne pouvait pas voir. « On dirait que c'est aligné vers la
      droite » décrivait exactement ça.
      **Deux gestes, aucun déplacement** (la décision de juillet — horloge et état restent
      entre Réseau et Publier — est donc respectée) :
      (1) libellé armé « Annuler la publication · N » → « **Annuler · N** ». C'est lui qui
      fixait la largeur du bouton : 184 → **120 px**. L'alternative (retirer l'état armé du
      calcul) a été écartée — le bouton se serait élargi de 80 px À CHAQUE publication,
      faisant sauter l'action la plus fréquente. Ici rien ne bouge jamais.
      (2) chip d'état `justify-content: flex-end` : la réserve reste nécessaire (sans elle
      les onglets sauteraient à chaque frappe) mais rien n'obligeait à la laisser du côté
      de l'action — elle se réfugie contre le filet de l'horloge, entre deux témoins passifs.
      **Résultat mesuré : creux 117 → 25 px, puis réglé par Nathan en deux passes —
      25 px trop serré, 40 px encore : valeur finale 56 px**, obtenue par une MARGE de
      31 px avant le bouton (et non un padding, qui aurait étendu la zone de survol et de
      clic dans un espace n'appartenant pas au bouton). Le seuil de la garde suit à 70 px,
      jamais calé sur la valeur exacte de la cible : il tomberait au moindre décalage de
      police. Le défaut qu'il attrape valait 117 px, la marge de détection reste large.
      **Nathan, 2026-08-04 : les 487 px entre le fil d'Ariane et les onglets ne le gênent
      pas** — rien à faire de ce côté.
      **Garde ajoutée** (`tests/e2e/test_header_geometrie.py`, 2 tests) : le piège est
      structurel — il suffit d'ajouter un libellé long à `fixWidthToLongest()` pour rouvrir
      le creux sans qu'aucune assertion existante ne bronche. Elle mesure la distance entre
      les GLYPHES. Deux mutations, une propriété chacune, chacune vue tomber : libellé armé
      long → 57 px + 96 px de rab (les deux gardes) ; `flex-end` retiré → 85 px (la garde du
      creux SEULE, celle du bouton reste verte).
      *Reste ouvert, non demandé* : 487 px de vide subsistent entre le fil d'Ariane et les
      onglets (`.admin-tabs { margin-left: auto }`) — c'est le seul vrai vide du bandeau,
      mais Nathan n'a pas dit qu'il le gênait.
- [~] ~~8 (analyse initiale, conservée pour mémoire)~~ — « il y a un vrai vide entre
      lui et le "en direct" ». **MESURÉ à 1440 px (2026-08-03), et la mesure contredit la
      lecture spontanée** : titre `155→229`, onglets `716→1061`, horloge `1061→1133`,
      état `1133→1256`, Publier `1256→1440`. Les quatre derniers sont CONTIGUS — il n'y a
      aucun vide à supprimer entre les onglets et Publier, seulement 195 px d'éléments
      (horloge 72 + état 123). Le seul vrai vide du bandeau est ailleurs : **487 px entre
      le titre et les onglets**. Rapprocher davantage exige donc de RÉDUIRE ou DÉPLACER
      l'horloge et l'état — or déplacer avait été explicitement révoqué par Nathan le
      2026-07-27 (« ils doivent rester entre Réseau et Publier »). **Arbitrage demandé
      avant tout code**, options chiffrées : (a) horloge sans les secondes ≈ −20 px ;
      (b) état réduit à sa pastille, le détail vivant déjà dans la barre d'état ≈ −80 px ;
      (c) horloge + état déplacés à gauche dans le vide de 487 px ≈ −195 px, ce qui
      revient sur la décision de juillet.
- [x] **9. Redesigner la page de login.** **DIAGNOSTIC POSÉ ET MESURÉ (2026-08-04)**,
      exécution à faire — capture relue à 1440×900, valeurs relevées en CSSOM :
      - **Charge `main.css` + `auth.css`.** C'est la cause de tout le reste : la page hérite
        de la feuille globale dont l'admin a été DÉCOUPLÉ en juillet (leçon 2026-07-25 :
        « on ne peut pas énumérer ce qu'on hérite »). Le login est donc le dernier endroit
        du produit resté sur la DA abandonnée.
      - **Voile turquoise toujours actif** : `body::before` =
        `radial-gradient(circle at 50% 0%, rgba(51,214,198,.04), transparent 60%)`. C'est
        le halo diagnostiqué comme signature « projet fait par l'IA » au lot des apparences,
        neutralisé sur `/display` pour toute apparence ≠ basique — jamais ici.
      - **Bouton en pilule turquoise pleine et arrondie**, alors que l'admin a abandonné les
        pilules pour des segments plats et que « Publier » y est en TEXTE sans fond
        (décision de Nathan, 2026-07-23). La page contredit la DA du reste du produit.
      - **Carte 420×428 px = 13,9 % de l'écran**, flottant dans 86 % de vide ; `line-height`
        25,6 px hérité du body global ; deux accents turquoise saturés (contour permanent du
        champ + aplat du bouton) sur une page qui n'a qu'UNE action.
      **Remède retenu (à exécuter) :** découpler comme l'admin — la page ne charge plus que
      sa feuille, reconstruite sur les jetons de l'admin. Verrouiller par un test
      (`assert "main.css" not in html`), sur le modèle de celui qui garde déjà l'admin.
      ⚠️ `login.html` porte TROIS états dans le même template (connexion · réinitialisation ·
      code de récupération affiché) : les trois doivent être capturés, pas seulement le
      premier. Et `setup.html` partage `auth.css` — vérifier qu'il ne casse pas.

---

# LOT 2026-08-04 — La porte d'entrée (point 9 : login + setup)

Exécution du diagnostic ci-dessus. **Direction donnée par Nathan (2026-08-04) :** « d'abord
ambiance face avant puis plein cadre, un truc pro, carré, clean, cool, complet, geek ».
Soit le registre de l'écran de démarrage validé le 2026-07-29 (le voyant d'un appareil de
scène) posé dans une composition plein cadre, et non une carte centrée.

## Périmètre : les DEUX pages, cinq états

Le diagnostic disait « vérifier que `setup.html` ne casse pas ». Vérifié : il casserait.
Les deux templates chargent `main.css` + `auth.css`, et `setup.html` consomme `.field`,
`.btn`, `.primary` — tous définis dans `main.css`. Découpler le login seul le laisserait
donc à la fois cassé ET seul survivant de la DA turquoise abandonnée : deux formes de la
même porte selon le chemin, exactement le défaut que nomment la leçon du 2026-08-03 (deux
constructeurs pour une même entité) et celle du 2026-07-30 (deux documents qui divergent).

Cinq états à rendre, tous à capturer — aucun n'est joignable par une simple URL :
1. connexion (`/admin/login`)
2. réinitialisation (`/admin/recover`)
3. code de récupération après réinitialisation (`login.html` + `recovery_code`)
4. configuration initiale (`/admin/setup`, seulement sur un boîtier vierge)
5. code de récupération après création (`setup.html` + `recovery_code`)

## Structure retenue

- **Bandeau** (filet dessous) : voyant · glyphe (ou logo de marque) · nom · version à droite.
- **Corps** : colonne calée à gauche sur la MÊME gouttière que le bandeau — c'est
  l'alignement qui fait le « carré », pas les bordures.
- **Pied** (filet dessus) : état de liaison en toutes lettres · horloge.

## Le point qui décide de tout : le voyant doit dire vrai

Un disque qui respire sur une page de login est un ornement — et la leçon du 2026-07-28
interdit l'ornement qui ressemble à une mesure (c'est elle qui a fait tomber le filet du
Journal et les faux `[ OK ]` de l'ancien splash). Il ne se justifie que s'il mesure :
sonde `/healthz` périodique, le voyant tombe si le ComRoster ne répond plus. Un poste de
régie laissé sur cette page sait alors que le boîtier est parti.
- Bornée à la visibilité du document (leçon 2026-07-30 : un sondage qui avait le droit de
  tourner dans une page dédiée ne l'a plus quand personne ne regarde).
- `/healthz` renvoie DÉJÀ la version sans session (« fuite assumée — LAN de régie »,
  commentaire de `__init__.py`) : le bandeau n'expose donc rien de neuf.

## Étapes — LIVRÉ (2026-08-04)
- [x] 1. Captures AVANT des cinq états (le diagnostic n'en tenait qu'un).
- [x] 2. `auth.css` reconstruite AUTONOME sur les jetons d'`admin.css`.
- [x] 3. `login.html` + `setup.html` : plein cadre, `main.css` retiré des deux.
- [x] 4. `static/js/auth.js` — sonde et horloge, servi depuis `self` (CSP stricte).
- [x] 5. Gardes : découplage sur les cinq états, structurelle script ⇄ page, jetons CSS.
- [x] 6. Captures APRÈS, console vide, contrastes et géométrie mesurés, mutations passées.

### Une décision de structure, pas de style : le cadre est écrit UNE fois
`templates/auth_base.html` porte le bandeau, le pied et le voyant ; les deux pages n'ont
plus que leur contenu. Les dupliquer aurait reconduit le défaut que ce dépôt paie depuis
juillet — deux documents qui divergent (fusion des panneaux, 2026-07-30) et deux
constructeurs pour une même entité (`add_group` sans `manual_order`, 2026-08-03).
Conséquence sur l'outillage : la garde `script ⇄ page rendue` ne voyait pas l'héritage
Jinja. Un cadre commun aurait été un angle mort parfait — il porte le script, ses enfants
sont les seuls servis, et aucun des trois n'entrait dans la garde. Elle suit désormais
`{% extends %}` et exclut les cadres, qui n'ont pas de route propre.

### Trois défauts trouvés en REGARDANT, qu'aucun test n'aurait vus
- **Le code de récupération se coupait en deux** — « LCJQ-6JYS-Z393-S » puis « 8ZH ».
  `word-break: break-all` dans une carte de 420 px. C'est le seul texte du produit qu'un
  humain doit RECOPIER à la main, et un code recopié faux, c'est un boîtier qu'on ne
  rouvre plus. Il tient maintenant sur une ligne, sans exception (la boîte défile plutôt
  que le code ne se coupe), et une garde lit la règle dans la feuille.
- **`Courier New`** pour ce même code, dans un produit qui auto-héberge Inter et Outfit
  précisément pour ne dépendre d'aucune fonte du système.
- **Un émoji ⚠️ en couleur** posé en `::before`, qui rend selon la fonte d'emoji de la
  machine, dans une DA par ailleurs monochrome.

### Le voyant dit vrai, sinon il n'existerait pas
Un disque qui respire dans un bandeau est un ornement, et la leçon du 2026-07-28 interdit
l'ornement qui ressemble à une mesure (c'est elle qui a retiré le filet du Journal et les
faux « [ OK ] » de l'ancien splash). Il sonde donc `/healthz` toutes les 10 s, borné à la
visibilité du document (leçon 2026-07-30). Ce qu'il dit exactement : « le ComRoster répond
MAINTENANT » — trivial au chargement, utile ensuite, quand un poste laissé sur cette page
voit le voyant tomber au lieu d'afficher un formulaire mort d'apparence normale.
`/healthz` servant déjà la version sans session, le bandeau n'expose rien de neuf.

### Mesuré, pas jugé (1440×900)
Pire contraste **4,92:1** (seuil AA 4,5) sur les huit textes de la page. Les trois
gouttières — bandeau, colonne, pied — à **44 px exactement** : c'est cet alignement qui
fait le « carré » demandé, pas des bordures. Bandeau à 53 px, le même jeton `--top-h` que
l'admin. Débord horizontal **0**. Console navigateur vide, collecteur prouvé armé par une
sonde (sans quoi l'assertion négative ne prouverait rien).

### Gardes confrontées à leur mutation, chacune vue tomber
`main.css` réintroduit dans le cadre → les 5 tests de découplage tombent ; `nowrap`
remplacé par `break-all` → la garde du code tombe ; la découverte des porteurs privée de
l'héritage → la garde structurelle tombe (elle avait d'ailleurs signalé `auth_base.html`
d'elle-même, avant que je ne l'aie déclarée). Le témoin positif
`test_les_cinq_etats_sont_bien_atteints` existe parce qu'une page d'erreur ou une
redirection ne contient pas non plus `main.css` : sans lui, les cinq assertions négatives
passeraient sur des états jamais atteints.

### Défaut de MON exécution, corrigé et consigné
`git checkout <fichier>` employé pour annuler une mutation de contrôle sur deux fichiers
NON commités : il ne rend pas l'état d'avant la mutation, il rend HEAD — le travail du lot
a été effacé sur `auth.css` et `test_pages_et_scripts.py`, sans le moindre avertissement.
Reconstruits à l'identique (mesures rejouées : mêmes valeurs au pixel et au centième),
encodage et alphabet contrôlés. Leçon écrite.

### Deux incidents de harnais, tous deux de mon fait
- **Renommage de classe non tracé.** `auth-submit` → `auth-go` sans chercher ses porteurs :
  huit fichiers e2e cliquent `a.auth-submit` pour se connecter, tous ont expiré. Corrigé
  dans les huit. **Dette NON résorbée, signalée** : ces huit fichiers dupliquent chacun
  leur fonction de connexion, donc un renommage coûte huit corrections au lieu d'une —
  c'est le motif que la leçon du 2026-07-31 condamne, ici au huitième besoin. La
  factoriser dans `helpers.py` touche toute la suite e2e : c'est un lot à part.
- **Deux suites e2e concurrentes** : 59 échecs en 27 min. Relancée seule, la même suite
  donne **62 verts en 101 s**. Le code n'était pas en cause.

### Vérifié
**540 unitaires · 62 e2e · 43 JS · ruff propre.**

### Reste à faire — le seul point qui demande Nathan
Juger les cinq états à l'œil. Les mesures disent que rien ne déborde et que tout est
lisible ; elles ne disent pas si la composition lui plaît. Deux réglages sont des valeurs
d'ambiance, faciles à bouger : la gouttière (44 px) et la largeur de colonne (372 px).

---

## État au 2026-08-09 — `main` à jour, CI verte

18 commits poussés (le distant était resté au 2026-08-02 : les lots des jours
précédents n'avaient jamais été envoyés non plus).

### ✅ Dette n°1 — TROIS tests instables, CORRIGÉS (2026-08-09)
Cause racine commune aux deux e2e : `fill("#person-beltpack")` sans attendre
`#person-dialog[open]` — sur un runner lent, la saisie part avant l'ouverture de la
boîte et le formulaire est soumis incomplet. Motif répété à DOUZE endroits, dans six
fichiers ; l'attente est posée partout, plus l'attente du RÔLE après soumission (le
symptôme exact vu en CI). Le troisième, `test_l_archive_est_chiffree`, cherchait
« Son » — trois caractères — dans du base64 : ~0,4 % de faux positif MESURÉ. Marqueur
allongé, et garde posée dans le test pour qu'on n'en réintroduise pas un court.
Éprouvés par RÉPÉTITION (3 passes), une exécution verte ne prouvant rien.

### (historique) ### ⚠️ Dette ouverte n°1 — DEUX e2e INSTABLES (à traiter en priorité)
La CI est tombée sur `main` puis est passée AU RE-RUN, sans une ligne de code changée.
Ce ne sont donc pas des régressions, mais des tests instables :
- `test_exporter_le_plateau_courant_depuis_le_pied` : `assert 'Régie' in ['']` — le
  beltpack existe mais son RÔLE est vide. La saisie du formulaire n'a pas abouti avant
  la suite du test, alors que `wait_saved` est bien appelé : l'attente porte sur
  l'enregistrement du brouillon, pas sur la prise en compte du champ.
- `test_les_membres_sont_tries_par_numero_sans_intervention` : expiration en attendant
  le beltpack « 30 » — création de 30 beltpacks trop lente pour le runner.
Les deux passent systématiquement en local (63/63) et n'échouent que sur le runner, plus
lent. **Pourquoi il faut les corriger et non les tolérer** : un test qui échoue au hasard
finit par être ignoré, et le jour où il signale un VRAI défaut, personne ne le croit.

### ✅ Dette n°2 — helper de connexion e2e, RÉSORBÉE (2026-08-09)
`enter_admin` et `ajouter_beltpack` vivent dans `helpers.py`. Les sept copies locales de
`_enter_admin` (identiques à l'octet près) sont supprimées, et les deux helpers locaux de
saisie délèguent désormais au geste commun — les attentes qui réparent les flakys
(ouverture du dialogue, rendu du numéro PUIS du rôle) sont ainsi écrites une seule fois.

**Fausse manœuvre au passage, consignée** : mon premier script de suppression employait
`re.S`, qui fait matcher `.` à travers les lignes — 1479 lignes effacées dans sept
fichiers, sans la moindre erreur. Restauré par `git checkout` : sûr ICI parce que tout
était commité et poussé, à la différence de l'incident du 2026-08-04. Refait en
raisonnant par LIGNES, et contrôlé par une grandeur invariante (`--collect-only` rend
toujours 63 tests) plutôt qu'en relisant un diff énorme.

### (historique) ### Dette ouverte n°2 — le helper de connexion e2e, dupliqué huit fois
Huit fichiers portent leur propre `_enter_admin`. C'est ce qui a fait qu'un simple
renommage de classe (`auth-submit` → `auth-go`) a coûté huit corrections au lieu d'une.
`helpers.py` existe déjà et porte `open_reglages` / `wait_saved` : la place est prête.

### À juger par Nathan, à l'œil (aucun test ne le fera)
- Les cinq états de connexion.
- Le dialogue Sauvegarde.
- La feuille imprimée : couleurs, alignement, monochrome, et le BLANC en bas de rangée
  (prix assumé de l'alignement — une rangée se cale sur son groupe le plus haut).

---

## Reste à faire au 2026-08-09 (après six lots livrés et poussés)

### 1. Ce qui n'appartient qu'à Nathan — REGARDER
Aucun test ne le fera. Les mesures disent que rien ne déborde et que tout est lisible ;
elles ne disent pas si c'est bien.
- les cinq états de connexion ;
- le dialogue Sauvegarde ;
- la feuille imprimée, et surtout le **blanc en bas de rangée** : une rangée se cale sur
  son groupe le plus haut. C'est le prix de l'alignement demandé — si ça gêne à l'usage,
  l'arbitrage alignement / densité est à rouvrir.

### 2. Impression — points du diagnostic NON tranchés
Le lot a répondu aux arbitrages donnés, mais le diagnostic initial listait aussi :
- le pied qui redit l'en-tête (sur un document d'une page, c'est une redondance de
  composition) — Nathan a demandé de GARDER le pied, sans dire s'il fallait l'alléger.

### 3. Dette technique connue, non traitée
- ~~`tests/e2e/test_e2e.py` fait 600+ lignes et mélange des sujets sans rapport.~~ →
  **découpé par `fbae2cb`** (« un fichier par sujet, au lieu d'un fourre-tout de
  627 lignes »). Le fichier n'existe plus ; le plus gros e2e fait 303 lignes.
- ~~Le helper de connexion e2e, dupliqué huit fois~~ → **zéro occurrence de `_enter_admin`**
  aujourd'hui : `tests/e2e/helpers.py` porte `enter_admin` et sept autres helpers.
- ~~La course sur le champ rôle est CONTOURNÉE côté test. Le correctif de fond serait côté
  `admin.js` : ne pas écraser une saisie de l'utilisateur.~~ → **réglé, relevé dans le code
  le 2026-08-20.** Les trois pièces sont en place :
  - `admin.js` l. 1291 — `if (el.personRole.value && !roleAutofilled) return;` : une saisie
    manuelle n'est jamais écrasée. C'est exactement le correctif de fond réclamé ici.
  - `admin.js` l. 1269 — `roleAutofilled` remis à `false` à CHAQUE ouverture du dialogue.
    Sans cette ligne, un `true` hérité d'une ouverture précédente ferait écraser le rôle
    d'un beltpack qu'on vient rouvrir pour l'éditer.
  - `helpers.py` l. 88-93 — le contournement (reposer la valeur effacée) a été RETIRÉ le
    2026-08-09 ; l'assertion qui vérifie le rôle avant soumission reste et tomberait si le
    défaut revenait.
  Ce qui subsiste n'est pas un défaut mais le parti pris documenté l. 1284-1288 : la
  proposition reste VIVANTE tant que le champ rôle n'a pas été touché à la main — taper
  « 2 » propose le rôle du 2, continuer en « 22 » doit re-proposer ou vider.

### 4. Jamais demandé, jamais fait
- Captures dans la documentation (étape 7 du lot des apparences). **Toujours ouvert.**
- ~~Cahier des charges (D1) non retouché depuis l'origine.~~ → **réécrit par `79f6a64`**
  (« le cahier des charges décrit enfin le logiciel qui existe »), et gardé depuis par
  `tests/test_cahier_des_charges.py`.

---

## LOT 2026-08-09 — Le focus différé du dialogue « beltpack »

**Demande de Nathan : « fais le champ rôle ».** Le contournement posé côté test le
2026-08-09 traitait le symptôme ; voici la cause, côté PRODUIT.

`openPersonDialog` finit par `requestAnimationFrame(() => el.personBeltpack.focus())`.
Le focus est donc posé APRÈS l'ouverture, à la frame suivante. Entre les deux,
l'utilisateur a le temps de cliquer ou de tabuler vers le champ rôle : le rAF lui VOLE
alors le focus, et ce qu'il tape ensuite part dans le champ numéro.

**Ce n'est pas qu'un problème de test.** À l'usage : ouvrir « Ajouter un beltpack »,
aller vite au rôle, taper — la saisie atterrit dans le mauvais champ. C'est le même
mécanisme qui sortait « BP 42 — » en CI.

**Correctif :** le focus initial est une COMMODITÉ, pas une règle — il ne doit s'appliquer
que si personne n'a encore pris la main. On ne le pose donc que si le focus est encore
sur le dialogue lui-même.

**Le contournement de test est retiré** (le double remplissage du champ rôle) : le garder
masquerait une régression future de ce correctif. La VÉRIFICATION de la valeur avant
soumission, elle, reste — elle dit clairement ce qui ne va pas si le défaut revient.

**LIVRÉ (2026-08-09).** Le focus n'est plus posé que si personne n'a pris la main.
Contournement de test retiré (helper + cinq sites) ; la vérification de la valeur avant
soumission reste, elle dira clairement ce qui ne va pas si le défaut revient.
Vérifié : 550 unitaires · 64 e2e (deux passes identiques) · 43 JS · ruff propre.
**Le premier test écrit ne prouvait rien** — il passait aussi avec le défaut réintroduit,
`wait_for_selector` durant bien plus qu'une frame. Refait en RETENANT le
`requestAnimationFrame` (mis en file par `add_init_script`, libéré après la saisie), avec
un témoin positif que la file n'est pas vide. Confronté à sa mutation : il tombe.

---

# 👉 POINT D'ENTRÉE — état au 2026-08-09 (fin de session)

**Rien n'est en cours, rien n'est cassé.** `main` à jour, CI VERTE, arbre propre.
Dernier commit : `c772677`. Suite : **550 unitaires · 64 e2e · 43 JS · ruff propre**.

Sept lots livrés dans la session : connexion (login+setup), sauvegarde, retour au
plateau depuis le logo, pagination A3, refonte de la feuille imprimée, couleurs +
monochrome, focus du dialogue beltpack. Plus trois tests instables corrigés et la
factorisation des helpers e2e.

## ✅ Verdict de Nathan (2026-08-09, après relecture des rendus) — RIEN À REPRENDRE

Verbatim : « 1 tout est okay tel quel 2 okay aussi ». Les deux points qui n'appartenaient
qu'à son œil sont donc **validés tels quels** :
- le **blanc en bas de rangée** de la feuille imprimée : okay tel quel. L'arbitrage
  alignement / densité est **TRANCHÉ EN FAVEUR DE L'ALIGNEMENT** — ne pas le rouvrir de
  sa propre initiative : le blanc est un prix accepté, pas un défaut en attente.
- le **dialogue Sauvegarde** : okay aussi.
- le **pied de la feuille** qui redit l'en-tête : couvert par « tout est okay tel quel »,
  et cohérent avec sa demande antérieure de le GARDER. On n'y touche pas. S'il y revient,
  ce sera une demande neuve, pas une dette.

## Ce qui reste, par ordre

1. ~~**Dette assumée** : `tests/e2e/test_e2e.py` fait 600+ lignes et mélange des sujets
   sans rapport.~~ **RÉSORBÉE le 2026-08-09** — voir le lot « Découper test_e2e.py »
   plus bas.
2. ~~**Jamais demandé, jamais fait** : captures dans la documentation~~ **FAIT le
   2026-08-11** (voir le lot plus bas). ~~Reste de ce point : le cahier des charges~~
   **FAIT le 2026-08-11 également** : il vit à la racine (`comroster-cahier-des-charges.md`),
   il est à jour, et cinq gardes le tiennent désormais.

**Il ne reste rien de listé.** Les points ouverts sont ceux que l'usage fera remonter.

---

# LOT 2026-08-11 (c) — Le cahier des charges remis à jour

**Demande de Nathan, verbatim : « go cahier des charges ».** Dernier point du reste à
faire. Le document vit à la racine : `comroster-cahier-des-charges.md`, écrit le
2026-06-19 et **jamais retouché depuis** — deux mois.

## Ce qu'il affirmait de faux (vérifié, pas supposé)

- le champ **`nom`** dans le modèle : retiré depuis, en régie on cherche une fonction ;
- **8 caractères** de mot de passe minimum : c'est **4** depuis le 2026-07-06 ;
- **SortableJS** comme brique de glisser-déposer : jamais installé, c'est du HTML5 natif ;
- **six routes** cartographiées : le produit en sert **soixante-trois** ;
- **« last-write-wins, pas de verrou »** : invalidé par la sérialisation du cycle
  lire-modifier-écrire ;
- **Python 3.7+** : c'est 3.12 ;
- dix modules livrés depuis n'y figuraient pas du tout (apparences, impression,
  sauvegarde chiffrée, configurations nommées, journal, contrôle avant show, antenne
  Bolero, réseau, marque blanche, kiosk, version visible).

## Ce qui est livré

Document réécrit. Les sections dont l'intention tient encore sont marquées **§ d'origine**
et conservées telles quelles ; le reste décrit ce qui EXISTE. Les décisions corrigées le
disent explicitement plutôt que d'effacer la trace — pourquoi le champ `nom` est parti,
pourquoi 4 et non 8, pourquoi le verrou a remplacé le last-write-wins.

**Cinq gardes** (`tests/test_cahier_des_charges.py`) confrontent les CHIFFRES du document
au code : routes contre `app.url_map`, minimum de mot de passe contre la constante,
nombre de services contre le paquet, taille de la palette contre `GROUP_PALETTE`, forme
d'un beltpack contre le normaliseur. Le coût est assumé : ajouter une route obligera à
corriger un nombre ici. C'est le but — un document qu'on n'a jamais à toucher est un
document qui ment déjà.

**La garde a attrapé ma propre erreur à son premier lancement** : j'avais écrit
« vingt-deux services » pour une liste qui en comptait vingt-trois. Meilleure preuve
qu'elle mord qu'une mutation. Celle des routes a quand même été éprouvée à part (63 → 61
dans le texte : elle tombe en nommant l'écart).

**Vérifié : 558 unitaires · ruff propre.**

---

# LOT 2026-08-11 (b) — Le bandeau de l'apparence `lineaire`

**Demande de Nathan, verbatim** : « Effectivement le pictogramme n'est pas bon.
Effectivement fais le même ordre que dans "grille". »

Deux décisions, prises après qu'il a vu la capture produite par le lot précédent.

## Cause racine — une seule, deux symptômes

`lineaire` passe `.header-actions` en `align-items: stretch` (skins.css:174) pour que
chaque zone du bandeau porte son filet vertical pleine hauteur. La pastille et l'horloge
se re-centrent alors chacune pour leur compte (`display:flex; align-items:center`) et
reçoivent un `order` explicite (1 et 2). **Le logo n'a reçu ni l'un ni l'autre** :

- sans `order`, il garde la valeur par défaut **0** et passe DEVANT ses deux frères ;
- sans re-centrage, `stretch` retombe sur le début de l'axe pour un élément de hauteur
  définie (`height: 1.85rem`) — il reste donc collé en haut.

Le commentaire de skins.css:178 décrit l'intention d'origine (« En direct avant l'heure,
l'heure finit la barre »). Nathan tranche en sens inverse : **l'ordre de `grille`**, qui
est simplement l'ordre du DOM — horloge, pastille, logo. Les deux `order` sautent donc,
et le commentaire avec eux : le garder en ferait une affirmation fausse.

## À ne pas oublier

`docs/img/ecran-lineaire.png` montre le défaut : la capture doit être RÉGÉNÉRÉE dans le
même commit, sinon la documentation contredit le produit.

## LIVRÉ (2026-08-11)

Les deux `order` sont retirés, le logo reçoit la même forme de cellule que ses voisines
(`align-self: stretch; height: auto`), et le commentaire qui revendiquait l'ancien ordre
est remplacé — le garder en aurait fait une affirmation fausse.

**Mesuré, pas jugé** (1920×1080, les trois apparences) : ordre visuel identique partout,
`board-clock → status-badge → brand-mark`. Le logo occupe désormais 0→63 px dans un
bandeau de 64, écart au centre **−0,5 px** — exactement celui de ses deux voisines, donc
son filet vertical court de haut en bas comme les leurs.

**Garde ajoutée** : `test_le_bandeau_est_range_pareil_dans_les_trois_apparences`,
paramétré sur les trois apparences. Il mesure l'ordre VISUEL (trié par abscisse) et non
celui du DOM — sans quoi il passerait quels que soient les `order`, c'est-à-dire
précisément ce qu'il surveille. L'ordre attendu est une constante écrite en clair, pas
une comparaison croisée entre apparences : celle-ci passerait au vert le jour où les
trois dérivent ensemble.

**Chaque garde vue tomber, une propriété à la fois** (leçon n°83) : `order: 1` rendu à la
pastille → l'ordre tombe sur `board-clock, brand-mark, status-badge` ; l'étirement retiré
au logo → le centrage tombe à **−17,2 px**. Dans les deux cas, seule `lineaire` échoue,
`basique` et `grille` restent vertes.

**Capture régénérée**, et seulement celle-là : les trois autres ont été restaurées depuis
l'index, l'heure affichée étant leur seule différence. Le diff ne porte donc que sur ce
qui a réellement changé.

**Vérifié : 553 unitaires · 67 e2e · 43 JS · ruff propre.**

### Au passage, un point qui inquiétait Nathan et qui n'est pas un défaut
Les compteurs « 6 groupes · 26 beltpacks » absents de `lineaire` et de `grille` sont
**délibérés** : `skins.css:92` masque `.stats-container` hors `basique`, chaque groupe
portant déjà son propre décompte.

---

# LOT 2026-08-11 — Les captures de la documentation

**Demande de Nathan : « OK GO »**, périmètre choisi « les captures dans la doc ».
Étape 7 du lot des apparences, restée en suspens depuis juillet.

## Ce qui est livré

Quatre captures dans `docs/img/`, insérées là où le README décrivait en MOTS ce qui se
regarde : les trois apparences de l'écran de régie sous le tableau qui les compare, et
l'écran d'administration sous « Premier démarrage ». Chaque image apparaît **une seule
fois** — un README qui montre deux fois la même chose a le même défaut que l'interface
qu'il documente.

**Un générateur commité**, `tools/captures.py`, plutôt que des PNG déposés à la main :
une capture qu'on ne sait pas refaire se périme en silence, et c'est précisément ce qui
est arrivé au texte de ce README (leçon n°32). Trois partis pris y sont défendus en
commentaire — résolution réelle (1920×1080, celle du kiosk), jeu de données
représentatif (6 groupes, 26 beltpacks, teintes claires ET sombres pour exercer les deux
sorties de la règle d'encre), souris écartée avant chaque prise (sinon on photographie
un `:hover`, leçon n°90).

**Trois gardes** (`tests/test_readme_images.py`) : toute image référencée existe, aucune
n'est vide, et aucune capture de `docs/img` n'est orpheline. Cette dernière moitié compte
autant que la première — sans elle, supprimer une section laisse son image derrière, et
plus personne n'ose y toucher. Éprouvées par mutation ciblée : une capture vidée ne fait
tomber QU'UNE des trois (leçon n°83).

`.captures-tmp/` est au `.gitignore` — le script le nettoie, mais s'il tombe en route il
laisserait un état complet à la racine, `admin_secret.json` compris. Règle vérifiée par
`git check-ignore`, pas par relecture.

**Vérifié : 553 unitaires · ruff propre.**

## Deux défauts que SEULE la capture a montrés

1. **Mon jeu d'essai** donnait la même valeur au titre et au nom de production : le
   bandeau affichait « CARMEN » à gauche et « Carmen » au centre. Corrigé (le titre est
   devenu la salle). Aucun test ne pouvait le voir — les deux champs étaient justes.
2. **Le produit, sur l'apparence `lineaire`** : le pictogramme et la pastille « EN
   DIRECT » ne sont pas alignés sur l'horloge, et une surface plus claire les entoure —
   ce que `basique` ne fait pas. **NON CORRIGÉ, non mesuré**, hors du périmètre donné.
   À trancher par Nathan : soit c'est le parti pris de l'apparence, soit c'est un défaut
   d'alignement, et dans ce cas la métrique honnête est la position des GLYPHES, pas
   celle des boîtes (leçon n°88).

---

# LOT 2026-08-09 (b) — Découper `tests/e2e/test_e2e.py`

**Demande de Nathan, verbatim : « reglons le pb du 2E2 ».** Il s'agit du point 1 du reste
à faire : 627 lignes, 20 tests, 8 helpers locaux, des sujets sans rapport dans un seul
fichier. (J'avais d'abord annoncé « 21 tests », à Nathan et ici : c'était un comptage à
l'œil, démenti par la comparaison automatique des noms en fin de lot. La leçon vaut
au-delà de l'anecdote — un chiffre relevé à la main n'est pas une mesure.)

## Ce que le fichier contient réellement (relevé, pas supposé)

| Helper local | Utilisé par | Destination |
|---|---|---|
| `_open_screen_tab` | 5 tests **de trois futurs fichiers** + déjà réinventé en dur dans `test_audit_features.py:63` | **`helpers.py`**, rendu public sous `open_screen_tab` |
| `_NUMBER_ROLE_OFFSET`, `_publish_one_group` | les 4 tests d'apparence | avec eux |
| `_ANIM_RECORDER`, `_open_display_recording`, `_add_group_and_publish` | les 3 tests de transition | avec eux |
| `_wait_frame` | le seul test d'aperçu | avec lui |
| `_seed_table` | les 3 tests de sélection | avec eux |

## Découpage retenu — par SUJET, 20 tests répartis en 8 fichiers

1. `test_parcours_complet.py` (1) — setup → publication → écran. Le parcours nominal.
2. `test_apparences.py` (4) — `basique` / `lineaire` / `grille`, bornes d'ajustement, encre.
3. `test_transitions_affichage.py` (3) — arrivée, mode performance, `snapshot` n'anime pas.
4. `test_apercu_temoin.py` (1) — le témoin suit le publié et n'ouvre aucun flux SSE.
5. `test_selection_tableau.py` (3) — MAJ+clic, réaffectation en lot, ⌘A et le filtre.
6. `test_annuler_refaire.py` (2) — portée de ⌘Z, et sa réserve dans les champs de saisie.
7. `test_admin_dialogues.py` (4) — filtre réserve, indicateurs, réseau, antenne.
8. `test_ecran_autonome.py` (2) — box neuve (onboarding + QR), Screen Wake Lock. Les deux
   seuls tests qui ne passent JAMAIS par l'admin.

## Garde-fous, tirés des leçons — chacun est une étape, pas une intention

- **Collision de noms** (leçon n°80) : `tests/e2e` n'est pas un package, un nom de fichier
  de test est un identifiant GLOBAL. Les 8 noms ont été confrontés aux 47 fichiers de
  `tests/` et aux 10 de `tests/e2e/` : **aucune collision**. À revérifier après création.
- **Pas de `re.S`** (leçon n°102) : le déplacement se fait par LIGNES, jamais par une
  expression régulière multi-lignes. 1479 lignes avaient été effacées ainsi.
- **Sauvegarde hors git** (leçon n°89) : `git checkout` ne rend pas l'état d'avant, il rend
  HEAD. Copie du fichier dans le scratchpad AVANT de commencer, et travail commité d'abord.
- **Invariant de contrôle** (leçon n°102) : `--collect-only` doit rendre **exactement 64**
  tests e2e avant ET après. C'est la grandeur qui prouve qu'aucun test n'a été perdu —
  relire un diff de 627 lignes ne le prouve pas.
- **Jamais deux suites en parallèle** (leçon n°92) : 59 faux échecs. Vérifier `ps` avant.
- **Lire `N passed`, pas le code retour** (leçons n°73 et 92) : `pytest tests/e2e` sans
  `-m e2e` répond « 64 deselected » ET code 0. Ce n'est pas un succès.

## Ce que ce lot ne fait PAS

Aucun test n'est réécrit, renommé, ajouté ni supprimé : c'est un déplacement. Toute
tentation d'« améliorer un test au passage » rendrait l'invariant de comptage aveugle au
seul risque réel — en perdre un en chemin.

## LIVRÉ (2026-08-09)

`tests/e2e/test_e2e.py` n'existe plus. Ses 20 tests vivent dans les huit fichiers prévus,
déplacés sans une modification de corps. Deux helpers sont montés dans `helpers.py` :
`open_screen_tab` (ses appelants se répartissaient sur trois fichiers, et
`test_audit_features` réinventait le même clic en dur — il l'appelle désormais) et
`open_board_tab`, son retour, qui était recopié à quatre endroits.

**Vérifié : 550 unitaires · 64 e2e (DEUX passes, 103 s et 104 s) · 43 JS · ruff propre.**

### Ce que les contrôles ont réellement prouvé
- Le comptage (64 avant, 64 après) dit qu'il y a le bon NOMBRE de tests, pas que ce sont
  les mêmes. La comparaison des NOMS (`def test_*` de la sauvegarde contre ceux des huit
  fichiers, triés puis diffés) le dit : aucune différence. C'est elle qui a démenti mon
  « 21 tests » annoncé à l'œil.
- `__pycache__` purgé avant la collecte : un cache périmé masque exactement les défauts
  d'import, ceux qui bloquent toute la suite (leçon n°80).
- Aucune collision de basename : `tests/e2e` n'est pas un package, un nom de fichier de
  test y est un identifiant GLOBAL.
- Contrôle d'alphabet sur les 750 lignes ajoutées : 23 caractères non-ASCII, tous
  légitimes (`°`, `→`, `↵`, `⇧`, `≈`, `⌘` et les accents). Aucun homoglyphe.

### Deux faux signaux de MON exécution, à ne pas rejouer
- `grep -P` n'existe pas sur le grep BSD de macOS : mon premier contrôle d'alphabet a
  rendu une sortie VIDE, que j'ai failli lire comme « rien à signaler ». Refait par un
  script du scratchpad (leçon n°52).
- Le hook rtk a rejeté un `find ... -exec` (« compound predicates ») et mon `echo` de
  confort affichait quand même « aucun doublon ». Conclusion tirée d'une commande en
  ERREUR — récidive exacte de la leçon n°49. Refait par `rtk proxy find`.

---

## Trois pièges de cette session, à ne pas rejouer
- `git checkout <fichier>` sur du travail NON commité rend HEAD et efface tout en silence.
- `re.S` dans un motif de SUPPRESSION rend le point gourmand à travers les lignes
  (1479 lignes effacées d'un coup, sans erreur). Raisonner en lignes.
- Ne jamais lancer deux suites e2e en parallèle : 59 faux échecs.

## Dette d'accessibilité relevée le 2026-08-13 (revue finale du thème jour/nuit de l'admin)

Deux boutons rouges portent un texte sous le seuil AA de 4,5:1. Préexistants au thème clair,
non aggravés par lui, hors du périmètre de cette branche — mais réels et mesurés :

- `.confirm-danger` (`admin.css`) : blanc sur `--error` = **3,60:1** en nuit (5,44:1 en jour).
- `.selection-bar .danger-btn` (`admin.css`) : `--fg` sur `--error` = **3,18:1** en nuit,
  3,29:1 en jour. Celui-ci échappe à toute garde, sa couleur passant par un jeton.

Corriger les deux ensemble : assombrir le fond, ou passer l'encre en graisse ≥ 600 et taille
≥ 18,66 px pour relever du seuil « texte large » (3:1).

---

# LOT 2026-08-14 — La carte des fonctions (navigation de l'admin) — À ARBITRER

Origine : Nathan demande un avis extérieur, honnête et complet, sur l'organisation de
l'admin — « pas très claire, un peu tirée par les cheveux ». Revue faite application
LANCÉE (copie de `instance/` dans un dossier temporaire, port 8099, arrêté et nettoyé),
chaque panneau et chaque dialogue parcouru en 1512 px puis en 1180 px.

**Le diagnostic tient en une phrase : le problème n'est pas l'apparence, c'est la carte
des fonctions.** L'artisanat visuel est au-dessus de la moyenne ; l'interface expose une
quinzaine de destinations au même niveau, dans quatre systèmes de navigation qui n'ont ni
le même comportement ni le même indicateur d'état. Ce n'est pas la carte du métier d'un
régisseur, c'est la sédimentation de l'historique des lots : chaque fonction a atterri là
où il restait de la place.

## Ce que la revue a établi — mesuré, pas supposé

- **Six conteneurs de navigation, treize destinations, trois comportements d'ouverture**
  (panneau / modal / menu). La règle « un bouton par fonction » (leçon 2026-07-25) est
  tenue — elle ne dit rien sur OÙ poser le bouton, et c'est là que ça s'est joué.
- **L'indicateur « vous êtes ici » saute d'une surface à l'autre.** Preuve : sur le
  panneau Impression, AUCUN onglet de l'en-tête n'est actif — l'état est passé dans la
  latérale. Sur Santé, c'est « Réglages » qui est souligné, un mot qui ne dit pas où on est.
- **« Réglages » ne contient pas les réglages** : il porte Santé et Journal (de la
  consultation) pendant que les réglages réels vivent à CINQ endroits — onglet Écran,
  barre d'état, menu Réglages, intérieur du modal Intercom, barre de la trame Impression.
- **38 % de la largeur en chrome à 1180 px** (latérale 204 + réserve 242 sur 1180), dont
  la réserve VIDE dans le cas nominal (« Tous les beltpacks sont affectés »). Le plateau
  tombe de 4 colonnes à 2.
- **L'inventaire des groupes ne fait que défiler** : `goToGroup()` = `scrollIntoView` +
  flash 900 ms. Sept rangées permanentes qui redisent les en-têtes visibles à côté.
- **Cinq mécanismes de persistance, six mots**, dont « Sauvegarde » (menu Réglages) et
  « Sauvegarder » (dialogue Configurations) — deux choses sans rapport, à une lettre près.
  Et deux boutons « Exporter » simultanés dans le même dialogue.
- **L'objet central n'a aucune affordance** : la carte beltpack est un
  `<article draggable="true">` SANS `tabindex` ni `role`, avec cinq gestes souris tous
  invisibles (clic = sélection, double-clic n° = édition, double-clic nom = édition,
  clic droit = menu, glisser = déplacer). Aucun chemin clavier vers l'objet principal ;
  le seul parcours accessible est la vue Tableau, présentée comme une préférence.
- **Les rangées `[data-group]` de l'inventaire sont focalisables et annoncées
  « bouton », mais aucun `keydown` n'y est branché** — alors que leurs voisines
  (`[data-add-group]`, `[data-view]`) en ont un, dans la MÊME fonction. Entrée n'y fait rien.
- **Le motif ARIA des onglets est à moitié posé** : `role="tablist"` contient 2 vrais
  `role="tab"`, un bouton sans rôle et une `<div>` ; les cinq panneaux n'ont pas
  `role="tabpanel"` et les onglets pas d'`aria-controls`.
- **L'interface compense par du texte ce que la structure a mal placé** : « Ne concerne
  que l'écran de régie… » (posé sous la MAUVAISE colonne), l'étiquette « Fichier » pour
  départager deux « Exporter », l'infobulle de portée sur l'inverseur. Quand il faut une
  phrase pour dire où est un objet, c'est que l'objet est au mauvais endroit.

## La maquette

`design/maquette-admin-8-navigation.html` — charge la VRAIE `admin.css` et `ink.js` en
chemins relatifs (fidélité de rendu, pas un dessin approximatif) ; navigation cliquable :
quatre onglets, rail du panneau Système, dialogue à trois volets, filtre par groupe, rail
de la réserve, inverseur d'apparence dans les deux thèmes. Rien de l'application n'est
touché ; le fichier n'est référencé par rien (Flask sert `templates/` et `static/`).

Gain mesuré à 1180 px, réserve repliée et latérale absente hors du plateau :
plateau **734 → 930 px (+27 %)**, **2 → 3 colonnes**, chrome 38 % → 21 %.

## Les six changements

1. **Quatre onglets, un seul comportement** — `Affectations · Affichage · Impression ·
   Système`. Aucun n'ouvre de modal, aucun n'ouvre de menu. L'en-tête répond à « où
   suis-je », et à ça seulement.
2. **Tout le boîtier derrière UNE porte, qui est un PANNEAU** — rail à gauche
   (Consulter : Diagnostic, Journal · Configurer : Réseau, Intercom, Sauvegarde complète,
   Mot de passe · Agir : Redémarrer), section à droite. Plus aucun réglage dans une
   fenêtre modale ; le modal redevient l'acte ponctuel (créer un groupe, éditer un
   beltpack, confirmer).
3. **Le voyant Intercom redevient un témoin** — il rejoint l'horloge et la chip d'état à
   droite, et MÈNE à Système › Intercom au lieu d'ouvrir un assistant par-dessus le plateau.
4. **Un seul lieu pour revenir en arrière** — rangée « Historique · Presets… », dialogue
   à trois volets. Remplace Historique + Configurations + les deux « Exporter ».
5. **La place rendue** — réserve repliée en rail quand elle est vide, latérale masquée
   hors du plateau, inventaire des groupes transformé en FILTRE (ce qu'il aurait dû être).
6. **La carte beltpack montre ce qu'on peut lui faire** — bouton « ··· » visible au
   survol et au focus, `tabindex`, clic droit conservé. Et `keydown` sur les rangées du
   filtre.

## Nomenclature — ARBITRÉE point par point avec Nathan le 2026-08-14

| Objet | Retenu | Écarté |
|---|---|---|
| Onglets | `Affectations · Affichage · Impression · Système` | Écran, Boîtier |
| Écran diffusé, PARTOUT | **l'affichage** | **« écran de régie » — trop situé, « 0 Pro »** |
| Section diagnostic | **Diagnostic** | Santé, État, Supervision |
| Archive complète du boîtier | **Sauvegarde complète** | Archive du boîtier, Clone, Copie de secours |
| Retour en arrière | rangée **« Historique · Presets… »** → dialogue **« Historique et presets »** | Versions, Reprendre un état, Plateaux |
| Volets | **Historique · Presets · Fichier** | Publications, Mes préparations, Import/Export |
| États nommés | **presets** (et bouton « Enregistrer un preset ») | Configurations, préparations |
| Latérale du plateau | **Filtrer par groupe** (+ section « Vues » à part) | Groupes, Filtres |
| Témoin du pied | **aucun écran connecté** (mots du Diagnostic) | aucun afficheur, aucun écran abonné |
| Inverseur d'apparence | **« Sombre » seul**, sans mot de portée | Console, Cette page, Administration |
| Intertitres du rail Système | **Consulter · Configurer · Agir** | Diagnostic/Réglages/Actions, Lire/Régler/Agir |

**« Presets » règle « Sauvegarde » gratuitement** : les états nommés n'étant plus des
« Configurations », leur bouton n'est plus « Sauvegarder ». Le mot « Sauvegarde » redevient
libre et « complète » dit sa portée. L'arbitrage de Nathan est plus économe que ma
proposition (« Archive du boîtier »).

Deux libellés DÉDUITS, non soumis, à confirmer : l'onglet **Affichage** (suivait le terme
générique — il s'appelait « Écran ») et le titre de carte **AFFICHAGE** dans cet onglet,
avec le champ réduit à **Luminosité**.

## Registre des sous-titres — RÈGLE

**Ligne de spec, jamais de pédagogie.** Verdict de Nathan sur mes premiers jets : « trop
verbeux, pas assez pro, trop long, on dirait que je prends le client pour un bébé ».

- Proscrit : l'explication PAR CONTRASTE (« …, un preset non »), qui définit un objet par
  ce qu'il n'est pas ; le cas d'usage donné en exemple ; la reformulation du titre.
- Retenu : `Conservation : 30 jours — sauf les repères épinglés, conservés indéfiniment.`
  · `Chiffrée. Contenu : plateau, affichage, réseau, intercom, presets, mot de passe.`
  · `Indisponible environ une minute. Le brouillon est conservé.` · `État : non connecté.`
  · `Un fichier .rost se transporte d'un boîtier à l'autre.` · `117 événements · dernier
  hier à 19:44` · `Le code de récupération n'est pas régénéré.`
- **Presets : AUCUN sous-titre** — le champ nommé et son bouton portent tout le sens.

## Découpage — par ordre d'exécution

**Lot 1 · « régie » quitte le produit.** Préalable, mécanique, sans risque fonctionnel —
mais il touche des fichiers déjà livrés, donc il passe AVANT d'écrire les nouveaux
panneaux. ~30 chaînes visibles : `admin.html` (16), `admin.js` (6), `print.html` (3),
`health.js` (2), `login.html`, `auth_base.html` ; plus une trentaine d'occurrences en
commentaire (`pubsub.py`, `display.py`, `discovery.py`…). ⚠️ Distinguer le VOCABULAIRE
d'interface des DONNÉES de test : `test_parcours_complet.py:50` et
`test_impression_papier.py:157` cherchent « régie » comme NOM DE GROUPE — ne pas y toucher.

**Lot 2 · Le panneau Système.** Le plus gros gain par unité de risque : il ne touche ni au
plateau, ni à la publication, ni aux e2e du plateau. Coût réel identifié à la maquette :
`admin.css` n'habille les champs et les boutons QUE dans un `<dialog>` (l. 924-967) —
sortir la configuration des modaux demande une passe de GÉNÉRALISATION des sélecteurs, pas
une duplication.

**Lot 3 · Historique · Presets · Fichier.**

**Lot 4 · Les quatre onglets + la latérale contextuelle** (masquée hors du plateau) +
l'ARIA du motif d'onglets (`role="tabpanel"`, `aria-controls`, sortir le voyant et le menu
du `tablist`).

**Lot 5 · La réserve repliable.** ⚠️ `.admin-layout` réserve `1fr var(--pool-w)` en dur
(`admin.css:405`) : sans une règle qui rend la colonne, replier la réserve ne rend RIEN au
plateau. C'est tout l'objet du lot — la largeur rendue, pas le rail.

**Lot 6 · La carte beltpack** (`tabindex`, bouton « ··· », chemin clavier) + `keydown` sur
les rangées `[data-group]`.

## Tests qui tomberont — RELEVÉ, pas supposé

- `tests/test_ui.py:250-251` — `assert "Luminosité de l'écran de régie" in html` (lots 1 et 2).
- `tests/test_ui.py:254` — `assert "Réglages → Écran" in pied` : l'infobulle disparaît (lot 4).
- `tests/test_ui.py:338-339` — le menu Réglages doit contenir `>Santé<`, `>Journal<`,
  `id="password-btn"` : le menu n'existe plus (lot 2).
- `tests/test_ui.py:133-142` — dialogue « Configurations » (lot 3).
- `tests/test_css_tokens.py:29` — clé `"écran de régie"` d'un dict de garde : renommage
  cosmétique, pas une casse.
- `tests/e2e/test_reglages_menu.py` — **fichier entier** : comportement clavier et souris
  d'un menu qui disparaît. Lignes 124/126 : `activeElement.textContent == "Santé"` /
  `"Journal"`. À réécrire en test du RAIL, pas à supprimer.
- `tests/e2e/test_panneaux_navigation.py:195-201` — « arriver sur Écran replie Affichage
  en cours » : l'onglet change de nom.
- `tests/test_panneaux.py`, `tests/test_version.py:492` — assertions sur l'onglet « Santé ».

Rappel de la leçon 2026-07-26 : **chercher le libellé dans les tests AVANT de le
renommer**, et ne jamais enchaîner un `git commit` derrière un `pytest | tail` (le pipe
masque le code retour).

## Ce que ce lot ne fait PAS

- Il ne touche pas au modèle de données, ni à la publication, ni au protocole SSE.
- Il ne redessine rien : jetons, palette de groupes, typographie, feuille imprimée,
  bouton Publier et son décompte — tout est conservé tel quel.
- Il ne résorbe pas la dette d'accessibilité du 2026-08-13 (`.confirm-danger`,
  `.selection-bar .danger-btn`) : c'est un lot à part, déjà décrit plus haut.

## Vérifications exigées à chaque lot

1. `pytest` unitaires, `pytest tests/e2e`, `ruff` — trois commandes SÉPARÉES, résultat lu,
   PUIS commit à la main.
2. Après chaque lot : capture à 1512 ET à 1180 px, dans les DEUX thèmes.
3. Après le lot 5 : mesurer la largeur du plateau et le nombre de colonnes (attendu à
   1180 px : 930 px, 3 colonnes). Une mesure, pas un coup d'œil.
4. Après le lot 6 : parcourir l'admin ENTIÈREMENT au clavier, sans souris.
5. Aucun serveur de dev laissé en fond (leçon 2026-07-26) : `lsof -ti tcp:PORT | xargs kill`.

## LIVRÉ (2026-08-15) — branche `refonte-navigation-admin`, NON commitée

**Vérifié : 585 unitaires · 75 e2e · 43 JS · ruff propre.** Trois commandes séparées,
résultats lus, aucun `&&` derrière un `pytest | tail` (leçon 2026-07-26). Serveur de
vérification arrêté et instances temporaires supprimées (leçon 2026-07-26).

Les six lots sont livrés en une passe plutôt qu'en six, leurs périmètres s'étant révélés
inséparables dès le premier : sortir les dialogues du boîtier obligeait à refaire la barre
d'onglets, qui obligeait à rendre la latérale contextuelle, qui décidait du sort de la
réserve. Le découpage tenait pour PLANIFIER, pas pour exécuter.

### Ce qui a changé
- **Onglets** `Affectations · Affichage · Impression · Système`, chacun un GLYPHE
  surmontant sa légende (demande de Nathan) — grille, écran, imprimante, écrou. Tracés en
  ligne, `stroke="currentColor"` : ils suivent l'état et le thème sans une règle de plus.
  L'en-tête n'a pas bougé d'un pixel (53 px, mesuré).
- **Voyant Intercom** : le glyphe (antenne + ondes) EST le témoin, teinté par
  `--success` / `--warning` / `--muted`. Une pastille de moins pour la même information.
  La couleur ne dit jamais seule : `title` et `aria-label` portent l'état en toutes
  lettres (`ETATS_ANTENNE`).
- **Panneau Système** : rail `Consulter · Configurer · Agir`, sept sections, toutes de
  vrais `.tab-panel` — d'où l'héritage gratuit de `?panneau=`, de la mémorisation et du
  signal `panneau-affiche`. **Plus aucun réglage dans un dialogue modal** (contrôlé : les
  neuf `showModal()` restants sont tous des actes ponctuels).
- **Historique · Presets · Fichier** en un dialogue à trois volets.
- **Latérale contextuelle**, **réserve repliable** (plateau 734 → 930 px, 2 → 3 colonnes
  à 1180 px, mesuré), **carte beltpack** focalisable avec bouton « ··· ».
- **« régie » retiré du produit** : 43 occurrences, 16 fichiers, au profit d'« affichage ».

### Quatre défauts trouvés par les e2e — tous corrigés dans le PRODUIT
1. Le repli de la réserve cachait « + Ajouter un beltpack », son unique accès. Le rail
   porte désormais la fonction lui-même (`#pool-rail-add`), et ne se replie jamais sur un
   roster vide.
2. « Déconnexion », restée dans la latérale, devenait inatteignable depuis sept panneaux.
   Elle rejoint « Redémarrer » sous « Agir » — les deux sorties, comme avant.
3. La mémorisation d'onglet survivait à la déconnexion : la session suivante s'ouvrait sur
   « Mot de passe ». Elle est oubliée à la sortie.
4. `test_systeme_rail.py` sans `pytestmark` : dix tests dans la mauvaise suite, deux
   suites vertes pour de mauvaises raisons.

### Correction du 2026-08-15 (retour de Nathan à l'usage)
« Déconnexion et Redémarrer ne sont plus accessibles comme avant, et c'est un problème. »
Juste : la rangée d'avant était visible en PERMANENCE, un clic depuis n'importe où ; les
avoir mises dans Système › Agir imposait deux clics ET un changement de panneau qui fait
perdre ce qu'on regardait.

Les deux ont été séparées, parce qu'elles n'ont pas le même profil :
- **Déconnexion** — fréquente, sans risque, elle doit rester à UN clic depuis les dix
  panneaux. Elle vit dans la **barre d'état, tout à droite** : le seul chrome permanent du
  BAS, donc le seul qui conserve le geste appris. Elle y voisine l'inverseur d'apparence,
  l'autre contrôle de la console — et rien de destructeur, contrairement à un voisinage
  avec « Publier ». Teinte et graisse de ses voisines (`--muted`, 400) : c'est un segment
  de la barre, pas une alerte ; la découvrabilité passe par le survol.
- **Redémarrer** — rare, et il coupe l'affichage une minute. Il **reste dans Système ›
  Agir** : deux clics sont le bon prix, et c'est le seul endroit où la phrase qui dit ce
  qu'on risque peut l'accompagner.

Vérifié dans le navigateur : la déconnexion est visible sur les **dix** panneaux (relevé
programmatique, pas à l'œil), elle n'est ni dans le rail ni dans l'en-tête.

### Reste à faire
- ~~**Faire relire par Nathan**, puis committer : rien n'est commité, la branche est à lui.~~
  → **relu et commité** : la refonte est dans `main` depuis `707a93b` (« la carte des
  fonctions — quatre onglets, un panneau Système, un mot pour l'affichage »).
- ~~Les deux libellés DÉDUITS sans arbitrage tiennent toujours à confirmation~~ →
  **Affichage** confirmé par Nathan le 2026-08-16. Le champ est devenu **Thème**.
- ~~La dette d'accessibilité du 2026-08-13~~ → **réglée le 2026-08-16** (lot ci-dessous) :
  jeton `--on-error`, 5,28:1 en nuit et 5,44:1 en jour, garde de contraste ajoutée.
- ~~`design/maquette-admin-8-navigation.html` est resté en arrière de l'implémentation~~ →
  **supprimée le 2026-08-16**. Elle reste lisible dans `cd8bb3d` ; l'arbitrage qu'elle
  servait est écrit en toutes lettres plus haut, c'est lui qui avait de la valeur.

---

# LOT 2026-08-16 — Dette d'accessibilité, maquette, et la course du panneau réseau

Trois demandes de Nathan en une passe : régler la dette d'accessibilité du 2026-08-13,
supprimer la maquette divergente, et comprendre les erreurs GitHub des derniers envois.

## 1. Les deux boutons rouges — ce n'est pas un arbitrage, c'est une règle non appliquée

`admin.css` énonce déjà sa règle d'encre (l. 30-34, décision du 2026-07-25) : **luminance
> 0,179 ⇒ encre SOMBRE sur bouton plein**, la même que `ink.js` pour l'écran. Mesuré :

| Jeton | Luminance | Encre due | Encre posée | Contraste |
|---|---|---|---|---|
| `--accent` nuit `#D96253` | 0,2411 | sombre | sombre ✓ | — |
| `--error` **nuit** `#F04D3E` | **0,2418** | **sombre** | `#FFFFFF` ✗ | **3,60:1** |
| `--error` **jour** `#C0392B` | 0,1431 | claire | `var(--fg)` ✗ | **3,23:1** |
| `--warning` nuit `#E8A13A` | 0,4295 | sombre | sombre ✓ | 8,67:1 |

`--error` nuit a la MÊME luminance que `--accent` (0,2418 vs 0,2411) : les deux boutons
rouges étaient simplement les seuls à ne pas suivre la règle du projet. `.reboot-btn`,
juste à côté, la suit et passe dans les deux thèmes — la norme, ce sont eux.

**Correctif** : un jeton `--on-error` par thème, dérivé de la règle et non d'un goût.
Nuit `#141005` (l'encre de `--on-accent`), jour `#FFFFFF`. Aucune couleur inventée,
`--error` intact partout ailleurs. Résultat : **5,28:1** en nuit, **5,44:1** en jour,
survols compris (5,44 et 7,53).

Garde ajoutée (`tests/test_contraste_admin.py`) : le contraste est CALCULÉ depuis les
jetons, pour les deux thèmes. Aucun test ne mesurait de contraste jusqu'ici — c'est
précisément pourquoi `.selection-bar .danger-btn` a survécu, sa couleur passant par un
jeton là où la garde anti-couleurs-en-dur ne cherche que des littéraux.

## 2. La maquette — supprimée

`design/maquette-admin-8-navigation.html` a divergé de l'implémentation sur les cinq
défauts corrigés en route. Elle n'est pas perdue : `cd8bb3d` la contient, et l'arbitrage
qu'elle servait est écrit en toutes lettres dans le lot 2026-08-14 ci-dessus. Garder un
fichier ouvrable qui rejouerait ces cinq défauts, c'est fabriquer un piège.

## 3. Les erreurs GitHub — une régression, pas un aléa

Les échecs du 11 et du 14 août étaient le job **Lint**, déjà réglé par `6beed0a`.
Les deux derniers (15 et 16 août) sont le MÊME test, deux fois :
`test_network_dialog_sets_static_ip` — `#net-static-fields` reste masqué.

**Cause racine.** `openNetwork()` est `async` et s'attache à `panneau-affiche` : le
panneau est AFFICHÉ avant que sa configuration soit lue. Entre les deux, l'opérateur
peut choisir « Statique » — puis la réponse de `/api/network` arrive, réécrit `#net-mode`
et `toggleNetFields()` remasque les champs. Le dialogue d'avant n'avait pas ce trou :
il n'apparaissait qu'une fois rempli. **La refonte panneau a ouvert la fenêtre.**

Ce n'est pas un test capricieux : c'est un vrai défaut produit, que le CI voit parce que
sa machine est plus lente, et qu'un Raspberry Pi verrait aussi. Vert ici ≠ vert ailleurs.

**Correctif** : les commandes du formulaire sont inhibées le temps de la lecture. Un
opérateur ne peut plus saisir dans un formulaire pas encore rempli — et Playwright, qui
attend l'état « enabled », se synchronise sans qu'aucun `wait` artificiel soit ajouté.

`openAntenna()` porte le MÊME défaut (il remet `#wiz-ip` et `#wiz-password` à vide après
son `await`) : corrigé pareil, sans attendre qu'un test le découvre.

---

# LOT 2026-08-16 (2) — Mise à niveau, verrouillage et surveillance des dépendances

Nathan : « pourquoi on n'utiliserait pas le dernier python ? Mets à jour, optimise et
sécurise tout ce qui doit l'être. Go dependabot. Go pour tout. »

## La question Python se retourne

Le boîtier est un **Raspberry Pi OS Bookworm** (`deploy/raspberry-pi.md`,
`deploy/build-image.md`) et `setup-pi.sh` l. 55/65 crée son venv avec le `python3` du
système — soit **Python 3.11**, ce que Debian Bookworm embarque. La CI teste sur 3.12.

**Elle n'a donc jamais testé la version qui tourne en production.** Prendre 3.14 (dernière
stable) éloignerait la CI du boîtier au lieu de l'en rapprocher : ce serait tester ce que
personne n'exécute. La bonne réponse n'est pas « la plus récente », c'est « celle du
boîtier, plus les suivantes pour voir venir ».

→ Matrice sur les tests unitaires : **3.11** (vérité du boîtier), **3.12**, **3.13**.
→ e2e sur **3.11** seule : c'est la seule version dont l'échec signifie « cassé chez le
   client », et une matrice e2e coûterait trois fois 3 minutes pour rien.
→ 3.14 volontairement écarté : aucune roue Debian, et le boîtier ne l'aura pas avant que
   Pi OS ne passe à Trixie. À réexaminer ce jour-là.

## Les six dépendances de production flottent

Bornes ouvertes : la CI et le boîtier installent « la dernière au moment du `pip install ».
Écart constaté entre ce qui est déclaré et ce que la CI a réellement installé :
`cryptography>=42` → 50.0.0 (8 majeures), `gunicorn>=21` → 26.0.0 (5), `Flask-Limiter>=3.5`
→ 4.1.1 (changement de majeure). Personne n'a décidé ça, et **un déploiement d'aujourd'hui
n'installe pas ce qu'installait un déploiement du mois dernier.**

C'est la leçon déjà écrite à côté de `ruff` dans requirements-dev.txt, jamais appliquée aux
dépendances de production. Ordre retenu : METTRE À JOUR d'abord, VÉRIFIER, PUIS figer —
figer sur un état non vérifié ne ferait que graver une inconnue.

## Les quatre chantiers

1. Matrice Python en CI (3.11/3.12/3.13), e2e sur 3.11.
2. `.venv` local resynchronisé sur ce que la CI installe, suites relancées dessus — c'est
   l'écart local/CI qui a valu deux CI rouges cette semaine.
3. Bornes hautes sur les six dépendances de production (`>=x,<y+1`), après vérification.
4. `dependabot.yml` (pip + npm + github-actions) : c'est lui qui rend l'épinglage au SHA
   tenable, et les alertes de sécurité sont aujourd'hui DÉSACTIVÉES sur le dépôt (403).
5. shellcheck 0.9.0 → 0.11.0, avertissements nouveaux traités.

## Vérification exigée

Suites complètes sur le venv REMIS À NIVEAU (pas l'ancien), puis CI sur branche avant
fusion. Une mise à jour de dépendances ne se valide pas en lisant un numéro de version.

## LIVRÉ (2026-08-16) — branche `maj-dependances-et-python`

CI verte sur la branche AVANT fusion, six jobs : **py3.11 · py3.12 · py3.13**, e2e sur
3.11, lint, JS. C'est la première fois que la version du boîtier est testée.

- Python : matrice 3.11/3.12/3.13, e2e sur 3.11. 3.14 écarté (le boîtier ne l'aura pas).
- Six dépendances de production bornées, après mise à niveau ET vérification :
  597 unitaires, 76 e2e, couverture 89 %, ruff 0.16.3 propre.
- `.venv` local resynchronisé (il avait trois paquets de retard, dont Playwright 1.60
  contre 1.62 en CI — d'où le confort trompeur des e2e de cette semaine).
- shellcheck 0.9.0 → 0.11.0, aucun avertissement nouveau. `lint-local.sh` lit sa version
  dans `ci.yml`, la divergence local/CI qu'il signalait en en-tête disparaît.
- `dependabot.yml` : pip hebdomadaire (majeures isolées), actions et npm mensuels groupés.
- **Alertes de sécurité du dépôt ACTIVÉES** (elles étaient coupées), plus les correctifs
  de sécurité automatiques.

### Reste ouvert
- ~~`pyproject.toml` n'a pas de section `[project]`~~ → **fait le 2026-08-18** : la section
  existe, `requires-python = ">=3.11"`, et `tests/test_versions_supportees.py` l'ancre à la
  cible de déploiement. (Entrée restée non rayée un jour : un « reste ouvert » périmé est
  pire qu'une liste absente — il fait chercher un travail déjà fait.)
- ~~Python 3.14 : à réexaminer~~ → **mesuré compatible le 2026-08-18**, entré dans la
  matrice comme vigie. Le réexamen porte désormais sur le PLANCHER, pas sur 3.14, et c'est
  la garde qui le déclenchera quand `deploy/` changera de cible.

## LIVRÉ (2026-08-18) — branche `versions-supportees-ancrees`

La fragilité relevée au lot précédent est levée : `requires-python = ">=3.11"` dans
`pyproject.toml`, et `tests/test_versions_supportees.py` (4 tests) ancre le plancher à la
CIBLE DE DÉPLOIEMENT plutôt qu'à une préférence. Éprouvé en désaccordant le plancher :
trois assertions sur quatre tombent avec un message qui dit quoi faire.

- **Python 3.14 : mesuré compatible**, pas seulement supposé — venv 3.14.5 jetable,
  dépendances installées, 597 unitaires verts. Entré dans la matrice comme vigie.
- Matrice : 3.11 (boîtier Bookworm) · 3.12 · 3.13 (boîtier Trixie de demain) · 3.14 (vigie).
- Job lint ramené de 3.12 à 3.11, comme les e2e.
- 14 `datetime.timezone.utc` → `datetime.UTC`, débloqués par la déclaration du plancher.
- Vérifié : 601 unitaires, 76 e2e, 43 JS, ruff propre, couverture 89 %.

### Trixie, pour mémoire
Raspberry Pi OS Trixie (octobre 2025) rebase sur Debian 13 et fait passer le Python
système de 3.11 à **3.13**. Le jour où `deploy/raspberry-pi.md` visera Trixie, la garde
réclamera un plancher à 3.13 — c'est exactement ce qu'elle est là pour faire.

## LIVRÉ (2026-08-19) — ménage

- **Dependabot** passe en `versioning-strategy: increase-if-necessary`. Ses quatre
  premières PR relevaient un plancher vers une version que la fourchette autorisait déjà
  (`flask>=3.1` → `>=3.1.3`) : rien de ce qui s'installe n'aurait changé. Fermées avec
  l'explication. Le risque n'était pas le travail, c'était l'habitude — quatre PR sans
  enjeu et on ferme sans lire, y compris la cinquième.
- **Neuf branches distantes supprimées**, après contrôle que chacune ne portait aucun
  commit absent de `main` (`git rev-list --count origin/main..origin/<b>` = 0). Le distant
  ne porte plus que `main`.

### Nuance à ne pas perdre
Les bornes hautes empêchent une MAJEURE d'arriver seule sur le boîtier, pas une mineure :
ce qui reste dans la fourchette continue d'être installé sans rien demander. Figer à
l'octet près demanderait un fichier de verrouillage avec empreintes — chantier non ouvert,
et non nécessaire tant que les majeures sont tenues.

### Trixie — écarté le 2026-08-19
Décision de Nathan : on n'y va pas. Le code est prêt (py3.13 vert en continu), mais la
migration porterait sur l'APPLIANCE — `cage`/`chromium` en kiosque Wayland, `/boot/firmware`,
`nmcli` —, tout ce qui a été validé sur vrai matériel serait à revalider, et aucun besoin
ne l'exige. La garde `test_versions_supportees.py` réclamera le plancher 3.13 le jour où
`deploy/raspberry-pi.md` visera Trixie : la bascule est préparée, pas engagée.

---

# LOT 2026-08-19 — Les entrées : rendre l'arrivée des écrans perceptible

Nathan : « j'aimerai un peu plus d'animations pour rendre l'interface sympa ». Option
retenue après relevé : **sobre — les entrées, bien faites**. L'écran n'est pas touché.

## Ce que le relevé a montré

Les trois surfaces ne sont pas au même point, et la demande ne portait pas là où je
croyais :

- **L'écran est déjà le mieux servi** : `block-in` + `text-in`, 260 ms, décalage par rang
  (`--anim-i`), plafonné (`--anim-cap`), supprimé en mode performance, et testé
  (`test_transitions_affichage.py`). Rien à ajouter — on n'y touche pas.
- **La connexion est animée sur le papier seulement** : `auth-arrivee` dure **0,16 s**,
  sous le seuil de perception. Elle existe sans se voir.
- **L'admin n'a AUCUNE animation d'arrivée.** Des animations ponctuelles oui (`block-up`,
  `inv-flash`, `pub-sent`), mais l'écran entier surgit d'un bloc. C'est le vrai manque.
- **`display.css` est la seule des quatre feuilles à ignorer `prefers-reduced-motion`.**
  Ce n'est pas une question de goût : corrigé quoi qu'il arrive.

## Le principe

Une animation d'ARRIVÉE est gratuite : elle joue une fois, sur un écran qu'on découvre,
et personne n'attend derrière. Une animation qui RETARDE un contrôle en régie est hostile.
Donc : soigner les entrées, ne jamais ralentir un geste. Budget total sous 400 ms.

## Ce qui est fait

1. **Admin** — cascade sur les trois conteneurs STABLES : `header.admin-top` →
   `div.admin-body` → `footer.admin-status`. Ancrer sur les panneaux serait une faute :
   ils sont pilotés par `hidden`, l'animation rejouerait à chaque changement d'onglet.
2. **Connexion** — `.auth-col` allongé, puis décalage de ses enfants via `> :nth-child()`.
   Par position et non par classe : les trois gabarits (login, setup, recover) n'ont pas
   la même liste d'enfants, une règle positionnelle les couvre tous sans les énumérer.
3. **`display.css`** — bloc `prefers-reduced-motion` aligné sur les trois autres feuilles.
4. **Garde** — un test vérifie que toute feuille qui anime respecte `prefers-reduced-motion`,
   et que le budget d'entrée reste sous 400 ms.

## Deux pièges écartés

- `transform` sur un conteneur crée un bloc englobant et casserait `position: fixed` chez
  ses descendants. Vérifié : les trois éléments fixes (`.cr-toast`, `.drag-ghost`,
  `.selection-bar`) sont HORS `.admin-body`. Et `backwards` — non `forwards` — fait que la
  transformation ne survit pas à l'animation : la fenêtre de risque est nulle.
- Pas de nouveaux jetons CSS pour les durées : les timings du dépôt sont déjà littéraux
  (`block-up 0.3s`, `inv-flash 0.9s`), et un jeton non couleur dans `:root` irait se
  heurter aux gardes de thème.

## CORRECTION en cours de lot — `display.css` n'avait pas de manque

Le plan ci-dessus affirmait que `display.css` « est la seule des quatre feuilles à ignorer
`prefers-reduced-motion` ». **C'est faux, et je l'ai vérifié trop tard** : `display.html`
charge `main.css` (l. 9) AVANT elle, et la règle qui s'y trouve porte sur `*` en
`!important` — la cascade des blocs et le fondu des textes étaient déjà couverts.

L'erreur de raisonnement : j'ai compté les feuilles au lieu de compter les PAGES.
`admin.css`, `auth.css` et `print.css` sont autonomes (elles ne chargent pas `main.css`,
c'est un découplage voulu et testé), donc elles doivent porter la règle. `display.css` ne
l'est pas : elle n'a pas à se suffire.

Le bloc ajouté a été retiré, remplacé par un commentaire qui dit POURQUOI il n'y en a pas
— sans quoi le prochain lecteur referait le même « correctif ».

Ce qui reste de l'épisode, et qui valait le détour : `tests/test_mouvement.py` raisonne
par GROUPE de feuilles chargées ensemble, découpage repris de `test_css_tokens.py`. Une
garde fichier par fichier aurait signalé un manque inexistant à chaque exécution — et une
garde qui crie à tort finit désactivée.

## LIVRÉ (2026-08-19)

- **Admin** : cascade `admin-entree` sur `.admin-top` → `.admin-body` → `.admin-status`.
  MESURÉ dans le navigateur via `getAnimations()` : retards 0 / 60 / 110 ms, durée 200 ms,
  dernier élément arrivé à **310 ms**.
- **Connexion** : `auth-arrivee` passe de 0,16 s (imperceptible) à 240 ms, avec décalage
  positionnel des enfants — 40 / 90 / 130 / 160 ms, plafonné au 4e.
- **Écran** : non touché, sa cascade était déjà la meilleure des trois.
- **Garde** : `tests/test_mouvement.py`, 6 tests + 1 ignoré à raison (`print.css` n'anime
  rien). Éprouvée dans les deux sens : retirer la règle de `main.css` la fait échouer,
  gonfler l'entrée à 900 ms aussi.
- Vérifié : 607 unitaires, 76 e2e, 43 JS, ruff propre.

---

# LOT 2026-08-20 — État des lieux : trois « restes » périmés, et une version qui mentait

État des lieux demandé par Nathan. Les suites ont été relancées avant tout jugement :
**607 unitaires · 76 e2e · 43 JS · ruff propre · couverture 88,97 %**, arbre et distant
propres, CI verte. Rien à redresser côté produit — la dette qui restait était
**documentaire**, et dans un dépôt qui se pilote par `todo.md`, c'est la plus coûteuse.

## Ce que le relevé a trouvé de faux

Trois entrées décrivaient un travail **déjà fait**. Exactement le piège que la leçon du
2026-08-19 nomme : « un reste ouvert périmé est pire qu'une liste absente — il fait
chercher un travail déjà fait. » Écrite, puis reproduite trois fois ailleurs dans le même
fichier, parce que rayer une entrée demande de RELIRE les vieilles sections, ce que
personne ne fait en clôturant un lot.

1. `### Reste à faire` du lot refonte navigation : « rien n'est commité, la branche est à
   lui » — la refonte est dans `main` depuis `707a93b`.
2. « `tests/e2e/test_e2e.py` fait 600+ lignes » — découpé par `fbae2cb`, le fichier
   n'existe plus, le plus gros e2e fait 303 lignes.
3. « Cahier des charges (D1) non retouché depuis l'origine » — réécrit par `79f6a64`.
   (Et la dette n°2 du helper e2e dupliqué huit fois : zéro occurrence aujourd'hui.)

## La version qui mentait, et pourquoi rien ne l'a dit

`README.md` et le cahier des charges annonçaient **Python 3.12** alors que le plancher est
passé à **3.11** le 2026-08-16, puis a été ancré dans `pyproject.toml` le 2026-08-18.
Quatre jours de faux, en silence.

La cause n'est pas l'oubli, c'est la **portée de la garde existante** :
`test_versions_supportees.py` confronte `pyproject.toml` à `deploy/`. Elle surveille la
chaîne technique, pas la prose. Or c'est la prose que lit quelqu'un qui installe.

## Ce qui est fait

- **README** : `Python 3.11+`, et la commande d'installation passe de `python3.12 -m venv`
  à `python3 -m venv` — c'est ce que fait `deploy/setup-pi.sh` l. 65 sur le boîtier. Une
  note dit le plancher et la matrice (3.11 → 3.14).
- **Cahier des charges** : `Python 3.11+` en §6 (portabilité) et §10.1 (pile).
- **§10.7 — les compteurs de tests retirés**, pas mis à jour. Ils étaient figés à
  553 · 67 au 2026-08-11 quand les suites en comptaient 607 et 76. Un nombre qui change à
  chaque lot ne se maintient pas à la main : il ne serait redevenu faux qu'au lot suivant.
  Ce qu'un cahier des charges doit garantir, c'est que les suites existent et passent —
  leur compte du jour se lit en les lançant.
- **Garde** : `test_la_version_python_annoncee_est_le_plancher_declare`, paramétrée sur
  les DEUX documents, lit `requires-python` via `tomllib` et exige que chaque « Python
  X.Y » du document soit ce plancher.

## Éprouvée dans les deux sens — pas seulement verte

- README remis à `Python 3.12` → le cas `[readme]` tombe, le cas `[cahier]` reste vert
  (la mutation ne fausse qu'une propriété).
- Plancher `pyproject` porté à `>=3.13` → les deux cas tombent, avec le message qui dit
  quoi corriger.
- Fichiers restaurés et contrôlés après chaque mutation.

Le jour où `deploy/` visera Trixie, `test_versions_supportees.py` réclamera le plancher
3.13 et CETTE garde-ci réclamera les deux documents. Les deux moitiés du problème sont
tenues.

## Reste ouvert — vérifié encore ouvert au 2026-08-20

- ~~**La course sur le champ rôle** dans `admin.js`~~ → **RECTIFIÉ le 2026-08-20, voir
  ci-dessous.** Elle était réglée depuis le 2026-08-09 ; je l'ai reconduite sans lire le
  code.
- **Le pied de la feuille imprimée** qui redit l'en-tête : garder demandé, alléger non
  tranché.
- **Captures dans la documentation** (étape 7 du lot des apparences) : jamais demandé.
- **Le blanc en bas de rangée** à l'impression : prix assumé de l'alignement.

## RECTIFICATIF (même jour) — le lot a fabriqué le défaut qu'il corrigeait

Nathan a demandé ce qu'était cette « course sur le champ rôle ». En ouvrant `admin.js`
pour lui répondre : **elle n'existe plus**, et le relevé ci-dessus était faux.

Les trois autres entrées de ce lot ont été vérifiées commit par commit (`707a93b`,
`fbae2cb`, `79f6a64`). Celle-ci, non : je l'ai recopiée depuis le document qui la portait,
en me contentant de la redater. **Une entrée datée « vérifié au 2026-08-20 » est plus
crédible qu'une entrée sans date** — l'erreur est donc plus coûteuse que celle qu'on
venait de corriger, pas moins.

Ce qui restait ouvert se réduit à trois arbitrages qui appartiennent à Nathan, et **zéro
défaut produit connu** : le pied de la feuille imprimée, les captures dans la doc, le blanc
en bas de rangée.

---

# LOT 2026-08-20 (2) — Quatre points signalés à l'usage

Nathan, après un état des lieux : réserve non repliable, dialogue « Historique et presets »
jugé mauvais, recherche qui ne filtre pas, et une question de droit des marques.

## 1. La réserve se replie — LIVRÉ (`f7d235c`)

Le mot « bug » laissait attendre un défaut de comportement ; le relevé a montré **une
fonction absente**. `refletRail` faisait dépendre le pli d'une seule condition calculée
(zéro disponible), et aucun contrôle ne permettait de replier.

Second défaut, plus insidieux, trouvé en lisant le premier : `pool-rail-open` posait
`state.poolOuvert = true` et **aucun chemin ne le remettait à `false`**. Déplier était
irréversible pour la session.

`poolOuvert` a trois états : `null` calcule, `true`/`false` commandent, et la commande bat
le calcul — sans quoi un repli serait défait par l'action suivante, donc inutilisable. Le
bouton se cache sur un roster vide plutôt que d'y rester sans effet.

Garde : `tests/e2e/test_reserve_repli.py`, 4 tests, confrontée à sa mutation — l'ancienne
formule rétablie en fait tomber trois. Le quatrième porte sur la visibilité du bouton, qui
ne dépend pas du calcul : il est juste qu'il tienne.

## 2. La recherche filtre — LIVRÉ (`f7d235c`)

`.includes()` retenait une lettre trouvée n'importe où : taper « i » mettait en avant
Régie, Lumière ET Micro. Règle retenue avec Nathan : le **début d'un mot** — « son »
trouve « Régie son », « i » ne trouve rien.

**Le repli des accents n'est pas un supplément, c'est ce que la règle du début EXIGE** :
`"régie".startsWith("re")` est faux, donc passer au début sans replier aurait rendu la
recherche pire qu'avant, sur exactement le vocabulaire de ce produit (Régie, Éclairage).

La règle vit dans `board.js` (logique pure, 8 tests vitest) et sert les DEUX filtres —
réserve et plateau. NFD + plage U+0300-U+036F plutôt que `\p{Diacritic}` : pas de plancher
de version sur le Chromium du boîtier.

## 3. Marques Riedel — LIVRÉ

Question de Nathan : peut-il nommer Riedel dans son logiciel ? Réponse documentée dans le
produit plutôt que dans un fil de discussion.

L'usage **référentiel** d'une marque tierce est prévu par les textes (art. L.713-6 CPI,
art. 14(1)(c) du règlement UE 2017/1001) : nommer la marque pour indiquer la destination
de son propre produit, à condition de ne pas suggérer de lien commercial. Nommer
« antenne Bolero » est donc le cas prévu ; le logo, la typographie ou un nom de produit
qui intègre la marque ne le seraient pas.

Désaveu ajouté au README et au panneau **Diagnostic** — pas dans un « À propos », il n'en
existe pas et en créer un pour une phrase serait un panneau de plus à traverser.

**Le vrai sujet n'était pas la marque.** `RIEDEL SOFTS/` (150 Mo) contient leur webapp,
leurs bundles et un `BOLERO_API_BIBLE.md` : c'est du DROIT D'AUTEUR, que nul désaveu ne
règle. Contrôlé : `.gitignore` l. 51, **zéro fichier suivi**, rien n'est jamais parti sur
GitHub. À garder strictement local — jamais dans une image de boîtier ni dans une archive
de sauvegarde.

## 4. « Historique et presets » — NON FAIT, à prendre en session fraîche

Nathan a coché les TROIS axes : les listes elles-mêmes, l'incohérence des trois volets, et
le cadre du dialogue qui saute d'un volet à l'autre. C'est une refonte, pas un correctif.

Relevé déjà fait, à ne pas refaire :
- `admin.html` l. 839-887 — trois volets sous un segmenté, sans composition commune :
  Historique a notice + liste + pied rouge ; Presets a saisie + liste, sans notice ;
  Fichier a notice + deux boutons, sans liste.
- « Supprimer l'historique » est seul dans un pied que les deux autres volets n'ont pas.
- `.history-list` et `.configs-list` n'ont quasiment aucune règle propre dans `admin.css`.
- Le dialogue se dimensionne sur son contenu : changer de volet fait sauter la boîte.

Méthode convenue : peupler historique et presets en local, capturer dans les deux thèmes,
**proposer un parti pris écrit AVANT de toucher une ligne**.

---

# LOT 2026-08-20 (3) — Le dialogue « Historique et presets » rejoint le produit

Retour de Nathan sur le parti pris proposé : **point 1 REFUSÉ** (ne pas inverser
horodatage et nom — c'est l'horodatage qui mène la rangée), points 2 à 6 retenus, plus
trois demandes : le bouton favori, le sélecteur de volets, et surtout — « de façon
générale ce menu est très loin du design de l'interface principale ».

## Ce que les captures ont montré

Dialogue peuplé, capturé et MESURÉ (script jetable, `DATA_DIR` temporaire) :

- **Le cadre perdait 55 % de sa hauteur** : 502 / 400 / 224 px selon le volet, à largeur
  constante. La boîte s'effondrait sous le curseur.
- **Douze boutons** dans le volet Presets (4 rangées × 3), dont quatre « Supprimer » en
  rouge — quatre alertes pour une liste d'objets ordinaires, et le nom, seule chose qu'on
  lit, devenu l'élément le plus discret.
- **Le `space-between` creusait un trou** : tout l'espace s'accumulait entre le nom et les
  boutons, d'autant plus large que le nom était court.
- **Trois charpentes différentes** dans un même dialogue.

Et la langue elle-même : le plateau est fait de RANGÉES PLATES — numéro tabulaire discret,
nom en gras, un filet pour séparer, presque aucun bouton visible. Le dialogue empilait des
cartes blanches bordées et des boutons pleins. Deux vocabulaires dans un produit.

## Le défaut que la refonte a RÉVÉLÉ, et qui n'était pas cosmétique

`.tb-seg .seg-btn` (l. 459) ne pose pas de fond. Sur cette seule propriété,
`.admin-dialog button` (l. 974) l'emportait et peignait les trois onglets en
`--surface-3` — **la teinte réservée à l'onglet ACTIF**. Trois onglets actifs, donc aucun :
**le segmenté n'a jamais dit quel volet était ouvert.**

Invisible tant qu'on ne compare pas le dialogue à la barre d'outils du plateau, où le même
composant fonctionne. C'est une perte d'information, pas une question de goût — et c'est
en cherchant à rapprocher les deux qu'elle est apparue.

## Ce qui est fait

- **Rangées plates** : plus de carte par ligne, un filet pour séparer, survol en `--inset`.
  L'horodatage en tête, tabulaire, `--muted` — le rôle du numéro de beltpack (arbitrage
  de Nathan : l'inversion est écartée).
- **Actions à la demande**, idiome de la carte beltpack : rien au repos, tout au survol ET
  au focus. `#context-menu` n'est PAS réutilisé — il porte `state.context {userId,
  blockId}`, le généraliser toucherait le chemin beltpack pour rien.
- **L'épingle est un ÉTAT** : elle reste visible une fois posée, s'efface sinon, et prend
  `--accent`. Elle a sa PROPRE colonne de grille — la mettre dans `.vers-actions` la ferait
  hériter d'`opacity: 0`, qu'aucune règle enfant ne peut annuler.
- **Charpente unique** aux trois volets : notice → corps → pied, avec `min-height` sur le
  corps. Écart de hauteur ramené de 278 px à 40 px.
- **Le destructeur part à gauche** : « Supprimer l'historique » n'est plus empilé au-dessus
  de « Fermer ». Même arbitrage que `.reboot-btn` dans Système.
- **Grille au lieu de `space-between`** : le trou se referme.

## Gardes — et une garde creuse réparée

`tests/e2e/test_versions_dialogue.py`, 3 tests qui MESURENT au lieu de regarder.

Le test de hauteur, écrit d'abord sur un boîtier neuf, était **CREUX** : listes vides,
trois volets naturellement courts, retirer `min-height` ne le faisait pas tomber. Il
passait sans rien démontrer. Réparé en peuplant le décor — trois publications, trois
presets. Il tombe désormais avec « le dialogue change de hauteur de 101 px ».

Les trois confrontées à leur mutation, chacune ne tombant que sur la sienne :
retirer le fond de l'onglet actif → test 1 ; retirer `min-height` → test 2 ;
retirer `:focus-within` → test 3.

Le test du segmenté compare les trois fonds ENTRE EUX et non à une couleur nommée : la
valeur appartient au thème, la DIFFÉRENCE appartient au produit. Il a d'abord échantillonné
pendant la transition (`rgba(…, 0.004)`, un fond en train d'apparaître) — corrigé en
attendant que les valeurs cessent de bouger, pas en allongeant un `sleep`.

## Retour de Nathan sur les presets (même jour)

« La partie presets, mieux compartimenter les presets sauvegardés, là on ne distingue pas
bien dans l'interface. » Juste : en aplatissant les rangées, j'avais appliqué aux presets
le traitement de l'historique, alors que les deux listes n'ont pas la même nature.

**Un repère d'historique se lit dans une SUITE** — le filet suffit à le séparer du
précédent, et six surfaces empilées feraient un damier. **Un preset se choisit
ISOLÉMENT** : à plat, sa rangée n'était qu'une ligne de texte, et quatre presets se
lisaient comme un paragraphe.

Deux corrections, dont une seule est cosmétique :

1. **`updated_at` était renvoyé par l'API et JETÉ par l'interface.** `Configs.list()` le
   compose depuis toujours (`comroster/services/configs.py` l. 33), `refreshConfigs`
   n'affichait que le nom. C'est un défaut d'INFORMATION, et c'est lui qui explique le
   symptôme : une rangée réduite à un mot ne fait pas objet. Ajouter une bordure n'y
   aurait rien changé. Formatage côté client — changer la réponse de `/api/configs`
   toucherait un contrat testé pour un gain nul.
2. **Surface rendue aux rangées de presets** : `--inset`, rayon, intervalle réel, sans
   bordure — celle des rangées de beltpack dans un groupe. Compartimenté dans la langue du
   plateau, pas en cartes bordées. L'historique garde ses filets.

Garde : `test_un_preset_montre_sa_date_d_enregistrement`, confrontée à sa mutation (date
vidée → « la rangée n'affiche aucune date »). Elle vérifie la PRÉSENCE d'une date, jamais
son formatage : `toLocaleString` dépend de la locale du navigateur, et figer « 20 août »
ferait tomber le test sur une machine en anglais sans qu'aucune information soit perdue.

Vérifié : 609 unitaires, 84 e2e, 51 JS, ruff propre.
