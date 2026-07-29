import json

import pytest

from comroster import create_app

#: SVG minimal valide, suffisant pour passer la validation d'un pack de marque
#: (comroster/services/branding.py ne regarde que l'extension et l'existence du fichier).
_SVG_MARQUE = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"></svg>'


@pytest.fixture
def app(tmp_path):
    app = create_app({"TESTING": True, "DATA_DIR": str(tmp_path), "SECRET_KEY": "test-secret"})
    return app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth_client(client):
    """Client déjà authentifié (la plupart des routes exigent une session admin).

    Onze fichiers de test la redéfinissaient à l'identique ; elle vit ici pour que les
    nouveaux n'aient pas à la recopier une douzième fois. Les définitions locales
    existantes continuent de primer : pytest résout la fixture la plus proche.
    """
    client.post("/admin/setup", data={"password": "motdepasse8"})
    return client


@pytest.fixture
def client_avec_pack(tmp_path):
    """Fabrique un client dont l'application a un pack de marque client actif.

    Fixture-USINE (elle renvoie une fonction, pas un client) : le pack posé varie d'un
    test à l'autre (nom, fichiers, drapeau `mono`) — `client_avec_pack(manifeste=...,
    fichiers=...)`, ou `client_avec_pack()` pour le pack par défaut.

    Promue ici depuis tests/test_branding.py, sur le même précédent qu'`auth_client` :
    tests/test_version.py la réutilisait via un import direct d'un helper privé d'un
    autre fichier de tests (`from test_branding import _client_avec_pack`), ce qui
    imposait un `# noqa: E402` (le groupe E4 est délibérément sélectionné dans
    pyproject.toml) et couplait deux fichiers de tests sans raison de fond.
    """
    def _fabrique(manifeste=None, fichiers=("logo.svg",)):
        dossier = tmp_path / "branding"
        dossier.mkdir(exist_ok=True)
        for nom in fichiers:
            (dossier / nom).write_bytes(_SVG_MARQUE)
        (dossier / "brand.json").write_text(
            json.dumps(manifeste or {"name": "Acme Live", "logo": "logo.svg"}),
            encoding="utf-8",
        )
        app = create_app({
            "TESTING": True,
            "DATA_DIR": str(tmp_path),
            "SECRET_KEY": "test-secret",
            "BRAND_DIR": str(dossier),
        })
        return app.test_client()
    return _fabrique
