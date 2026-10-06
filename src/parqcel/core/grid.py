"""Raw cell rendering, bounded literal search and structured column summaries."""

from __future__ import annotations

from decimal import Decimal, localcontext
import json
from typing import Any, Sequence

import polars as pl

_SEARCH_CHUNK_SIZE = 65_536


def raw_value_text(value: Any, *, null_text: str = "null") -> str:
    """Render a Python/Polars scalar without rounding or truncating nested values."""
    if value is None:
        return null_text
    try:
        if isinstance(value, pl.Series):
            value = value.to_list()
        if isinstance(value, (list, tuple, dict)):
            return json.dumps(value, ensure_ascii=False, default=str)
        return str(value)
    except Exception:
        return f"<unprintable {type(value).__name__}>"


def _raw_strings(series: pl.Series, *, null_text: str = "null") -> pl.Series:
    """Use native scalar rendering; only unsupported nested values need Python."""
    if series.dtype == pl.String:
        return series.fill_null(null_text)
    if series.dtype.is_nested() or series.dtype in (pl.Object, pl.Binary):
        return pl.Series(
            series.name,
            [raw_value_text(value, null_text=null_text) for value in series],
            dtype=pl.String,
        )
    try:
        return series.cast(pl.String).fill_null(null_text)
    except (TypeError, ValueError, pl.exceptions.PolarsError):
        return pl.Series(
            series.name,
            [raw_value_text(value, null_text=null_text) for value in series],
            dtype=pl.String,
        )


def raw_cell_text(series: pl.Series, row: int, *, null_text: str = "") -> str:
    """Return an unformatted cell string, retaining native nanosecond precision.

    Native Polars scalar-to-string conversion keeps large integers exact and
    avoids the nanosecond truncation of Python datetime/time objects. This is
    suitable for clipboard and editor text, independently of display formats.
    """
    if not 0 <= row < len(series):
        raise IndexError("Row is outside the column")
    # Common table paint paths avoid building a one-element string Series.
    if (
        series.dtype == pl.String
        or series.dtype.is_integer()
        or series.dtype in (pl.Boolean, pl.Null, pl.Binary)
    ):
        value = series[row]
        if value is None:
            return null_text
        if isinstance(value, bool):
            return "true" if value else "false"
        return raw_value_text(value, null_text=null_text)
    return str(_raw_strings(series.slice(row, 1), null_text=null_text)[0])


def raw_column_text(series: pl.Series, *, null_text: str = "") -> pl.Series:
    """Render a requested column slice once for precision-preserving clipboard I/O.

    Callers should supply only the bounded rows they intend to copy. The result
    uses the same unformatted representation as find_match and raw_cell_text.
    """
    return _raw_strings(series, null_text=null_text)


def _find_in_column(
    series: pl.Series,
    needle: str,
    start: int,
    stop: int,
    case_sensitive: bool,
    backwards: bool,
) -> int | None:
    cursor = stop if backwards else start
    while (cursor > start) if backwards else (cursor < stop):
        lower = max(start, cursor - _SEARCH_CHUNK_SIZE) if backwards else cursor
        upper = cursor if backwards else min(stop, cursor + _SEARCH_CHUNK_SIZE)
        strings = _raw_strings(series.slice(lower, upper - lower))
        if not case_sensitive:
            strings = strings.str.to_lowercase()
        matches = strings.str.contains(needle, literal=True)
        if backwards:
            matches = matches.reverse()
        position = matches.arg_max()
        if position is not None and matches[position]:
            return upper - 1 - position if backwards else lower + position
        cursor = lower if backwards else upper
    return None


