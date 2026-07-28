import pytest

from comroster import create_app


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
