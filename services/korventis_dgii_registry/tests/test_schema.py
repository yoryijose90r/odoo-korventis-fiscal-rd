"""Real schema tests against PostgreSQL. Does not load the official padrón."""

from __future__ import annotations

import pytest
from psycopg.errors import CheckViolation, UniqueViolation

from korventis_dgii_registry.migrate import apply_migrations, schema_status
from tests.conftest import connect, recreate_database


def _sha(label):
    return ("%s%s" % (label, "0" * 64))[:64]


def test_apply_migrations_is_idempotent(db_conninfo):
    fresh = recreate_database(db_conninfo, "korventis_dgii_fresh")
    first = apply_migrations(fresh)
    second = apply_migrations(fresh)
    assert first == ["001_initial", "002_hardening", "003_importer"]
    assert second == []
    status = schema_status(fresh)
    assert status["migrations"] == ["001_initial", "002_hardening", "003_importer"]
    assert status["schema"] is True
    assert status["registry"] == "pending"
    assert status["active_versions"] == 0
    assert status["auto_import_enabled"] == "false"


def test_empty_registry_is_pending_not_failure(db_conninfo):
    status = schema_status(db_conninfo)
    assert status["schema"] is True
    assert status["registry"] == "pending"
    assert status["active_versions"] == 0


def test_one_active_version_unique_index(db_conninfo):
    with connect(db_conninfo) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO dgii_rnc_version (
                    name, state, source_url, source_filename, archive_sha256, imported_at, record_count
                ) VALUES (
                    'fixture-a', 'active', 'https://example.invalid/a.zip', 'a.zip',
                    %s, now(), 1
                )
                """,
                (_sha("a"),),
            )
            conn.commit()
            with pytest.raises(UniqueViolation):
                cur.execute(
                    """
                    INSERT INTO dgii_rnc_version (
                        name, state, source_url, source_filename, archive_sha256, imported_at, record_count
                    ) VALUES (
                        'fixture-b', 'active', 'https://example.invalid/b.zip', 'b.zip',
                        %s, now(), 1
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


def test_archive_sha256_is_unique(db_conninfo):
    sha = _sha("dup")
    with connect(db_conninfo) as conn:
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


def test_rnc_unique_per_version_and_no_test_context_column(db_conninfo):
    with connect(db_conninfo) as conn:
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


def test_rnc_normalizado_unique_preserves_leading_zeros_and_rejects_blank(db_conninfo):
    with connect(db_conninfo) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO dgii_rnc_version (
                    name, state, source_url, source_filename, archive_sha256, imported_at
                ) VALUES (
                    'rnc-norm', 'staging', 'https://example.invalid/g.zip', 'g.zip',
                    %s, now()
                )
                RETURNING id
                """,
                (_sha("g"),),
            )
            version_id = cur.fetchone()[0]
            cur.execute(
                """
                INSERT INTO dgii_rnc (
                    version_id, rnc, rnc_normalizado, razon_social,
                    razon_social_normalizada, estado, regimen_pago, fecha_importacion
                ) VALUES (
                    %s, '012345678', '012345678', 'CERO SRL', 'CERO SRL',
                    'ACTIVO', 'NORMAL', now()
                )
                """,
                (version_id,),
            )
            conn.commit()
            cur.execute(
                """
                SELECT rnc_normalizado FROM dgii_rnc
                 WHERE version_id = %s AND rnc_normalizado = %s
                """,
                (version_id, "012345678"),
            )
            stored = cur.fetchone()[0]
            assert stored == "012345678"
            assert stored != "12345678"
            with pytest.raises(UniqueViolation):
                cur.execute(
                    """
                    INSERT INTO dgii_rnc (
                        version_id, rnc, rnc_normalizado, razon_social,
                        razon_social_normalizada, estado, regimen_pago, fecha_importacion
                    ) VALUES (
                        %s, 'RNC-012345678', '012345678', 'CERO SRL', 'CERO SRL',
                        'ACTIVO', 'NORMAL', now()
                    )
                    """,
                    (version_id,),
                )
                conn.commit()
            conn.rollback()
            with pytest.raises(CheckViolation):
                cur.execute(
                    """
                    INSERT INTO dgii_rnc (
                        version_id, rnc, rnc_normalizado, razon_social,
                        razon_social_normalizada, estado, regimen_pago, fecha_importacion
                    ) VALUES (
                        %s, ' ', '131000001', 'BLANK', 'BLANK',
                        'ACTIVO', 'NORMAL', now()
                    )
                    """,
                    (version_id,),
                )
                conn.commit()
            conn.rollback()
            with pytest.raises(CheckViolation):
                cur.execute(
                    """
                    INSERT INTO dgii_rnc (
                        version_id, rnc, rnc_normalizado, razon_social,
                        razon_social_normalizada, estado, regimen_pago, fecha_importacion
                    ) VALUES (
                        %s, '131000001', '', 'BLANKN', 'BLANKN',
                        'ACTIVO', 'NORMAL', now()
                    )
                    """,
                    (version_id,),
                )
                conn.commit()
