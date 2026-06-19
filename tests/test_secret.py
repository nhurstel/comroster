import os
import pytest
from comroster.services.secret import SecretStore


def test_setup_and_verify(tmp_path):
    s = SecretStore(str(tmp_path))
    assert not s.is_configured()
    code = s.setup("motdepasse8")
    assert s.is_configured()
    assert isinstance(code, str) and len(code) >= 8
    assert s.verify_password("motdepasse8")
    assert not s.verify_password("mauvais")


def test_setup_twice_refused(tmp_path):
    s = SecretStore(str(tmp_path))
    s.setup("motdepasse8")
    with pytest.raises(RuntimeError):
        s.setup("autre1234")


def test_recover_resets_password(tmp_path):
    s = SecretStore(str(tmp_path))
    code = s.setup("motdepasse8")
    new_code = s.recover(code, "nouveaupass1")
    assert s.verify_password("nouveaupass1")
    assert not s.verify_password("motdepasse8")
    assert new_code != code


def test_recover_wrong_code(tmp_path):
    s = SecretStore(str(tmp_path))
    s.setup("motdepasse8")
    with pytest.raises(ValueError):
        s.recover("mauvais-code", "nouveaupass1")


def test_secret_file_permissions(tmp_path):
    s = SecretStore(str(tmp_path))
    s.setup("motdepasse8")
    mode = os.stat(s.secret_path).st_mode & 0o777
    assert mode == 0o600
