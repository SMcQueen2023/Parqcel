"""Parsing helpers for date/datetime detection and value parsing.

These functions are pure and small so they can be unit-tested without GUI.
"""
from __future__ import annotations

from typing import Iterable, List, Optional, Any
import datetime

from .date_formats import DATE_FORMATS, DATETIME_FORMATS


def detect_format_for_samples(values: Iterable[Any], formats: Iterable[str], sample_size: int = 500) -> Optional[str]:
    """Try to detect a format from a small sample of string values.

    Returns the first format that successfully parses all sampled non-empty strings, or None.
    """
    samples: List[str] = []
    for v in values:
        if v is None:
            continue
        s = str(v).strip()
        if s:
            samples.append(s)
        if len(samples) >= sample_size:
            break

    if not samples:
        return None

    for fmt in formats:
        ok = True
        for s in samples:
            try:
                datetime.datetime.strptime(s, fmt)
            except Exception:
                ok = False
                break
        if ok:
            return fmt
    return None


def parse_single_date(text: Any) -> Optional[datetime.date]:
    """Parse a single text value to a date using configured formats.

    Returns a date or None on failure.
    """
    if text is None:
        return None
    s = str(text).strip()
    if not s:
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.datetime.strptime(s, fmt).date()
        except Exception:
            continue
    return None


def parse_single_datetime(text: Any) -> Optional[datetime.datetime]:
    """Parse a single text value to a datetime using configured formats.

    Falls back to date-only formats converted to midnight when necessary.
    Returns a datetime or None on failure.
    """
    if text is None:
        return None
    s = str(text).strip()
    if not s:
        return None

    # Try datetime formats first
    for fmt in DATETIME_FORMATS:
        try:
            return datetime.datetime.strptime(s, fmt)
        except Exception:
            continue

    # Fallback: try date formats and convert to datetime at midnight
    for fmt in DATE_FORMATS:
        try:
            d = datetime.datetime.strptime(s, fmt).date()
            return datetime.datetime.combine(d, datetime.time())
        except Exception:
            continue

    return None


def parse_list_of_datetimes(values: Iterable[Any]) -> List[Optional[datetime.datetime]]:
    """Parse an iterable of strings to datetimes (pure python fallback).

    This is intentionally simple: it calls `parse_single_datetime` per value.
    """
    return [parse_single_datetime(v) for v in values]
