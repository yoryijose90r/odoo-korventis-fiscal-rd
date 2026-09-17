"""Config and health payload tests. No ZIP download."""

from __future__ import annotations

import json
import threading
from http.client import HTTPConnection

import pytest

from korventis_dgii_registry.config import Settings, redact_database_url
from korventis_dgii_registry.server import build_health_payload, make_server


def test_redact_database_url():
    raw = "postgresql://korventis_dgii:super-secret@postgres:5432/korventis_dgii"
    assert "super-secret" not in redact_database_url(raw)
    assert "korventis_dgii:***" in redact_database_url(raw)


def test_settings_require_database_url(monkeypatch):
    monkeypatch.delenv("KORVENTIS_DGII_DATABASE_URL", raising=False)
    with pytest.raises(SystemExit):
        Settings.from_env()


def test_settings_reject_unknown_mode(monkeypatch):
    monkeypatch.setenv("KORVENTIS_DGII_DATABASE_URL", "postgresql://x:y@localhost/db")
    monkeypatch.setenv("KORVENTIS_DGII_MODE", "production")
    with pytest.raises(SystemExit):
        Settings.from_env()


def test_health_ready_pending_without_active_version(registry_db, monkeypatch):
    monkeypatch.setenv("KORVENTIS_DGII_DATABASE_URL", registry_db)
    monkeypatch.setenv("KORVENTIS_DGII_MODE", "local")
    monkeypatch.setenv("KORVENTIS_DGII_BIND", "127.0.0.1")
    monkeypatch.setenv("KORVENTIS_DGII_PORT", "0")
    settings = Settings.from_env()
    payload = build_health_payload(settings)
    assert payload["status"] == "ok"
    assert payload["registry"] == "pending"
    assert payload["postgres"] is True
    assert "super-secret" not in json.dumps(payload)


def test_http_health_endpoints(registry_db, monkeypatch):
    monkeypatch.setenv("KORVENTIS_DGII_DATABASE_URL", registry_db)
    monkeypatch.setenv("KORVENTIS_DGII_MODE", "shared")
    monkeypatch.setenv("KORVENTIS_DGII_BIND", "127.0.0.1")
    monkeypatch.setenv("KORVENTIS_DGII_PORT", "0")
    settings = Settings.from_env()
    httpd = make_server(settings)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = httpd.server_address[:2]
        conn = HTTPConnection(host, port, timeout=5)
        conn.request("GET", "/health")
        live = json.loads(conn.getresponse().read().decode("utf-8"))
        assert live["status"] == "ok"
        conn.request("GET", "/health/ready")
        ready = json.loads(conn.getresponse().read().decode("utf-8"))
        assert ready["status"] == "ok"
        assert ready["registry"] == "pending"
        assert ready["mode"] == "shared"
        conn.request("GET", "/lookup")
        missing = conn.getresponse()
        assert missing.status == 404
        conn.close()
    finally:
        httpd.shutdown()
        httpd.server_close()
