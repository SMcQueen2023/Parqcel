import polars as pl
import datetime
import pytest
from PyQt6.QtCore import Qt, QModelIndex
from PyQt6.QtTest import QSignalSpy

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


def test_drop_column_undo_redo_restores_columns(qapp):
    df = pl.DataFrame({"a": [1, 2], "b": [3, 4], "c": [5, 6]})
    model = PolarsTableModel(df, chunk_size=10)

    model.drop_column("b")
    assert model._data.columns == ["a", "c"]

    model.undo()
    assert model._data.columns == ["a", "b", "c"]
    assert model.columnCount() == 3
    assert "b" in model._column_types

    model.redo()
    assert model._data.columns == ["a", "c"]
    assert model.columnCount() == 2


def test_drop_column_clears_redo_after_new_mutation(qapp):
    df = pl.DataFrame({"a": [1, 2], "b": [3, 4]})
    model = PolarsTableModel(df, chunk_size=10)

    model.drop_column("b")
    model.undo()
    assert model._data.columns == ["a", "b"]

    model.add_column("c", 0)
    assert model._data.columns == ["a", "b", "c"]

    model.redo()
    assert model._data.columns == ["a", "b", "c"]


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


@pytest.mark.parametrize(
    "dtype,initial,edit,expected",
    [
        (pl.Boolean, True, "false", False),
        (pl.UInt64, 2**63, str(2**63 + 1), 2**63 + 1),
        (pl.Int8, 1, "-2", -2),
        (pl.Time, datetime.time(1), "02:03:04", datetime.time(2, 3, 4)),
    ],
)
def test_typed_edits_preserve_schema_and_history(qapp, dtype, initial, edit, expected):
    model = PolarsTableModel(pl.DataFrame({"a": pl.Series([initial], dtype=dtype)}))
    changed = QSignalSpy(model.dataset_changed)
    assert model.setData(model.index(0, 0), edit)
    assert model._data["a"][0] == expected
    assert model._data["a"].dtype == dtype
    assert str(dtype) in model.headerData(0, Qt.Orientation.Horizontal)
    assert len(changed) == 1
    model.undo()
    assert model._data["a"][0] == initial
    model.redo()
    assert model._data["a"][0] == expected
    assert len(changed) == 3


def test_failed_edit_keeps_redo_and_revision(qapp):
    model = PolarsTableModel(pl.DataFrame({"a": pl.Series([1], dtype=pl.Int8)}))
    model.setData(model.index(0, 0), "2")
    model.undo()
    revision = model.session.revision
    changed = QSignalSpy(model.dataset_changed)
    assert not model.setData(model.index(0, 0), "128")
    assert not model.setData(QModelIndex(), "2")
    assert model.session.revision == revision
    assert len(model._undo_stack) == 0 and len(model._redo_stack) == 1
    assert len(changed) == 0
    model.redo()
    assert model._data["a"][0] == 2


def test_sort_undo_and_pagination_signals(qapp):
    model = PolarsTableModel(pl.DataFrame({"a": [3, 2, 1]}), chunk_size=2)
    changed = QSignalSpy(model.dataset_changed)
    pages = QSignalSpy(model.pagination_changed)
    model.load_next_page()
    assert model.rowCount() == 1
    assert len(pages) == 1 and len(changed) == 0
    assert model.rowCount(model.index(0, 0)) == 0
    assert model.setData(model.index(0, 0), "5")
    assert model._data["a"].to_list() == [3, 2, 5]
    model.sort_column("a")
    assert model._data["a"].to_list() == [2, 3, 5]
    model.undo()
    assert model._data["a"].to_list() == [3, 2, 5]
    model.redo()
    assert model._data["a"].to_list() == [2, 3, 5]


def test_complex_columns_read_only_and_dataframe_access_is_snapshot(qapp):
    model = PolarsTableModel(pl.DataFrame({"a": [[1]], "b": [2]}))
    assert not model.flags(model.index(0, 0)) & Qt.ItemFlag.ItemIsEditable
    assert not model.setData(model.index(0, 0), "[3]")
    model.get_dataframe().drop_in_place("b")
    assert model.columnCount() == 2
    with pytest.raises(ValueError):
        PolarsTableModel(pl.DataFrame({"a": [1]}), chunk_size=0)
