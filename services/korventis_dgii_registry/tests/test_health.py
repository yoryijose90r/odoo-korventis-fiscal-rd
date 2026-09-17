"""Config and health payload tests. No ZIP download. No secrets in HTTP."""

from __future__ import annotations

import json
import threading
from http.client import HTTPConnection

import pytest

from korventis_dgii_registry.config import Settings
from korventis_dgii_registry.migrate import probe_readiness
from korventis_dgii_registry.server import make_server
from tests.conftest import connect


FORBIDDEN_HEALTH_FRAGMENTS = (
    "postgresql://",
    "postgres://",
    "PGPASSWORD",
    "Traceback",
    "File \"",
    "pghost",
    "password",
    "exception",
    "/app/",
    "OperationalError",
)


def _settings(conninfo, monkeypatch, mode="local", port="0", host=None, pgport=None):
    monkeypatch.setenv("KORVENTIS_DGII_PGHOST", host or conninfo["host"])
    monkeypatch.setenv("KORVENTIS_DGII_PGPORT", str(pgport or conninfo["port"]))
    monkeypatch.setenv("KORVENTIS_DGII_PGUSER", conninfo["user"])
    monkeypatch.setenv("KORVENTIS_DGII_PGPASSWORD", conninfo["password"])
    monkeypatch.setenv("KORVENTIS_DGII_PGDATABASE", conninfo["dbname"])
    monkeypatch.setenv("KORVENTIS_DGII_MODE", mode)
    monkeypatch.setenv("KORVENTIS_DGII_BIND", "127.0.0.1")
    monkeypatch.setenv("KORVENTIS_DGII_PORT", str(port))
    return Settings.from_env()


def _assert_no_secrets(payload, conninfo):
    raw = json.dumps(payload)
    for fragment in FORBIDDEN_HEALTH_FRAGMENTS:
        assert fragment.lower() not in raw.lower()
    assert conninfo["password"] not in raw
    assert conninfo["user"] not in raw
    assert str(conninfo["host"]) not in raw
    assert "error" not in payload
    assert "database" not in payload
    assert "bind" not in payload


def test_settings_require_pg_params(monkeypatch):
    for name in (
        "KORVENTIS_DGII_PGHOST",
        "KORVENTIS_DGII_PGUSER",
        "KORVENTIS_DGII_PGPASSWORD",
        "KORVENTIS_DGII_PGDATABASE",
    ):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(SystemExit):
        Settings.from_env()


def test_settings_reject_unknown_mode(monkeypatch):
    monkeypatch.setenv("KORVENTIS_DGII_PGHOST", "localhost")
    monkeypatch.setenv("KORVENTIS_DGII_PGUSER", "korventis_dgii")
    monkeypatch.setenv("KORVENTIS_DGII_PGPASSWORD", "unused")
    monkeypatch.setenv("KORVENTIS_DGII_PGDATABASE", "korventis_dgii")
    monkeypatch.setenv("KORVENTIS_DGII_MODE", "production")
    with pytest.raises(SystemExit):
        Settings.from_env()


def test_settings_repr_omits_password(monkeypatch):
    monkeypatch.setenv("KORVENTIS_DGII_PGHOST", "localhost")
    monkeypatch.setenv("KORVENTIS_DGII_PGUSER", "korventis_dgii")
    monkeypatch.setenv("KORVENTIS_DGII_PGPASSWORD", "unused-secret")
    monkeypatch.setenv("KORVENTIS_DGII_PGDATABASE", "korventis_dgii")
    monkeypatch.setenv("KORVENTIS_DGII_MODE", "local")
    rendered = repr(Settings.from_env())
    assert "unused-secret" not in rendered
    assert "pgpassword" not in rendered.lower()


def test_health_ready_pending_without_active_version(db_conninfo, monkeypatch):
    settings = _settings(db_conninfo, monkeypatch)
    payload = probe_readiness(settings)
    assert payload["status"] == "ok"
    assert payload["postgres"] is True
    assert payload["schema"] is True
    assert payload["registry"] == "pending"
    _assert_no_secrets(payload, db_conninfo)


