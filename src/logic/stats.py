import polars as pl
from typing import Any, List, Dict, cast


def _format_for_display(value: Any) -> str:
    """Return a safe string for display, decoding bytes when possible."""
    if isinstance(value, (bytes, bytearray)):
        try:
            return value.decode("utf-8")
        except Exception:
            return repr(value)
    return "None" if value is None else str(value)


def _format_number(value: Any, precision: int = 2) -> str:
    """Format numeric values with given precision; fall back to safe display."""
    try:
        if isinstance(value, (int, float)):
            return f"{value:.{precision}f}"
    except Exception:
        pass
    return _format_for_display(value)


def _safe_range(min_val: Any, max_val: Any) -> Any:
    """Return max_val - min_val if it's a valid operation, else None."""
    if min_val is None or max_val is None:
        return None
    # Try subtraction and fall back to None on failure
    try:
        return cast(Any, max_val) - cast(Any, min_val)
    except Exception:
        return None


def _value_count_summary(series: pl.Series, max_items: int = 5) -> List[str]:
    """
    Return top value counts and percentages for a series,
    dynamically detecting the counts column.
    """
    vc_df = series.value_counts()

    cols = vc_df.columns
    if len(cols) != 2:
        return ["Value counts unavailable due to unexpected output format."]

    # Use helper function to detect numeric dtype
    def _is_numeric_dtype(dtype) -> bool:
        numeric_types = {
            pl.Int8,
            pl.Int16,
            pl.Int32,
            pl.Int64,
            pl.UInt8,
            pl.UInt16,
            pl.UInt32,
            pl.UInt64,
            pl.Float32,
            pl.Float64,
        }
        return dtype in numeric_types

    if _is_numeric_dtype(vc_df[cols[0]].dtype):
        count_col = cols[0]
        value_col = cols[1]
    elif _is_numeric_dtype(vc_df[cols[1]].dtype):
        count_col = cols[1]
        value_col = cols[0]
    else:
        return ["Value counts unavailable due to no numeric counts column."]

    total = len(series)
    lines: List[str] = []
    for row in (
        vc_df.sort(count_col, descending=True).head(max_items).iter_rows(named=True)
    ):
        value = row[value_col]
        count = row[count_col]
        percentage = (count / total) * 100 if total > 0 else 0
        lines.append(f"{_format_for_display(value)}: {count} ({percentage:.2f}%)")

    return lines


def get_numeric_stats(series: pl.Series) -> List[str]:
    mean_val = series.mean()
    std_val = series.std()
    var_val = series.var()
    return [
        f"Non-Nulls: {series.drop_nulls().len()}",
        f"Nulls: {series.is_null().sum()}",
        f"Unique: {series.n_unique()}",
        f"Min: {_format_for_display(series.min())}",
        f"Max: {_format_for_display(series.max())}",
        f"Mean: {_format_number(mean_val)}",
        f"Median: {_format_for_display(series.median())}",
        f"Std Dev: {_format_number(std_val)}",
        f"Variance: {_format_number(var_val)}",
        f"Mode: {_format_for_display(series.mode()[0]) if series.mode().len() > 0 else 'N/A'}",
    ]


def get_string_stats(series: pl.Series) -> List[str]:
    non_null = series.drop_nulls().cast(str)
    lengths = non_null.str.len_chars()

    stats = [
        f"Non-Nulls: {non_null.len()}",
        f"Nulls: {series.is_null().sum()}",
        f"Blanks: {(series == '').sum()}",
        f"Unique: {series.n_unique()}",
        f"Min Length: {_format_for_display(lengths.min())}",
        f"Max Length: {_format_for_display(lengths.max())}",
        f"Median Length: {_format_for_display(lengths.median())}",
        f"Mean Length: {_format_number(lengths.mean())}",
    ]

    stats.append("Top Values:")
    stats.extend(_value_count_summary(series))
    return stats


def get_boolean_stats(series: pl.Series) -> List[str]:
    non_null_count = series.drop_nulls().len()
    # Count True values by summing the boolean series after dropping nulls.
    true_count = int(series.drop_nulls().sum() or 0)
    false_count = non_null_count - true_count

    return [
        f"Non-Nulls: {non_null_count}",
        f"Nulls: {series.is_null().sum()}",
        f"True: {true_count}",
        f"False: {false_count}",
        f"Mode: {_format_for_display(series.mode()[0]) if series.mode().len() > 0 else 'N/A'}",
    ]


