"""Santé du boîtier : parseurs purs (sans Pi) + endpoint."""
import pytest

from comroster.services import health


def test_parse_thermal():
    assert health.parse_thermal("58312\n") == 58.3
    assert health.parse_thermal("bad") is None
    assert health.parse_thermal(None) is None


def test_parse_meminfo():
    raw = "MemTotal:        1000000 kB\nMemFree: 200000 kB\nMemAvailable:   600000 kB\n"
    m = health.parse_meminfo(raw)
    assert m["total"] == 1000000 * 1024
    assert m["available"] == 600000 * 1024
    assert m["used"] == 400000 * 1024


def test_parse_meminfo_incomplet():
    assert health.parse_meminfo("MemTotal: 1000 kB\n") is None      # pas de MemAvailable
    assert health.parse_meminfo("") is None


def test_parse_throttled():
    # sous-tension actuelle (bit 0) + throttling passé (bit 18)
    flags = health.parse_throttled("throttled=0x40001")
    assert flags["undervoltage_now"] is True
    assert flags["throttled_now"] is False
    assert flags["throttled_past"] is True
    assert health.parse_throttled("throttled=0x0")["undervoltage_now"] is False
    assert health.parse_throttled("throttled=zzz") is None      # non hexadécimal


def test_parse_uptime():
    assert health.parse_uptime("1234.56 5678.9") == 1234
    assert health.parse_uptime("") is None


# ---------- endpoint ----------

@pytest.fixture
def auth_client(client):
    client.post("/admin/setup", data={"password": "motdepasse8"})
    return client


def test_health_page_requiert_session(client):
    assert client.get("/admin/health").status_code in (302, 401, 403)


def test_api_health_requiert_session(client):
    assert client.get("/api/health").status_code in (302, 401, 403)


def test_api_health_snapshot_structure(auth_client):
    d = auth_client.get("/api/health").get_json()
    # Toujours présents (tolérants : valeur possiblement None hors Pi).
    for key in ("time", "cpu", "memory", "disk", "uptime", "displays", "antenna", "published"):
        assert key in d
    assert "temp_c" in d["cpu"] and "load" in d["cpu"]
    assert d["disk"] is not None                 # shutil.disk_usage marche partout
    assert d["uptime"]["app_s"] >= 0
    assert d["displays"] == 0                     # aucun afficheur SSE sous tests
