"""CLI: migrate or serve. Default is serve after applying schema."""

from __future__ import annotations

import logging
import sys

from .config import Settings
from .migrate import apply_migrations
from .server import serve


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    command = argv[0] if argv else "serve"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    settings = Settings.from_env()
    logging.getLogger().setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
    if command == "migrate":
        applied = apply_migrations(settings.database_url)
        print("applied: %s" % (applied or "none"))
        return 0
    if command in ("serve", "run"):
        serve(settings)
        return 0
    raise SystemExit("Unknown command %r (use migrate or serve)" % command)


if __name__ == "__main__":
    raise SystemExit(main())
