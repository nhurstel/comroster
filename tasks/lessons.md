# Leçons — ComRoster

Format : `[date] | ce qui a mal tourné | règle pour l'éviter`

[2026-06-19] | pytest ne trouvait pas le module `comroster` (ModuleNotFoundError dans conftest) | Tout projet Python à la racine sans packaging : créer un `pyproject.toml` avec `[tool.pytest.ini_options] pythonpath = ["."]` dès P0, sinon les imports échouent.
