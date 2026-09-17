"""Environment configuration. Never log secrets."""

from __future__ import annotations

import os
from dataclasses import dataclass


ALLOWED_MODES = ("shared", "local")


def _as_bool(value, default=False):
    if value is None:
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def redact_database_url(url):
    if not url or "://" not in url:
        return url or ""
    scheme, rest = url.split("://", 1)
    if "@" not in rest:
        return url
    userinfo, host = rest.split("@", 1)
    if ":" in userinfo:
        user = userinfo.split(":", 1)[0]
        userinfo = "%s:***" % user
    return "%s://%s@%s" % (scheme, userinfo, host)


@dataclass(frozen=True)
class Settings:
    database_url: str
    bind: str
    port: int
    mode: str
    auto_import: bool
    log_level: str

    @classmethod
    def from_env(cls):
        database_url = os.environ.get("KORVENTIS_DGII_DATABASE_URL", "").strip()
        if not database_url:
            raise SystemExit("KORVENTIS_DGII_DATABASE_URL is required")
        mode = os.environ.get("KORVENTIS_DGII_MODE", "local").strip().lower()
        if mode not in ALLOWED_MODES:
            raise SystemExit(
                "KORVENTIS_DGII_MODE must be shared or local, not %r" % mode
            )
        bind = os.environ.get("KORVENTIS_DGII_BIND", "127.0.0.1").strip() or "127.0.0.1"
        try:
            port = int(os.environ.get("KORVENTIS_DGII_PORT", "8080"))
        except ValueError:
            raise SystemExit("KORVENTIS_DGII_PORT must be an integer")
        return cls(
            database_url=database_url,
            bind=bind,
            port=port,
            mode=mode,
            auto_import=_as_bool(os.environ.get("KORVENTIS_DGII_AUTO_IMPORT"), False),
            log_level=os.environ.get("KORVENTIS_DGII_LOG_LEVEL", "INFO").strip()
            or "INFO",
        )
