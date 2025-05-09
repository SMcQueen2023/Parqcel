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
    non_null_series = series.drop_nulls()
    str_lengths = non_null_series.cast(str).str.len_chars()

    return [
        f"Unique Values: {series.n_unique()}",
        f"Blanks: {(series == '').sum()}",
        f"Nulls: {series.is_null().sum()}",
        f"Min Length: {str_lengths.min()}",
        f"Max Length: {str_lengths.max()}",
        f"Median Length: {str_lengths.median()}",
        f"Average Length: {str_lengths.mean():.2f}"
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

def get_column_types(df: pl.DataFrame) -> dict:
    """Returns a dictionary with column names as keys and types as values."""
    return {col: str(dtype) for col, dtype in df.schema.items()}

def get_column_type_counts_string(df: pl.DataFrame) -> str:
    """
    Returns a concise string summary like "Utf8: 3, Int64: 2"
    """
    column_types = get_column_types(df)  # Get individual column types
    type_counts = {}

    for dtype in column_types.values():
        type_counts[dtype] = type_counts.get(dtype, 0) + 1  # Count the occurrences of each type

    return ", ".join(f"{dtype}: {count}" for dtype, count in type_counts.items())


def update_statistics(self):
    if hasattr(self, 'model') and self.model is not None:
        df = self.model._data
        row_count = df.height
        total_columns = df.width

        self.row_count_label.setText(f"Rows: {row_count}")
        self.total_column_count_label.setText(f"Total Columns: {total_columns}")

        type_count_text = get_column_type_counts_string(df)
        self.column_type_count_label.setText(f"Column Type Count: {type_count_text}")

def get_page_data(df: pl.DataFrame, page_number: int, chunk_size: int) -> pl.DataFrame:
    start_row = page_number * chunk_size
    return df.slice(start_row, chunk_size)

def calculate_max_pages(row_count: int, chunk_size: int) -> int:
    return (row_count + chunk_size - 1) // chunk_size

def get_column_statistics(df: pl.DataFrame, column_name: str) -> str:
    col = df[column_name]
    dtype = df.schema[column_name]
    stats = ""
    if dtype in [pl.Utf8, pl.Categorical]:
        stats += f"Unique Values: {col.n_unique()}\n"
        stats += f"Blanks: {(col == '').sum()}\n"
        stats += f"Nulls: {col.is_null().sum()}\n"
        value_counts = col.value_counts()
        for value, count in value_counts.iter_rows():
            percentage = (count / df.height) * 100
            stats += f"'{value}': {percentage:.2f}%\n"
    elif dtype in [pl.Int64, pl.Int32, pl.Float64, pl.Float32]:
        stats += f"Min: {col.min()}\n"
        stats += f"Max: {col.max()}\n"
        stats += f"Mean: {col.mean():.2f}\n"
        stats += f"Median: {col.median()}\n"
        stats += f"Std Dev: {col.std():.2f}\n"
        stats += f"Variance: {col.var():.2f}\n"
    else:
        stats += "Statistics not supported for this column type."
    return stats
