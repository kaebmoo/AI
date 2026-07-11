"""Naive-UTC now() helper — replaces the deprecated datetime.utcnow().

DB columns store naive UTC datetimes, so this preserves the exact semantics
of datetime.utcnow(). Migrating the whole system to timezone-aware datetimes
is future work (see plan/FIX_NOTES.md).
"""

from datetime import datetime, timezone


def utcnow() -> datetime:
    """Current UTC time as a naive datetime (same value datetime.utcnow() returned)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
