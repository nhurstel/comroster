import pytest
from comroster import create_app


@pytest.fixture
def app(tmp_path):
    app = create_app({"TESTING": True, "DATA_DIR": str(tmp_path), "SECRET_KEY": "test-secret"})
    return app


@pytest.fixture
def client(app):
    return app.test_client()
