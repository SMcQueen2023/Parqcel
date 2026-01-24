"""Parsing helpers for date/datetime detection and value parsing.

These functions are pure and small so they can be unit-tested without GUI.
"""

from __future__ import annotations

from typing import Iterable, List, Optional, Any
import datetime

from .date_formats import (
    DATE_FORMATS,
    DATETIME_FORMATS,
    PY_DATETIME_FORMATS,
    PY_DATE_FORMATS,
    POLARS_DATETIME_FORMATS,
)
import polars as pl


def detect_format_for_samples(
    values: Iterable[Any], formats: Iterable[str], sample_size: int = 500
) -> Optional[str]:
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
    # Use Python-friendly date formats for pure-Python parsing
    for fmt in PY_DATE_FORMATS:
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

    # Try datetime formats first (use Python-friendly patterns)
    for fmt in PY_DATETIME_FORMATS:
        try:
            return datetime.datetime.strptime(s, fmt)
        except Exception:
            continue

    # Fallback: try date formats and convert to datetime at midnight
    for fmt in PY_DATE_FORMATS:
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


def convert_series_to_datetime(series: "pl.Series", allow_fallback: bool = True) -> "pl.Series":
    """Robustly convert a Utf8/text `pl.Series` to `pl.Datetime`.

    Strategy:
    - If already datetime, return as-is.
    - Attempt vectorized parsing using detected datetime formats.
    - If vectorized parse leaves some nulls, fall back to pure-Python per-value parsing for those entries.
    - Return a `pl.Series` with `pl.Datetime` dtype (or the best-effort series if casting fails).
    """
    if series is None:
        return series

    try:
        # If already datetime dtype, nothing to do
        if series.dtype == pl.Datetime:
            return series

        # Prepare sample for format detection (first 500 non-empty values)
        sample_vals: List[str] = []
        try:
            sampled = series.head(500)
            for v in sampled.to_list():
                if v is None:
                    continue
                s = str(v).strip()
                if s:
                    sample_vals.append(s)
                if len(sample_vals) >= 500:
                    break
        except Exception:
            # Fallback iterator
            for v in series:
                if v is None:
                    continue
                s = str(v).strip()
                if s:
                    sample_vals.append(s)
                if len(sample_vals) >= 500:
                    break

        # Use Python-compatible formats for sample detection
        best_dt_fmt = (
            detect_format_for_samples(sample_vals, PY_DATETIME_FORMATS)
            if sample_vals
            else None
        )
        # Also attempt to detect date-only formats (e.g., "%Y-%m-%d") and treat them as midnight datetimes
        best_date_fmt = (
            detect_format_for_samples(sample_vals, PY_DATE_FORMATS) if sample_vals else None
        )
        name = series.name if series.name else "__col"

        # 1) If we detected a clear format, try a single vectorized parse using Series.str.strptime
        if best_dt_fmt:
            try:
                # For Polars parsing, use chrono/Polars format strings
                # convert the python-format to the closest Polars format if needed
                polars_fmt = (
                    best_dt_fmt.replace(".%f", "%.f")
                    if "%.f" not in best_dt_fmt
                    else best_dt_fmt
                )
                out = series.str.strptime(pl.Datetime, polars_fmt, strict=False)
                # If vectorized parse succeeded for all rows, return immediately (fast-path)
                if int(out.is_null().sum()) == 0:
                    return out.cast(pl.Datetime)
                # If fallback is disabled, bail out early instead of doing per-row Python parsing
                if not allow_fallback:
                    raise ValueError(
                        "Vectorized parse produced nulls and fallback is disabled"
                    )
            except Exception:
                pass

        # 1b) If we detected a clear date-only format, parse as Date then cast to Datetime at midnight
        if best_date_fmt:
            try:
                # best_date_fmt is python-style; convert fractional if needed (no fractional for dates)
                date_out = series.str.strptime(pl.Date, best_date_fmt, strict=False)
                if int(date_out.is_null().sum()) == 0:
                    # cast Date -> Datetime (midnight) and return
                    return date_out.cast(pl.Datetime)
                if not allow_fallback:
                    raise ValueError("Date-format vectorized parse produced nulls and fallback is disabled")
            except Exception:
                pass

        # 2) Try safe (4-digit year) formats first to avoid ambiguous %y parsing
        safe_formats = [f for f in DATETIME_FORMATS if "%y" not in f]
        formats_to_try = safe_formats if safe_formats else DATETIME_FORMATS

        parsed = None
        for fmt in formats_to_try:
            try:
                piece = series.str.strptime(pl.Datetime, fmt, strict=False)
            except Exception:
                continue
            parsed = piece if parsed is None else parsed.fill_null(piece)
            if int(parsed.is_null().sum()) == 0:
                return parsed.cast(pl.Datetime)

        # 3) If still have nulls, try remaining formats (including %y) if we didn't try them
        if safe_formats and len(safe_formats) != len(DATETIME_FORMATS):
            for fmt in DATETIME_FORMATS:
                if fmt in safe_formats:
                    continue
                try:
                    piece = series.str.strptime(pl.Datetime, fmt, strict=False)
                except Exception:
                    continue
                parsed = piece if parsed is None else parsed.fill_null(piece)
                if int(parsed.is_null().sum()) == 0:
                    return parsed.cast(pl.Datetime)

        # If fallback is disabled, and we still have nulls now, raise instead of doing Python fallback
        if not allow_fallback:
            # If we parsed something but nulls remain, signal failure to caller
            if parsed is None or int(parsed.is_null().sum()) != 0:
                raise ValueError(
                    "Could not fully parse series with vectorized attempts and fallback is disabled"
                )

        # 4) Fallback: Python-per-value parsing only for remaining nulls
        if parsed is None:
            parsed_vals = [parse_single_datetime(v) for v in series.to_list()]
        else:
            parsed_vals = parsed.to_list()
            null_mask = parsed.is_null().to_list()
            for i, is_null in enumerate(null_mask):
                if is_null:
                    parsed_vals[i] = parse_single_datetime(series[i])

        try:
            new_col = pl.Series(name=name, values=parsed_vals).cast(pl.Datetime)
        except Exception:
            new_col = pl.Series(name=name, values=parsed_vals)
        return new_col
    except Exception:
        return series
