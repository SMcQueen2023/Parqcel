"""Pure filtering helpers for applying filter operations to a Polars DataFrame.

This module contains `apply_filter_to_df` which performs the core filtering
logic in a way that's easy to unit-test without Qt dialogs.
"""
from __future__ import annotations

from typing import Any
import polars as pl


def apply_filter_to_df(df: pl.DataFrame, column_name: str, filter_type: str, filter_value: Any) -> pl.DataFrame:
    """Apply a filter to `df` on `column_name` using `filter_type` and `filter_value`.

    Supported filter_type values: 'contains', 'starts_with', 'ends_with', '==',
    'between', '<', '<=', '>', '>='.

    Returns the filtered DataFrame or raises ValueError on bad inputs.
    """
    if column_name not in df.columns:
        raise ValueError(f"Column '{column_name}' not found.")

    col = pl.col(column_name)

    if filter_type == "contains":
        return df.filter(col.str.contains(filter_value))
    if filter_type == "starts_with":
        return df.filter(col.str.starts_with(filter_value))
    if filter_type == "ends_with":
        return df.filter(col.str.ends_with(filter_value))
    if filter_type == "==":
        return df.filter(col == filter_value)
    if filter_type == "between":
        if not isinstance(filter_value, (tuple, list)) or len(filter_value) != 2:
            raise ValueError("Filter value for 'between' must be a (start, end) tuple")
        start_value, end_value = filter_value
        if start_value > end_value:
            start_value, end_value = end_value, start_value
        return df.filter((col >= start_value) & (col <= end_value))
    if filter_type == "<":
        return df.filter(col < filter_value)
    if filter_type == "<=":
        return df.filter(col <= filter_value)
    if filter_type == ">":
        return df.filter(col > filter_value)
    if filter_type == ">=":
        return df.filter(col >= filter_value)

    raise ValueError(f"Unsupported filter operation: {filter_type}")
