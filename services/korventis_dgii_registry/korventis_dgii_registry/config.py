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
        except ValueError:
            raise SystemExit("KORVENTIS_DGII_PORT and KORVENTIS_DGII_PGPORT must be integers")
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
        )