def find_match(
    frame: pl.DataFrame,
    text: str,
    columns: Sequence[str] | None = None,
    case_sensitive: bool = False,
    after: tuple[int, int] | None = None,
    backwards: bool = False,
) -> tuple[int, int] | None:
    """Find one literal substring in raw cell strings, wrapping at most once.

    Return zero-based ``(row, logical_column_index)`` in ``frame`` coordinates.
    Search is row-major regardless of ``columns`` order. With ``after``, begin
    strictly after/before that cell; the anchor is visited last after wrapping.
    Without it, start at the first/last cell. An empty query or column list has
    no match. Unknown columns or an out-of-range anchor raise ValueError.

    Null renders as ``null``; display rounding/format settings never affect
    matches. Work uses one column chunk at a time and retains a single candidate,
    not a list of every matching row or a Python copy of the whole dataframe.
    """
    if not isinstance(text, str):
        raise ValueError("Search text must be a string")
    names = frame.columns if columns is None else list(columns)
    if any(name not in frame.columns for name in names):
        raise ValueError("Search columns must exist in the dataset")
    selected = [i for i, name in enumerate(frame.columns) if name in names]
    total = frame.height * frame.width
    if after is not None:
        if (
            len(after) != 2
            or not all(isinstance(value, int) for value in after)
            or not 0 <= after[0] < frame.height
            or not 0 <= after[1] < frame.width
        ):
            raise ValueError("Search anchor is outside the dataset")
        anchor = after[0] * frame.width + after[1]
    else:
        anchor = 0
    if not text or not selected or not total:
        return None
    needle = text if case_sensitive else text.lower()
    if after is None:
        ranges = [(0, total)]
    elif backwards:
        ranges = [(0, anchor), (anchor, total)]
    else:
        ranges = [(anchor + 1, total), (0, anchor + 1)]
    for lower, upper in ranges:
        best: tuple[int, int] | None = None
        for column in selected:
            row_start = max(0, (lower - column + frame.width - 1) // frame.width)
            row_stop = min(frame.height, (upper - 1 - column) // frame.width + 1)
            if best is not None:
                if backwards:
                    row_start = max(row_start, best[0])
                else:
                    row_stop = min(row_stop, best[0] + 1)
            row = _find_in_column(
                frame[:, column], needle, row_start, row_stop, case_sensitive, backwards
            )
            if row is not None:
                candidate = (row, column)
                if best is None or (
                    candidate > best if backwards else candidate < best
                ):
                    best = candidate
        if best is not None:
            return best
    return None


def column_profile(frame: pl.DataFrame, name: str) -> dict[str, Any]:
    """Return typed statistics; count/unique include nulls, non_null does not.

    Numeric extrema retain their native Python type. Integer means use Decimal
    arithmetic to avoid rounding large IDs through float64. Non-numeric columns
    include at most five ``top_values`` entries of ``{value, count}``; exact
    counts still require a native distinct-value aggregation. Unsupported object
    aggregations are explicitly marked ``supported=False``.
    """
    if name not in frame.columns:
        raise ValueError(f"Column '{name}' not found")
    series = frame[name]
    profile: dict[str, Any] = {
        "name": name,
        "dtype": str(series.dtype),
        "count": len(series),
        "non_null": len(series) - series.null_count(),
        "nulls": series.null_count(),
        "unique": None,
    }
    try:
        profile["unique"] = series.n_unique()
    except (TypeError, ValueError, pl.exceptions.PolarsError):
        profile["supported"] = False
    if series.dtype.is_numeric():
        profile.update(min=series.min(), max=series.max(), mean=series.mean())
        if series.dtype.is_integer() and profile["non_null"]:
            with localcontext() as context:
                context.prec = 50
                try:
                    total = Decimal(
                        str(series.cast(pl.Decimal(precision=38, scale=0)).sum())
                    )
                except (TypeError, ValueError, pl.exceptions.PolarsError):
                    total = sum(
                        (Decimal(value) for value in series if value is not None),
                        Decimal(0),
                    )
                profile["mean"] = total / Decimal(profile["non_null"])
        return profile
    if series.dtype in (pl.String, pl.Date, pl.Datetime, pl.Time):
        profile.update(min=series.min(), max=series.max())
    profile["top_values"] = []
    try:
        counts = series.rename("value").value_counts(name="count")
        top = counts.top_k(5, by="count").sort("count", descending=True)
        profile["top_values"] = list(top.iter_rows(named=True))
    except (TypeError, ValueError, pl.exceptions.PolarsError):
        profile["supported"] = False
    return profile
