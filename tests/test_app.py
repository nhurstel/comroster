def test_healthz(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok"}


def test_prod_requires_secret_key():
    import pytest
    from comroster import create_app
    with pytest.raises(RuntimeError):
        create_app({"TESTING": False, "DEBUG": False, "SECRET_KEY": None})
