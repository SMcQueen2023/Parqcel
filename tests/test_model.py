import polars as pl
import datetime

from models.polars_table_model import PolarsTableModel


def test_pagination_and_row_counts(qapp):
    df = pl.DataFrame({"a": list(range(25)), "b": [f"x{i}" for i in range(25)]})
    model = PolarsTableModel(df, chunk_size=10)

    assert model.get_max_pages() == 3
    assert model.get_current_page() == 0
    assert model.rowCount() == 10

    model.load_next_page()
    assert model.get_current_page() == 1
    assert model.rowCount() == 10

    model.jump_to_page(2)
    assert model.get_current_page() == 2
    assert model.rowCount() == 5

    model.load_previous_page()
    assert model.get_current_page() == 1


def test_sort_and_drop_column(qapp):
    df = pl.DataFrame({"a": [3, 1, 2], "b": ["c", "a", "b"]})
    model = PolarsTableModel(df, chunk_size=10)

    model.sort_column("a", ascending=True)
    assert model._data["a"].to_list() == [1, 2, 3]

    model.drop_column("b")
    assert model.columnCount() == 1
    assert "b" not in model._data.columns


def test_update_data_and_undo_redo(qapp):
    df = pl.DataFrame({"a": [1, 2, 3, 4], "b": ["x", "y", "z", "w"]})
    model = PolarsTableModel(df, chunk_size=10)

    new_df = df.filter(pl.col("a") > 2)
    model.update_data(new_df)
    assert model._data.height == 2

    model.undo()
    assert model._data.height == 4

    model.redo()
    assert model._data.height == 2


def test_set_data_parses_date(qapp):
    df = pl.DataFrame({"d": [datetime.date(2024, 1, 1)]}).with_columns(
        pl.col("d").cast(pl.Date)
    )
    model = PolarsTableModel(df, chunk_size=10)

    index = model.index(0, 0)
    assert model.setData(index, "2024-01-31", role=2) is True
    assert model._data["d"][0] == datetime.date(2024, 1, 31)
