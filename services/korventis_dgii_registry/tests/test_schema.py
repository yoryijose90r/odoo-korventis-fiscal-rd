"""Real schema tests against PostgreSQL. Does not load the official padrón."""

from __future__ import annotations

import psycopg
import pytest
from psycopg.errors import UniqueViolation

from korventis_dgii_registry.migrate import apply_migrations, schema_status


def _sha(label):
    return ("%s%s" % (label, "0" * 64))[:64]


def test_apply_migrations_is_idempotent(registry_db):
    admin_url = registry_db.rsplit("/", 1)[0] + "/postgres"
    fresh_url = registry_db.rsplit("/", 1)[0] + "/korventis_dgii_fresh"
    with psycopg.connect(admin_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("DROP DATABASE IF EXISTS korventis_dgii_fresh")
            cur.execute("CREATE DATABASE korventis_dgii_fresh")
    first = apply_migrations(fresh_url)
    second = apply_migrations(fresh_url)
    assert first == ["001_initial"]
    assert second == []
    status = schema_status(fresh_url)
    assert status["migrations"] == ["001_initial"]
    assert status["registry"] == "pending"
    assert status["active_versions"] == 0
    assert status["auto_import_enabled"] == "false"


def test_empty_registry_is_pending_not_failure(registry_db):
    status = schema_status(registry_db)
    assert status["registry"] == "pending"
    assert status["active_versions"] == 0


def test_one_active_version_unique_index(registry_db):
    with psycopg.connect(registry_db) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO dgii_rnc_version (
                    name, state, source_url, source_filename, archive_sha256, imported_at
                ) VALUES (
                    'fixture-a', 'active', 'https://example.invalid/a.zip', 'a.zip',
                    %s, now()
                )
                """,
                (_sha("a"),),
            )
            conn.commit()
            with pytest.raises(UniqueViolation):
                cur.execute(
                    """
                    INSERT INTO dgii_rnc_version (
                        name, state, source_url, source_filename, archive_sha256, imported_at
                    ) VALUES (
                        'fixture-b', 'active', 'https://example.invalid/b.zip', 'b.zip',
                        %s, now()
                    )
                    """,
                    (_sha("b"),),
                )
                conn.commit()
            conn.rollback()
            cur.execute(
                """
                INSERT INTO dgii_rnc_version (
                    name, state, source_url, source_filename, archive_sha256, imported_at
                ) VALUES (
                    'fixture-staging', 'staging', 'https://example.invalid/c.zip', 'c.zip',
                    %s, now()
                )
                """,
                (_sha("c"),),
            )
            conn.commit()
            cur.execute("SELECT count(*) FROM dgii_rnc_version WHERE state = 'active'")
            assert cur.fetchone()[0] == 1
            cur.execute("SELECT count(*) FROM dgii_rnc_version WHERE state = 'staging'")
            assert cur.fetchone()[0] == 1


def test_archive_sha256_is_unique(registry_db):
    sha = _sha("dup")
    with psycopg.connect(registry_db) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO dgii_rnc_version (
                    name, state, source_url, source_filename, archive_sha256, imported_at
                ) VALUES (
                    'sha-1', 'staging', 'https://example.invalid/d.zip', 'd.zip',
                    %s, now()
                )
                """,
                (sha,),
            )
            conn.commit()
            with pytest.raises(UniqueViolation):
                cur.execute(
                    """
                    INSERT INTO dgii_rnc_version (
                        name, state, source_url, source_filename, archive_sha256, imported_at
                    ) VALUES (
                        'sha-2', 'staging', 'https://example.invalid/e.zip', 'e.zip',
                        %s, now()
                    )
                    """,
                    (sha,),
                )
                conn.commit()


def test_rnc_unique_per_version_and_no_test_context_column(registry_db):
    with psycopg.connect(registry_db) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT column_name FROM information_schema.columns
                 WHERE table_schema = 'public'
                """
            )
            columns = {row[0] for row in cur.fetchall()}
            assert "korventis_dgii_test_version_id" not in columns
            cur.execute(
                """
                INSERT INTO dgii_rnc_version (
                    name, state, source_url, source_filename, archive_sha256, imported_at
                ) VALUES (
                    'rnc-v', 'staging', 'https://example.invalid/f.zip', 'f.zip',
                    %s, now()
                )
                RETURNING id
                """,
                (_sha("f"),),
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
            with pytest.raises(UniqueViolation):
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
