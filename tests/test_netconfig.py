import json
import pytest
from comroster.services.netconfig import NetConfig, validate


def test_default_is_link_local(tmp_path):
    nc = NetConfig(str(tmp_path))
    assert nc.load() == {"mode": "link-local"}


def test_validate_accepts_static_without_gateway():
    ok, err = validate({"mode": "static", "address": "192.168.1.50", "prefix": 24})
    assert ok and err is None          # switch-only : passerelle facultative


def test_validate_rejects_bad_ip():
    ok, err = validate({"mode": "static", "address": "999.1.1.1", "prefix": 24})
    assert not ok and "IP" in err


def test_validate_rejects_bad_prefix():
    ok, _ = validate({"mode": "static", "address": "192.168.1.50", "prefix": 40})
    assert not ok


def test_validate_gateway_must_be_in_subnet():
    ok, err = validate({"mode": "static", "address": "192.168.1.50", "prefix": 24,
                        "gateway": "10.0.0.1"})
    assert not ok and "sous-réseau" in err


def test_validate_accepts_gateway_in_subnet():
    ok, err = validate({"mode": "static", "address": "192.168.1.50", "prefix": 24,
                        "gateway": "192.168.1.1", "dns": ["192.168.1.1"]})
    assert ok and err is None


def test_validate_rejects_bad_mode():
    ok, _ = validate({"mode": "wifi"})
    assert not ok


def test_save_persists_and_validates(tmp_path):
    nc = NetConfig(str(tmp_path))
    nc.save({"mode": "static", "address": "192.168.1.50", "prefix": 24})
    assert json.load(open(nc.path))["address"] == "192.168.1.50"
    assert nc.load()["mode"] == "static"


def test_save_rejects_invalid(tmp_path):
    nc = NetConfig(str(tmp_path))
    with pytest.raises(ValueError):
        nc.save({"mode": "static", "address": "nope"})
