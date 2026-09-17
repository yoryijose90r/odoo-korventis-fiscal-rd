"""Package invariants for commit 1."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCAN_DIRS = (ROOT / "korventis_dgii_registry", ROOT / "migrations")
FORBIDDEN = "korventis_dgii_test_version_id"


def test_service_does_not_include_odoo_test_version_context():
    hits = []
    for base in SCAN_DIRS:
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix not in {".py", ".sql"}:
                continue
            if FORBIDDEN in path.read_text(encoding="utf-8"):
                hits.append(str(path.relative_to(ROOT)))
    assert hits == [], "test-only Odoo context leaked into the service: %s" % hits


def test_auto_import_defaults_false_in_sql():
    sql = (ROOT / "migrations" / "001_initial.sql").read_text(encoding="utf-8")
    assert "('auto_import_enabled', 'false')" in sql


def test_hardening_migration_exists():
    path = ROOT / "migrations" / "002_hardening.sql"
    text = path.read_text(encoding="utf-8")
    assert "dgii_rnc_version_rnc_normalizado_uidx" in text
    assert "dgii_rnc_rnc_not_blank" in text


def test_importer_migration_exists():
    text = (ROOT / "migrations" / "003_importer.sql").read_text(encoding="utf-8")
    assert "dgii_rnc_version_active_has_records" in text
