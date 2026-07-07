import json
import pytest
from comroster.services.netconfig import NetConfig, validate


def test_default_is_link_local(tmp_path):
    nc = NetConfig(str(tmp_path))
    assert nc.load() == {"mode": "link-local", "link": "ethernet"}


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


# --- Lien Wi-Fi / Ethernet (design 2026-07-06) ---

def _wifi(mode="dhcp", ssid="REGIE", psk="motdepasse-wifi", **kw):
    cfg = {"link": "wifi", "mode": mode, "wifi": {"ssid": ssid, "psk": psk}}
    cfg.update(kw)
    return cfg

def test_validate_wifi_dhcp_ok():
    ok, err = validate(_wifi())
    assert ok and err is None

def test_validate_wifi_static_ok():
    ok, err = validate(_wifi(mode="static", address="192.168.42.10", prefix=24))
    assert ok and err is None

def test_validate_wifi_rejects_link_local():
    ok, err = validate(_wifi(mode="link-local"))
    assert not ok

def test_validate_wifi_requires_ssid():
    ok, _ = validate(_wifi(ssid=""))
    assert not ok
    ok, _ = validate(_wifi(ssid="x" * 33))
    assert not ok

def test_validate_wifi_psk_bounds():
    ok, _ = validate(_wifi(psk="court"))         # < 8 : WPA2 impossible
    assert not ok
    ok, _ = validate(_wifi(psk="x" * 64))        # > 63
    assert not ok
    ok, _ = validate({"link": "wifi", "mode": "dhcp", "wifi": {"ssid": "R"}})  # psk absent
    assert not ok

def test_validate_rejects_bad_link():
    ok, _ = validate({"link": "bluetooth", "mode": "dhcp"})
    assert not ok

def test_load_legacy_file_defaults_to_ethernet(tmp_path):
    # Rétro-compat : un network.json d'avant (sans `link`) reste valide
    import json as _json
    nc = NetConfig(str(tmp_path))
    with open(nc.path, "w") as fh:
        _json.dump({"mode": "static", "address": "192.168.1.50", "prefix": 24}, fh)
    assert nc.load()["link"] == "ethernet"

def test_save_wifi_keeps_existing_psk_when_omitted(tmp_path):
    # L'UI ne renvoie jamais le psk : un PUT sans psk conserve celui déjà enregistré
    nc = NetConfig(str(tmp_path))
    nc.save(_wifi(psk="premier-mdp-wifi"))
    nc.save({"link": "wifi", "mode": "dhcp", "wifi": {"ssid": "REGIE"}})
    assert nc.load()["wifi"]["psk"] == "premier-mdp-wifi"

def test_save_wifi_without_any_psk_rejected(tmp_path):
    import pytest as _pytest
    nc = NetConfig(str(tmp_path))
    with _pytest.raises(ValueError):
        nc.save({"link": "wifi", "mode": "dhcp", "wifi": {"ssid": "REGIE"}})
