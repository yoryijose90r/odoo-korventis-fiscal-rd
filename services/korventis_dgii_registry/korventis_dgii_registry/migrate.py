"""Apply versioned SQL migrations. Idempotent. No ZIP download."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

import psycopg


_logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


def migration_files():
    if not MIGRATIONS_DIR.is_dir():
        raise FileNotFoundError("Missing migrations directory: %s" % MIGRATIONS_DIR)
    return sorted(MIGRATIONS_DIR.glob("*.sql"))


def file_checksum(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def apply_migrations(database_url):
    files = migration_files()
    if not files:
        raise RuntimeError("No SQL migrations found")
    applied = []
    with psycopg.connect(database_url, autocommit=False) as conn:
        with conn.cursor() as cur:
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
    return applied


def schema_status(database_url):
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT version FROM schema_migrations
                ORDER BY version
                """
            )
            versions = [row[0] for row in cur.fetchall()]
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
    return {
        "migrations": versions,
        "active_versions": active,
        "registry": "active" if active else "pending",
        "auto_import_enabled": auto_import,
    }
