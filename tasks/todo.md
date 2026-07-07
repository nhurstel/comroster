# ComRoster — Suivi

**Plan détaillé (source de vérité) :** [docs/superpowers/plans/2026-06-19-comroster.md](../docs/superpowers/plans/2026-06-19-comroster.md)

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

## Non traité (choix assumés)
- `venv/` (Python 3.14, 44 Mo) coexiste avec `.venv/` (3.12 utilisé partout) → à supprimer
  à la main si plus utile, je n'ai pas voulu détruire un environnement potentiellement utilisé.
- `beltpack_roles` jamais purgé (croissance négligeable).
- Compteurs rate-limit en mémoire (reset au restart) : acceptable appliance mono-process.
