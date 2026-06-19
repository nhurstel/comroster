# Leçons — ComRoster

Format : `[date] | ce qui a mal tourné | règle pour l'éviter`

[2026-06-19] | pytest ne trouvait pas le module `comroster` (ModuleNotFoundError dans conftest) | Tout projet Python à la racine sans packaging : créer un `pyproject.toml` avec `[tool.pytest.ini_options] pythonpath = ["."]` dès P0, sinon les imports échouent.
[2026-06-19] | TemplateNotFound : Flask cherche `comroster/templates/` mais les templates sont à la racine du projet | Quand templates/ et static/ sont hors du package, instancier `Flask(__name__, template_folder="../templates", static_folder="../static")`.
