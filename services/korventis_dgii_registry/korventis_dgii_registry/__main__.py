"""CLI: migrate, serve, import local ZIP, restore previous version."""

from __future__ import annotations

import argparse
import json
import logging
import sys

from .config import Settings
from .importer import ImportLimits, RegistryImportError, import_zip, restore_previous
from .migrate import apply_migrations
from .server import serve


def _print_result(result):
    payload = {
        "state": result.state,
        "version_id": result.version_id,
        "accepted_count": result.accepted_count,
        "rejected_count": result.rejected_count,
        "warning_count": result.warning_count,
        "duplicate_count": result.duplicate_count,
        "total_rows": result.total_rows,
        "archive_sha256": result.archive_sha256,
    }
    if result.error:
        payload["error"] = result.error
    print(json.dumps(payload, sort_keys=True))


def _cmd_import(settings, argv):
    parser = argparse.ArgumentParser(prog="korventis-dgii-registry import")
    parser.add_argument("--zip", dest="zip_path", help="Path to a local ZIP")
    parser.add_argument("--url", dest="url", help="Remote URL (disabled unless authorized)")
    parser.add_argument("--source", default="local-zip", help="Origin label stored with the version")
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--validate-only",
        action="store_true",
        help="Persist a staging version; do not activate",
    )
    group.add_argument("--activate", action="store_true", help="Activate if integrity checks pass")
    group.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate ZIP/CSV without persistent writes",
    )
    args = parser.parse_args(argv)
    if args.url:
        if not settings.allow_remote:
            raise SystemExit(
                "remote import is disabled; KORVENTIS_DGII_ALLOW_REMOTE is not yes"
            )
        raise SystemExit("remote import is not implemented in this commit")
    if not args.zip_path:
        raise SystemExit("import requires --zip PATH")
    activate = bool(args.activate)
    persist = not bool(args.dry_run)
    limits = ImportLimits(
        min_records=settings.min_records,
        max_reject_ratio=settings.max_reject_ratio,
    )
    result = import_zip(
        settings.conninfo,
        args.zip_path,
        source_label=args.source,
        activate=activate,
        persist=persist,
        limits=limits,
    )
    _print_result(result)
    if result.state in {"failed", "skipped"}:
        return 1
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    command = argv[0] if argv else "serve"
    rest = argv[1:] if argv else []
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    settings = Settings.from_env()
    logging.getLogger().setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
    if command == "migrate":
        applied = apply_migrations(settings)
        print("applied: %s" % (applied or "none"))
        return 0
    if command in ("serve", "run"):
        serve(settings)
        return 0
    if command == "import":
        return _cmd_import(settings, rest)
    if command == "restore-previous":
        try:
            version_id = restore_previous(
                settings.conninfo,
                lock_timeout_ms=settings.restore_lock_timeout_ms,
            )
        except RegistryImportError as exc:
            print(json.dumps({"state": "failed", "error": str(exc)}, sort_keys=True))
            return 1
        print(json.dumps({"state": "success", "version_id": version_id}, sort_keys=True))
        return 0
    raise SystemExit("Unknown command %r (use migrate, serve, import or restore-previous)" % command)


if __name__ == "__main__":
    raise SystemExit(main())
