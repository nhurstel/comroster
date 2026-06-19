# ComRoster — Suivi

**Plan détaillé (source de vérité) :** [docs/superpowers/plans/2026-06-19-comroster.md](../docs/superpowers/plans/2026-06-19-comroster.md)

## Décisions techniques actées
- Python 3.12, Flask
- CSRF : Flask-WTF · Rate-limit login : Flask-Limiter
- Persistance : JSON plats + écriture atomique sous lock · IDs UUID4
- SSE broker mémoire → **1 seul worker gunicorn** en prod

## État des phases
- [ ] P0 — Socle (factory, config, /healthz)
- [ ] P1 — Données & validation (model, storage atomique) — *TDD strict*
- [ ] P2 — Auth & sécurité (setup/login/recover, CSRF, rate-limit)
- [ ] P3 — API CRUD (groupes, personnes, import/export)
- [ ] P4 — Publication & SSE (pubsub, history, /events) — *TDD strict*
- [ ] P5 — UI Admin (DnD SortableJS, publier)
- [ ] P6 — UI Display (EventSource, glassmorphism, auto-scroll, reconnexion)
- [ ] P7 — Historique (nice-to-have)
- [ ] P8 — Durcissement & déploiement (systemd, nginx, gunicorn)

## Prochaine action
Démarrer P0 — décider du mode d'exécution (subagents par tâche vs inline).
