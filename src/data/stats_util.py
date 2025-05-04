import polars as pl
from PyQt6.QtWidgets import QMessageBox

def get_numeric_stats(series):
    min_val, max_val = series.min(), series.max()
    mean_val = series.mean()
    return [
        f"Min: {min_val}",
        f"Max: {max_val}",
        f"Mean: {mean_val:.2f}",
        f"Median: {series.median()}",
        f"Std Dev: {series.std():.2f}",
        f"Variance: {series.var():.2f}"
    ]

def get_string_stats(series):
    return [
        f"Unique Values: {series.n_unique()}",
        f"Blanks: {(series == '').sum()}",
        f"Nulls: {series.is_null().sum()}"
    ]

def generate_statistics(model):
    if not hasattr(model, '_data') or model._data is None:
        raise ValueError("Model does not contain data.")
    
    df = model._data
    if df.height == 0:
        return "No data available to generate statistics."

    stats = []

    type_handlers = {
        pl.Int64: get_numeric_stats,
        pl.Int32: get_numeric_stats,
        pl.Float64: get_numeric_stats,
        pl.Float32: get_numeric_stats,
        pl.Utf8: get_string_stats,
        pl.Categorical: get_string_stats
    }

    for col in df.columns:
        col_stats = [f"Column: {col} ({df.schema[col]})"]
        dtype = df.schema[col]
        series = df[col]

        handler = type_handlers.get(dtype)
        if handler:
            col_stats.extend(handler(series))
        else:
            col_stats.append("Statistics not supported for this type.")
        
        stats.append("\n".join(col_stats))
    
    full_text = "\n\n".join(stats)
    return full_text
