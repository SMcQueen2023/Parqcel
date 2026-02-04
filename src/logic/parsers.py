"""Parsing helpers for date/datetime detection and value parsing.

These functions are pure and small so they can be unit-tested without GUI.
"""

from __future__ import annotations

from typing import Iterable, List, Optional, Any
import datetime

from .date_formats import (
    DATETIME_FORMATS,
    PY_DATETIME_FORMATS,
    PY_DATE_FORMATS,
)
import logging

logger = logging.getLogger(__name__)
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


def _extract_sample_values(series: "pl.Series", sample_size: int = 500) -> List[str]:
    """Extract a sample of non-empty string values from a series for format detection.
    
    Args:
        series: The Polars series to sample from
        sample_size: Maximum number of samples to collect
        
    Returns:
        List of non-empty string values
    """
    sample_vals: List[str] = []
    try:
        sampled = series.head(sample_size)
        for v in sampled.to_list():
            if v is None:
                continue
            s = str(v).strip()
            if s:
                sample_vals.append(s)
            if len(sample_vals) >= sample_size:
                break
    except Exception:
        # Fallback iterator: try iterating the series if head()/to_list() failed
        logger.debug("Head-based sampling failed; falling back to iterator sampling", exc_info=True)
        for v in series:
            if v is None:
                continue
            s = str(v).strip()
            if s:
                sample_vals.append(s)
            if len(sample_vals) >= sample_size:
                break
    
    return sample_vals


def _try_vectorized_datetime_parse(
    series: "pl.Series", fmt: str, strict: bool = False
) -> Optional["pl.Series"]:
    """Try to parse a series using a specific datetime format.
    
    Args:
        series: The series to parse
        fmt: The datetime format string
        strict: Whether to use strict parsing
        
    Returns:
        Parsed series if successful, None otherwise
    """
    try:
        # Convert Python format to Polars format if needed
        polars_fmt = fmt.replace(".%f", "%.f") if "%.f" not in fmt else fmt
        out = series.str.strptime(pl.Datetime, polars_fmt, strict=strict)
        return out
    except Exception:
        logger.debug("Vectorized parse failed for format: %s", fmt, exc_info=False)
        return None


def _try_vectorized_date_parse(
    series: "pl.Series", fmt: str, strict: bool = False
) -> Optional["pl.Series"]:
    """Try to parse a series as dates and convert to datetime at midnight.
    
    Args:
        series: The series to parse
        fmt: The date format string
        strict: Whether to use strict parsing
        
    Returns:
        Parsed series (as Datetime) if successful, None otherwise
    """
    try:
        date_out = series.str.strptime(pl.Date, fmt, strict=strict)
        # Cast Date -> Datetime (midnight)
        return date_out.cast(pl.Datetime)
    except Exception:
        logger.debug("Vectorized date parse failed for format: %s", fmt, exc_info=False)
        return None


def _apply_python_fallback_parsing(
    series: "pl.Series", partially_parsed: Optional["pl.Series"]
) -> List[Optional[datetime.datetime]]:
    """Apply Python-based per-value parsing for remaining nulls.
    
    Args:
        series: Original series
        partially_parsed: Series with some values already parsed (or None)
        
    Returns:
        List of parsed datetime values
    """
    if partially_parsed is None:
        # Parse all values
        return [parse_single_datetime(v) for v in series.to_list()]
    
    # Parse only the null values
    parsed_vals = partially_parsed.to_list()
    null_mask = partially_parsed.is_null().to_list()
    for i, is_null in enumerate(null_mask):
        if is_null:
            try:
                parsed_vals[i] = parse_single_datetime(series[i])
            except Exception:
                logger.debug("Python fallback parsing failed for index %d", i, exc_info=True)
    
    return parsed_vals


def convert_series_to_datetime(series: "pl.Series", allow_fallback: bool = True) -> "pl.Series":
    """Robustly convert a Utf8/text `pl.Series` to `pl.Datetime`.

    Strategy:
    - If already datetime, return as-is.
    - Attempt vectorized parsing using detected datetime formats.
    - If vectorized parse leaves some nulls, fall back to pure-Python per-value parsing for those entries.
    - Return a `pl.Series` with `pl.Datetime` dtype (or the best-effort series if casting fails).
    
    Args:
        series: Series to convert
        allow_fallback: Whether to allow Python fallback for unparseable values
        
    Returns:
        Series with Datetime dtype
    """
    if series is None:
        return series

    try:
        # If already datetime dtype, nothing to do
        if series.dtype == pl.Datetime:
            return series

        name = series.name if series.name else "__col"
        
        # Extract sample for format detection
        sample_vals = _extract_sample_values(series)

        # Detect best formats from samples
        best_dt_fmt = (
            detect_format_for_samples(sample_vals, PY_DATETIME_FORMATS)
            if sample_vals
            else None
        )
        best_date_fmt = (
            detect_format_for_samples(sample_vals, PY_DATE_FORMATS) if sample_vals else None
        )

        # 1) Try detected datetime format (fast path if successful)
        if best_dt_fmt:
            out = _try_vectorized_datetime_parse(series, best_dt_fmt, strict=False)
            if out is not None and int(out.is_null().sum()) == 0:
                return out.cast(pl.Datetime)
            if not allow_fallback:
                raise ValueError(
                    "Vectorized parse produced nulls and fallback is disabled"
                )

        # 2) Try detected date-only format
        if best_date_fmt:
            out = _try_vectorized_date_parse(series, best_date_fmt, strict=False)
            if out is not None and int(out.is_null().sum()) == 0:
                return out
            if not allow_fallback:
                raise ValueError("Date-format vectorized parse produced nulls and fallback is disabled")

        # 3) Try safe formats (4-digit year) first to avoid ambiguous %y parsing
        safe_formats = [f for f in DATETIME_FORMATS if "%y" not in f]
        formats_to_try = safe_formats if safe_formats else DATETIME_FORMATS

        parsed = None
        for fmt in formats_to_try:
            piece = _try_vectorized_datetime_parse(series, fmt, strict=False)
            if piece is not None:
                parsed = piece if parsed is None else parsed.fill_null(piece)
                if int(parsed.is_null().sum()) == 0:
                    return parsed.cast(pl.Datetime)

        # 4) Try remaining formats (including %y) if not tried yet
        if safe_formats and len(safe_formats) != len(DATETIME_FORMATS):
            for fmt in DATETIME_FORMATS:
                if fmt in safe_formats:
                    continue
                piece = _try_vectorized_datetime_parse(series, fmt, strict=False)
                if piece is not None:
                    parsed = piece if parsed is None else parsed.fill_null(piece)
                    if int(parsed.is_null().sum()) == 0:
                        return parsed.cast(pl.Datetime)

        # If fallback is disabled, signal failure
        if not allow_fallback:
            if parsed is None or int(parsed.is_null().sum()) != 0:
                raise ValueError(
                    "Could not fully parse series with vectorized attempts and fallback is disabled"
                )

        # 5) Python fallback for remaining nulls
        parsed_vals = _apply_python_fallback_parsing(series, parsed)

        try:
            new_col = pl.Series(name=name, values=parsed_vals).cast(pl.Datetime)
        except Exception:
            logger.debug(
                "Failed to cast parsed values to pl.Datetime for column %s, returning best-effort series",
                name,
                exc_info=True,
            )
            new_col = pl.Series(name=name, values=parsed_vals)
        return new_col
    except Exception:
        logger.exception("convert_series_to_datetime failed unexpectedly; returning original series")
        return series
