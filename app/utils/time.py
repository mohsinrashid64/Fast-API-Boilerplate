from datetime import UTC, datetime, timedelta


def utcnow() -> datetime:
    """Current UTC time as a *naive* datetime.

    The DateTime columns are timezone-naive (SQLite has no tz support),
    so we store and compare naive UTC values everywhere.
    """
    return datetime.now(UTC).replace(tzinfo=None)


def utc_in(**kwargs) -> datetime:
    """Naive UTC datetime offset from now, e.g. `utc_in(minutes=5)`."""
    return utcnow() + timedelta(**kwargs)
