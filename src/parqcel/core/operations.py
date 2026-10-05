"""Pure dataframe operations, independent of desktop widgets."""

from __future__ import annotations

import polars as pl

from parqcel.core.parsers import convert_series_to_datetime


def convert_column(df: pl.DataFrame, column: str, target: str) -> pl.DataFrame:
    types = {
        "String": pl.String,
        "Integer": pl.Int64,
        "Float": pl.Float64,
        "Boolean": pl.Boolean,
        "Date": pl.Date,
        "Datetime": pl.Datetime,
    }
    if target not in types:
        raise ValueError(f"Unsupported type: {target}")
    dtype = types[target]
    series = df[column]
    if target in ("Date", "Datetime") and series.dtype == pl.String:
        result = convert_series_to_datetime(series).cast(dtype, strict=True)
        invalid = result.is_null() & series.is_not_null()
        if result.dtype != dtype or invalid.any():
            raise ValueError(
                f"Cannot convert {int(invalid.sum())} non-null values to {target}."
            )
        return df.with_columns(result)
    if target == "Boolean" and series.dtype == pl.String:
        lowered = series.str.to_lowercase()
        values = {"true": True, "false": False, "1": True, "0": False}
        return df.with_columns(
            lowered.replace_strict(values, return_dtype=pl.Boolean).alias(column)
        )
    return df.with_columns(pl.col(column).cast(dtype, strict=True))


def featurize_dataset(df: pl.DataFrame, **options) -> pl.DataFrame:
    from ds.featurize import add_features_to_df, generate_feature_matrix

    matrix, names = generate_feature_matrix(df, **options)
    return add_features_to_df(df, matrix, names)


def pca_dataset(df: pl.DataFrame, components: int = 2) -> pl.DataFrame:
    from ds.dimensionality import compute_pca
    from ds.featurize import generate_feature_matrix

    matrix, _names = generate_feature_matrix(df)
    embedding, _variance = compute_pca(matrix, n_components=components)
    return pl.DataFrame(
        {f"pca_{i + 1}": embedding[:, i] for i in range(embedding.shape[1])}
    )
