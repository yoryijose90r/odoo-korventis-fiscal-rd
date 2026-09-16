"""Cron scheduling in America/Santo_Domingo, stored as naive UTC for Odoo."""

from datetime import datetime, timedelta, timezone


IMPORT_HOUR = 1
IMPORT_MINUTE = 0
AST = timezone(timedelta(hours=-4))


def santo_domingo_tz():
    """Return Santo Domingo tzinfo without using the operating-system zone."""
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo("America/Santo_Domingo")
    except Exception:
        try:
            import pytz

            return pytz.timezone("America/Santo_Domingo")
        except Exception:
            return AST


def _to_santo_domingo(moment):
    tz = santo_domingo_tz()
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    converted = moment.astimezone(tz)
    offset = converted.utcoffset() or timedelta(hours=-4)
    naive = converted.replace(tzinfo=None)
    return naive.replace(tzinfo=timezone(offset))


def next_santo_domingo_import(now=None):
    """Return the next 01:00 America/Santo_Domingo as naive UTC datetime."""
    current = _to_santo_domingo(now or datetime.now(tz=timezone.utc))
    candidate = current.replace(
        hour=IMPORT_HOUR,
        minute=IMPORT_MINUTE,
        second=0,
        microsecond=0,
    )
    if candidate <= current:
        candidate += timedelta(days=1)
    return candidate.astimezone(timezone.utc).replace(tzinfo=None)