def test_http_health_endpoints_hide_secrets(db_conninfo, monkeypatch):
    settings = _settings(db_conninfo, monkeypatch, mode="shared")
    httpd = make_server(settings)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = httpd.server_address[:2]
        conn = HTTPConnection(host, port, timeout=5)
        conn.request("GET", "/health")
        live_resp = conn.getresponse()
        live = json.loads(live_resp.read().decode("utf-8"))
        assert live_resp.status == 200
        assert live == {"status": "ok", "service": "korventis-dgii-registry"}
        _assert_no_secrets(live, db_conninfo)
        conn.request("GET", "/health/ready")
        ready_resp = conn.getresponse()
        ready = json.loads(ready_resp.read().decode("utf-8"))
        assert ready_resp.status == 200
        assert ready["status"] == "ok"
        assert ready["registry"] == "pending"
        assert set(ready) == {"status", "postgres", "schema", "registry"}
        _assert_no_secrets(ready, db_conninfo)
        conn.request("GET", "/lookup")
        missing = conn.getresponse()
        missing_body = json.loads(missing.read().decode("utf-8"))
        assert missing.status == 404
        assert "path" not in missing_body
        conn.close()
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_ready_reports_active_registry(db_conninfo, monkeypatch):
    settings = _settings(db_conninfo, monkeypatch)
    with connect(db_conninfo) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO dgii_rnc_version (
                    name, state, source_url, source_filename, archive_sha256,
                    imported_at, record_count
                ) VALUES (
                    'active-v', 'active', 'https://example.invalid/h.zip', 'h.zip',
                    %s, now(), 1
                )
                RETURNING id
                """,
                (("h" + "0" * 64)[:64],),
            )
            version_id = cur.fetchone()[0]
            cur.execute(
                """
                INSERT INTO dgii_rnc (
                    version_id, rnc, rnc_normalizado, razon_social,
                    razon_social_normalizada, estado, regimen_pago, fecha_importacion
                ) VALUES (
                    %s, '131098193', '131098193', 'ACME SRL', 'ACME SRL',
                    'ACTIVO', 'NORMAL', now()
                )
                """,
                (version_id,),
            )
        conn.commit()
    payload = probe_readiness(settings)
    assert payload["status"] == "ok"
    assert payload["registry"] == "active"
    _assert_no_secrets(payload, db_conninfo)


def test_ready_staging_with_rows_is_pending(db_conninfo, monkeypatch):
    settings = _settings(db_conninfo, monkeypatch)
    with connect(db_conninfo) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO dgii_rnc_version (
                    name, state, source_url, source_filename, archive_sha256,
                    imported_at, record_count
                ) VALUES (
                    'official-staging', 'staging', 'https://example.invalid/s.zip', 's.zip',
                    %s, now(), 2
                )
                RETURNING id
                """,
                (("s" + "1" * 64)[:64],),
            )
            version_id = cur.fetchone()[0]
            cur.execute(
                """
                INSERT INTO dgii_rnc (
                    version_id, rnc, rnc_normalizado, razon_social,
                    razon_social_normalizada, estado, regimen_pago, fecha_importacion
                ) VALUES
                    (%s, '131098191', '131098191', 'STAGING A', 'STAGING A',
                     'ACTIVO', 'NORMAL', now()),
                    (%s, '131098192', '131098192', 'STAGING B', 'STAGING B',
                     'ACTIVO', 'NORMAL', now())
                """,
                (version_id, version_id),
            )
        conn.commit()
    payload = probe_readiness(settings)
    assert payload["status"] == "ok"
    assert payload["registry"] == "pending"
    _assert_no_secrets(payload, db_conninfo)


def test_ready_empty_active_is_unavailable(db_conninfo, monkeypatch):
    settings = _settings(db_conninfo, monkeypatch)
    with connect(db_conninfo) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO dgii_rnc_version (
                    name, state, source_url, source_filename, archive_sha256,
                    imported_at, record_count
                ) VALUES (
                    'empty-active', 'active', 'https://example.invalid/i.zip', 'i.zip',
                    %s, now(), 1
                )
                """,
                (("i" + "0" * 64)[:64],),
            )
        conn.commit()
    payload = probe_readiness(settings)
    assert payload["status"] == "unready"
    assert payload["schema"] is True
    assert payload["registry"] == "unavailable"
    _assert_no_secrets(payload, db_conninfo)


def test_ready_unready_without_postgres_hides_exceptions(db_conninfo, monkeypatch):
    settings = _settings(db_conninfo, monkeypatch, pgport=1)
    payload = probe_readiness(settings)
    assert payload["status"] == "unready"
    assert payload["postgres"] is False
    assert payload["schema"] is False
    assert payload["registry"] == "unavailable"
    _assert_no_secrets(payload, db_conninfo)
    raw = json.dumps(payload)
    assert "could not connect" not in raw.lower()
    assert "connection refused" not in raw.lower()


def test_ready_unready_when_schema_missing(db_conninfo, monkeypatch):
    from tests.conftest import recreate_database

    fresh = recreate_database(db_conninfo, "korventis_dgii_noschema")
    settings = _settings(fresh, monkeypatch)
    payload = probe_readiness(settings)
    assert payload["status"] == "unready"
    assert payload["postgres"] is True
    assert payload["schema"] is False
    assert payload["registry"] == "unavailable"
    _assert_no_secrets(payload, fresh)
