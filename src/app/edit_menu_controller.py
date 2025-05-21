import polars as pl
from PyQt6.QtWidgets import QMessageBox
from app.widgets.edit_menu_gui import AddColumnDialog, MultiSortDialog, SortRuleWidget

def add_column(df: pl.DataFrame, col_name: str, dtype: str, default_value) -> pl.DataFrame:
    if not col_name:
        raise ValueError("Column name cannot be empty.")

    if col_name in df.columns:
        raise ValueError(f"Column '{col_name}' already exists.")

    try:
        if dtype == "Integer":
            default_value = int(default_value)
            new_col = pl.Series(name=col_name, values=[default_value] * df.height, dtype=pl.Int64)
        elif dtype == "Float":
            default_value = float(default_value)
            new_col = pl.Series(name=col_name, values=[default_value] * df.height, dtype=pl.Float64)
        elif dtype == "Date":
            new_col = pl.Series(name=col_name, values=[default_value] * df.height).cast(pl.Date)
        elif dtype == "Datetime":
            new_col = pl.Series(name=col_name, values=[default_value] * df.height).cast(pl.Datetime)
        else:  # String
            new_col = pl.Series(name=col_name, values=[default_value] * df.height, dtype=pl.Utf8)

        df = df.with_columns(new_col)
        return df

    except Exception as e:
        raise RuntimeError(f"Could not add column: {str(e)}")