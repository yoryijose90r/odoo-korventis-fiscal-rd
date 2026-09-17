"""Environment configuration. Never log secrets or connection strings."""

from __future__ import annotations

import os
from dataclasses import dataclass


ALLOWED_MODES = ("shared", "local")


def _as_bool(value, default=False):
    if value is None:
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _require(name):
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit("%s is required" % name)
    return value


@dataclass(frozen=True)
class Settings:
    pghost: str
    pgport: int
    pguser: str
    pgpassword: str
    pgdatabase: str
    bind: str
    port: int
    mode: str
    auto_import: bool
    log_level: str
    allow_remote: bool
    min_records: int
    max_reject_ratio: float
    restore_lock_timeout_ms: int

    def __repr__(self):
        return (
            "Settings(pghost=%r, pgport=%r, pguser=%r, pgdatabase=%r, "
            "bind=%r, port=%r, mode=%r)"
            % (
                self.pghost,
                self.pgport,
                self.pguser,
                self.pgdatabase,
                self.bind,
                self.port,
                self.mode,
            )
        )

    @property
    def conninfo(self):
        return {
            "host": self.pghost,
            "port": self.pgport,
            "user": self.pguser,
            "password": self.pgpassword,
            "dbname": self.pgdatabase,
        }

    @classmethod
    def from_env(cls):
        mode = os.environ.get("KORVENTIS_DGII_MODE", "local").strip().lower()
        if mode not in ALLOWED_MODES:
            raise SystemExit(
                "KORVENTIS_DGII_MODE must be shared or local, not %r" % mode
            )
        bind = os.environ.get("KORVENTIS_DGII_BIND", "127.0.0.1").strip() or "127.0.0.1"
        try:
            port = int(os.environ.get("KORVENTIS_DGII_PORT", "8080"))
            pgport = int(os.environ.get("KORVENTIS_DGII_PGPORT", "5432"))
            min_records = int(os.environ.get("KORVENTIS_DGII_IMPORT_MIN_RECORDS", "1"))
            max_reject_ratio = float(
                os.environ.get("KORVENTIS_DGII_IMPORT_MAX_REJECT_RATIO", "0.001")
            )
            restore_lock_timeout_ms = int(
                os.environ.get("KORVENTIS_DGII_RESTORE_LOCK_TIMEOUT_MS", "5000")
            )
        except ValueError:
            raise SystemExit("numeric KORVENTIS_DGII_* settings are invalid")
        return cls(
            pghost=_require("KORVENTIS_DGII_PGHOST"),
            pgport=pgport,
            pguser=_require("KORVENTIS_DGII_PGUSER"),
            pgpassword=_require("KORVENTIS_DGII_PGPASSWORD"),
            pgdatabase=_require("KORVENTIS_DGII_PGDATABASE"),
            bind=bind,
            port=port,
            mode=mode,
            auto_import=_as_bool(os.environ.get("KORVENTIS_DGII_AUTO_IMPORT"), False),
            log_level=os.environ.get("KORVENTIS_DGII_LOG_LEVEL", "INFO").strip()
            or "INFO",
            allow_remote=_as_bool(os.environ.get("KORVENTIS_DGII_ALLOW_REMOTE"), False),
            min_records=min_records,
            max_reject_ratio=max_reject_ratio,
            restore_lock_timeout_ms=restore_lock_timeout_ms,
        )
