import polars as pl

def get_column_types(df: pl.DataFrame) -> dict:
    return {col: str(dtype) for col, dtype in df.schema.items()}

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
