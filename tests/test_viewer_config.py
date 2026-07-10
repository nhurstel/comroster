import pytest
from comroster.services.viewer import ViewerConfig


def test_default_is_empty(tmp_path):
    vc = ViewerConfig(str(tmp_path))
    assert vc.load() == {"server_ip": "", "server_port": 8080}
    assert vc.display_url() is None
    assert vc.health_url() is None


def test_save_and_urls(tmp_path):
    vc = ViewerConfig(str(tmp_path))
    vc.save({"server_ip": "192.168.42.10", "server_port": 8080})
    assert vc.load()["server_ip"] == "192.168.42.10"
    assert vc.display_url() == "http://192.168.42.10:8080/display"
    assert vc.health_url() == "http://192.168.42.10:8080/healthz"


def test_save_rejects_bad_ip(tmp_path):
    vc = ViewerConfig(str(tmp_path))
    with pytest.raises(ValueError):
        vc.save({"server_ip": "pas-une-ip", "server_port": 8080})


def test_save_rejects_bad_port(tmp_path):
    vc = ViewerConfig(str(tmp_path))
    with pytest.raises(ValueError):
        vc.save({"server_ip": "192.168.42.10", "server_port": 70000})


def test_corrupt_file_falls_back_to_default(tmp_path):
    vc = ViewerConfig(str(tmp_path))
    with open(vc.path, "w") as fh:
        fh.write("{ pas du json")
    assert vc.load() == {"server_ip": "", "server_port": 8080}
