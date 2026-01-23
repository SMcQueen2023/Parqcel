import polars as pl
from typing import List, Dict


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
    lines = []
    for row in (
        vc_df.sort(count_col, descending=True).head(max_items).iter_rows(named=True)
    ):
        value = row[value_col]
        count = row[count_col]
        percentage = (count / total) * 100 if total > 0 else 0
        lines.append(f"{repr(value)}: {count} ({percentage:.2f}%)")

    return lines


def get_numeric_stats(series: pl.Series) -> List[str]:
    return [
        f"Non-Nulls: {series.drop_nulls().len()}",
        f"Nulls: {series.is_null().sum()}",
        f"Unique: {series.n_unique()}",
        f"Min: {series.min()}",
        f"Max: {series.max()}",
        f"Mean: {series.mean():.2f}",
        f"Median: {series.median()}",
        f"Std Dev: {series.std():.2f}",
        f"Variance: {series.var():.2f}",
        f"Mode: {series.mode()[0] if series.mode().len() > 0 else 'N/A'}",
    ]


def get_string_stats(series: pl.Series) -> List[str]:
    non_null = series.drop_nulls().cast(str)
    lengths = non_null.str.len_chars()

    stats = [
        f"Non-Nulls: {non_null.len()}",
        f"Nulls: {series.is_null().sum()}",
        f"Blanks: {(series == '').sum()}",
        f"Unique: {series.n_unique()}",
        f"Min Length: {lengths.min()}",
        f"Max Length: {lengths.max()}",
        f"Median Length: {lengths.median()}",
        f"Mean Length: {lengths.mean():.2f}",
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
        f"Mode: {series.mode()[0] if series.mode().len() > 0 else 'N/A'}",
    ]


def get_date_stats(series: pl.Series) -> List[str]:
    return [
        f"Non-Nulls: {series.drop_nulls().len()}",
        f"Nulls: {series.is_null().sum()}",
        f"Unique: {series.n_unique()}",
        f"Earliest: {series.min()}",
        f"Latest: {series.max()}",
        f"Median: {series.median()}",
        f"Mode: {series.mode()[0] if series.mode().len() > 0 else 'N/A'}",
    ]


def get_datetime_stats(series: pl.Series) -> List[str]:
    min_val = series.min()
    max_val = series.max()
    range_val = (
        max_val - min_val if min_val is not None and max_val is not None else None
    )

    return [
        f"Non-Nulls: {series.drop_nulls().len()}",
        f"Nulls: {series.is_null().sum()}",
        f"Unique: {series.n_unique()}",
        f"Min: {min_val}",
        f"Max: {max_val}",
        f"Range: {range_val if range_val else 'N/A'}",
        f"Median: {series.median()}",
        f"Mode: {series.mode()[0] if series.mode().len() > 0 else 'N/A'}",
    ]


def get_fallback_stats(series: pl.Series) -> List[str]:
    return [
        f"Type: {series.dtype}",
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
        col_header = f"📊 Column: {col_name} ({col_series.dtype})"
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
