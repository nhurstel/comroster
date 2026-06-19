# Leçons — ComRoster

Format : `[date] | ce qui a mal tourné | règle pour l'éviter`

[2026-06-19] | pytest ne trouvait pas le module `comroster` (ModuleNotFoundError dans conftest) | Tout projet Python à la racine sans packaging : créer un `pyproject.toml` avec `[tool.pytest.ini_options] pythonpath = ["."]` dès P0, sinon les imports échouent.
[2026-06-19] | TemplateNotFound : Flask cherche `comroster/templates/` mais les templates sont à la racine du projet | Quand templates/ et static/ sont hors du package, instancier `Flask(__name__, template_folder="../templates", static_folder="../static")`.
[2026-06-19] | Smoke test HTTP local : login/publish renvoyaient 400 (CSRF) car `SESSION_COOKIE_SECURE=True` empêche le cookie de session de circuler sur HTTP non-TLS | Comportement CORRECT en prod (HTTPS). Pour tester en local sans TLS, lancer avec `FLASK_DEBUG=true` (désactive SECURE) ou passer par le test client pytest (CSRF off).
