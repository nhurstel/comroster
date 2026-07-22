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
