"""Apply versioned SQL migrations. Idempotent. No ZIP download."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

import psycopg


_logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"

# Session/transaction advisory lock for schema changes. int4-safe.
MIGRATION_LOCK_KEY = 1262760519

REQUIRED_MIGRATIONS = ("001_initial", "002_hardening")


def migration_files():
    if not MIGRATIONS_DIR.is_dir():
        raise FileNotFoundError("Missing migrations directory")
    return sorted(MIGRATIONS_DIR.glob("*.sql"))


def file_checksum(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _conninfo(target):
    if hasattr(target, "conninfo"):
        return target.conninfo
    return target


def connect(target):
    return psycopg.connect(**_conninfo(target))


def apply_migrations(target):
    files = migration_files()
    if not files:
        raise RuntimeError("No SQL migrations found")
    applied = []
    with connect(target) as conn:
        conn.autocommit = False
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT pg_advisory_xact_lock(%s)", (MIGRATION_LOCK_KEY,))
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS schema_migrations (
                        version TEXT PRIMARY KEY,
                        checksum TEXT NOT NULL,
                        applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    )
                    """
                )
                for path in files:
                    version = path.stem
                    checksum = file_checksum(path)
                    cur.execute(
                        "SELECT checksum FROM schema_migrations WHERE version = %s",
                        (version,),
                    )
                    row = cur.fetchone()
                    if row:
                        if row[0] != checksum:
                            raise RuntimeError(
                                "Migration %s checksum mismatch; refusing to apply"
                                % version
                            )
                        continue
                    _logger.info("Applying migration %s", version)
                    cur.execute(path.read_text(encoding="utf-8"))
                    cur.execute(
                        """
                        INSERT INTO schema_migrations (version, checksum)
                        VALUES (%s, %s)
                        ON CONFLICT (version) DO NOTHING
                        """,
                        (version, checksum),
                    )
                    applied.append(version)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return applied


def schema_status(target):
    with connect(target) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('public.schema_migrations')")
            if cur.fetchone()[0] is None:
                return {
                    "schema": False,
                    "migrations": [],
                    "active_versions": 0,
                    "registry": "unavailable",
                    "auto_import_enabled": "false",
                }
            cur.execute("SELECT version FROM schema_migrations ORDER BY version")
            versions = [row[0] for row in cur.fetchall()]
            missing = [name for name in REQUIRED_MIGRATIONS if name not in versions]
            cur.execute("SELECT to_regclass('public.dgii_rnc_version')")
            has_registry = cur.fetchone()[0] is not None
            active = 0
            auto_import = "false"
            if has_registry:
                cur.execute(
                    """
                    SELECT count(*) FROM dgii_rnc_version WHERE state = 'active'
                    """
                )
                active = int(cur.fetchone()[0])
                cur.execute(
                    """
                    SELECT value FROM dgii_service_settings
                     WHERE key = 'auto_import_enabled'
                    """
                )
                row = cur.fetchone()
                auto_import = row[0] if row else "false"
            schema_ok = not missing and has_registry
            if not schema_ok:
                registry = "unavailable"
            elif active:
                registry = "active"
            else:
                registry = "pending"
    return {
        "schema": schema_ok,
        "migrations": versions,
        "active_versions": active,
        "registry": registry,
        "auto_import_enabled": auto_import,
    }


def probe_readiness(target):
    try:
        status = schema_status(target)
    except Exception as exc:  # noqa: BLE001
        _logger.error("readiness probe failed (%s)", type(exc).__name__)
        return {
            "status": "unready",
            "postgres": False,
            "schema": False,
            "registry": "unavailable",
        }
    if not status["schema"]:
        return {
            "status": "unready",
            "postgres": True,
            "schema": False,
            "registry": "unavailable",
        }
    return {
        "status": "ok",
        "postgres": True,
        "schema": True,
        "registry": status["registry"],
    }