def get_date_stats(series: pl.Series) -> List[str]:
    min_val = series.min()
    max_val = series.max()
    mode_val = series.mode()[0] if series.mode().len() > 0 else None

    return [
        f"Non-Nulls: {series.drop_nulls().len()}",
        f"Nulls: {series.is_null().sum()}",
        f"Unique: {series.n_unique()}",
        f"Earliest: {_format_for_display(min_val)}",
        f"Latest: {_format_for_display(max_val)}",
        f"Median: {_format_for_display(series.median())}",
        f"Mode: {_format_for_display(mode_val) if mode_val is not None else 'N/A'}",
    ]


def get_datetime_stats(series: pl.Series) -> List[str]:
    min_val = series.min()
    max_val = series.max()
    range_val = _safe_range(min_val, max_val)
    mode_val = series.mode()[0] if series.mode().len() > 0 else None

    return [
        f"Non-Nulls: {series.drop_nulls().len()}",
        f"Nulls: {series.is_null().sum()}",
        f"Unique: {series.n_unique()}",
        f"Min: {_format_for_display(min_val)}",
        f"Max: {_format_for_display(max_val)}",
        f"Range: {_format_for_display(range_val) if range_val is not None else 'N/A'}",
        f"Median: {_format_for_display(series.median())}",
        f"Mode: {_format_for_display(mode_val) if mode_val is not None else 'N/A'}",
    ]


def get_fallback_stats(series: pl.Series) -> List[str]:
    return [
        f"Type: {_format_for_display(series.dtype)}",
        f"Nulls: {series.is_null().sum()}",
        f"Unique: {series.n_unique()}",
        "Stats not supported for this type.",
    ]


def get_stats_for_column(series: pl.Series) -> List[str]:
    dtype = series.dtype

    if dtype in [
        pl.Int8,
        pl.Int16,
        pl.Int32,
        pl.Int64,
        pl.UInt8,
        pl.UInt16,
        pl.UInt32,
        pl.UInt64,
        pl.Float32,
        pl.Float64,
    ]:
        return get_numeric_stats(series)
    elif dtype in [pl.Utf8, pl.Categorical]:
        return get_string_stats(series)
    elif dtype == pl.Boolean:
        return get_boolean_stats(series)
    elif dtype == pl.Date:
        return get_date_stats(series)
    elif dtype == pl.Datetime or dtype == pl.Time:
        return get_datetime_stats(series)
    else:
        return get_fallback_stats(series)


def generate_statistics(model) -> str:
    if not hasattr(model, "_data") or model._data is None:
        raise ValueError("Model does not contain a valid DataFrame.")

    df: pl.DataFrame = model._data
    if df.is_empty():
        return "No data available."

    stats = []

    for col_name in df.columns:
        col_series = df[col_name]
        col_header = f"📊 Column: {_format_for_display(col_name)} ({_format_for_display(col_series.dtype)})"
        col_stats = get_stats_for_column(col_series)
        stats.append("\n".join([col_header] + col_stats))

    return "\n\n".join(stats)


def get_column_types(df: pl.DataFrame) -> Dict[str, str]:
    return {col: str(dtype) for col, dtype in df.schema.items()}


def get_column_type_counts_string(df: pl.DataFrame) -> str:
    from collections import Counter

    type_counts = Counter(str(dtype) for dtype in df.schema.values())
    return ", ".join(f"{dtype}: {count}" for dtype, count in type_counts.items())


def update_statistics(self) -> None:
    if hasattr(self, "model") and self.model is not None:
        df = self.model._data
        self.row_count_label.setText(f"Total Rows: {df.height}")
        self.total_column_count_label.setText(f"Total Columns: {df.width}")
        self.column_type_count_label.setText(
            f"Column Type Count: {get_column_type_counts_string(df)}"
        )


def get_page_data(df: pl.DataFrame, page_number: int, chunk_size: int) -> pl.DataFrame:
    return df.slice(page_number * chunk_size, chunk_size)


def calculate_max_pages(row_count: int, chunk_size: int) -> int:
    return (row_count + chunk_size - 1) // chunk_size


def get_column_statistics(df: pl.DataFrame, column_name: str) -> str:
    if column_name not in df.columns:
        return "Column not found."
    stats = get_stats_for_column(df[column_name])
    return "\n".join(stats)
