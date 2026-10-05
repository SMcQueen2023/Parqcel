"""Strict conversion of editor input without changing a column's dtype."""

from datetime import date, datetime, time
import math
from numbers import Integral, Real
import re
from typing import Any

import polars as pl


def is_editable_dtype(dtype: pl.DataType) -> bool:
    return (
        dtype.is_integer()
        or dtype.is_float()
        or dtype in (pl.Boolean, pl.String, pl.Date, pl.Datetime, pl.Time, pl.Null)
    )


def _check_temporal_precision(value: str) -> None:
    # Python temporal scalars cannot represent nanoseconds. Reject rather than
    # silently truncate an explicitly entered value.
    if re.search(r"[.,]\d{7,}", value):
        raise ValueError("Enter at most six fractional second digits")


def parse_cell_value(value: Any, dtype: pl.DataType) -> Any:
    """Parse an edit, preserving dtype and rejecting overflow or data loss.

    ``None`` represents null; blank input also represents null in non-string
    columns. String columns preserve blanks and whitespace. Unsupported complex
    dtypes are read-only. Timezone columns require an explicit offset in input.
    """
    if not is_editable_dtype(dtype):
        raise ValueError(f"Editing {dtype} values is not supported")
    if value is None:
        return None
    if dtype == pl.String:
        if not isinstance(value, str):
            raise ValueError("Expected text")
        return value

    text = value.strip() if isinstance(value, str) else None
    if text == "":
        return None
    if dtype == pl.Null:
        raise ValueError(
            "A Null column accepts only empty values; convert its type first"
        )
    parsed: Any
    if dtype.is_integer():
        if isinstance(value, bool):
            raise ValueError("Expected an integer")
        if text is not None and re.fullmatch(r"[+-]?\d+", text):
            parsed = int(text)
        elif isinstance(value, Integral):
            parsed = int(value)
        else:
            raise ValueError("Expected an integer without a decimal point")
    elif dtype.is_float():
        if isinstance(value, bool) or not isinstance(value, (str, Real)):
            raise ValueError("Expected a number")
        parsed = float(value)
    elif dtype == pl.Boolean:
        if isinstance(value, bool):
            return value
        if text is not None and text.lower() in {"true", "1", "yes"}:
            return True
        if text is not None and text.lower() in {"false", "0", "no"}:
            return False
        raise ValueError("Expected true or false")
    elif dtype == pl.Date:
        parsed = date.fromisoformat(text) if text is not None else value
        if not isinstance(parsed, date) or isinstance(parsed, datetime):
            raise ValueError("Expected an ISO date (YYYY-MM-DD)")
    elif dtype == pl.Datetime:
        if text is not None:
            _check_temporal_precision(text)
        parsed = datetime.fromisoformat(text) if text is not None else value
        if not isinstance(parsed, datetime):
            raise ValueError("Expected an ISO datetime")
        aware = parsed.utcoffset() is not None
        if bool(getattr(dtype, "time_zone", None)) != aware:
            raise ValueError(
                "Datetime timezone must match the column; include an offset for timezone columns"
            )
        if getattr(dtype, "time_unit", None) == "ms" and parsed.microsecond % 1000:
            raise ValueError("Value has more precision than this millisecond column")
    elif dtype == pl.Time:
        if text is not None:
            _check_temporal_precision(text)
        parsed = time.fromisoformat(text) if text is not None else value
        if not isinstance(parsed, time) or parsed.tzinfo is not None:
            raise ValueError("Expected an ISO time without a timezone")
    else:
        raise ValueError(f"Editing {dtype} values is not supported")

    try:
        validated = pl.Series("value", [parsed], dtype=dtype, strict=True)
        # Preserve the explicit input offset. Extracting a Python scalar from a
        # named-zone Series unnecessarily depends on system timezone data.
        if dtype == pl.Datetime:
            return parsed
        converted = validated[0]
    except (TypeError, ValueError, OverflowError, pl.exceptions.PolarsError) as exc:
        raise ValueError(f"Value cannot be represented as {dtype}") from exc
    if dtype.is_float() and math.isfinite(parsed) and not math.isfinite(converted):
        raise ValueError(f"Value is outside the range of {dtype}")
    return converted
