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
    assert "state <> 'active' OR record_count > 0" in text


def test_activate_does_not_rewrite_record_count():
    text = (ROOT / "korventis_dgii_registry" / "importer.py").read_text(encoding="utf-8")
    assert "SET record_count = %s" not in text
    assert "row count does not match record_count" in text
    assert "uncompressed size exceeded during read" in (
        ROOT / "korventis_dgii_registry" / "archive.py"
    ).read_text(encoding="utf-8")


def test_import_cli_keeps_dry_run_validate_only_and_activate_exclusive():
    text = (ROOT / "korventis_dgii_registry" / "__main__.py").read_text(encoding="utf-8")
    assert "add_mutually_exclusive_group()" in text
    assert "--validate-only" in text
    assert "--activate" in text
    assert "--dry-run" in text
    assert "persist = not bool(args.dry_run)" in text
    assert "activate = bool(args.activate)" in text
