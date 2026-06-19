# ComRoster — Suivi

**Plan détaillé (source de vérité) :** [docs/superpowers/plans/2026-06-19-comroster.md](../docs/superpowers/plans/2026-06-19-comroster.md)

## Décisions techniques actées
- Python 3.12, Flask
- CSRF : Flask-WTF · Rate-limit login : Flask-Limiter
- Persistance : JSON plats + écriture atomique sous lock · IDs UUID4
- SSE broker mémoire → **1 seul worker gunicorn** en prod

## État des phases — TERMINÉ (59 tests verts)
- [x] P0 — Socle (factory, config, /healthz)
- [x] P1 — Données & validation (model, storage atomique) — *TDD strict*
- [x] P1b — Rôle mémorisé par beltpack (beltpack_roles)
- [x] P2 — Auth & sécurité (setup/login/recover, CSRF, rate-limit, cookies durcis)
- [x] P3 — API CRUD (groupes, personnes, import/export)
- [x] P4 — Publication & SSE (pubsub, history, /events) — *TDD strict*
- [x] P5 — UI Admin (DnD SortableJS, publier, historique)
- [x] P6 — UI Display (EventSource, glassmorphism, auto-scroll, reconnexion)
- [x] P7 — Historique (UI en P5 + API testée en P4)
- [x] P8 — Durcissement & déploiement (systemd, nginx, gunicorn 1 worker)

## Vérifié en réel
- Flux SSE bout-en-bout (snapshot + published poussé après publication).
- Démarrage prod gunicorn (1 worker, en-têtes SSE corrects).
- beltpack→rôle remonte jusqu'au display (`beltpack_roles`).

## Reste manuel (navigateur)
Drag-and-drop SortableJS, auto-scroll, bascule jour/nuit : à valider à l'œil dans un vrai navigateur.
