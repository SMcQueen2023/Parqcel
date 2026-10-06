from datetime import datetime

import polars as pl
import pytest
from PyQt6.QtCore import QItemSelectionModel, QPersistentModelIndex, Qt
from PyQt6.QtTest import QAbstractItemModelTester, QSignalSpy
from PyQt6.QtWidgets import QTableView

from models.polars_table_model import PolarsTableModel
from models.preview_table_model import PreviewTableModel


@pytest.fixture(params=["editor", "preview"])
def formatted_model(request, qapp):
    frame = pl.DataFrame(
        {
            "id": pl.Series([2**64 - 1, None], dtype=pl.UInt64),
            "ratio": [0.125, 0.5],
            "timestamp": [datetime(2024, 1, 2, 3, 4, 5), None],
            "text": ["<b>raw</b>", ""],
            "nested": [[1, None], [2]],
        }
    )
    if request.param == "editor":
        return PolarsTableModel(frame)
    model = PreviewTableModel()
    model.replace_page(frame, 0)
    return model


def test_formatting_is_view_only_with_exact_edit_and_tooltip_text(formatted_model):
    model = formatted_model
    before = model.page_dataframe()
    session = getattr(model, "session", None)
    revision = session.revision if session else None
    model.set_column_format("id", "number", precision=2, thousands=True)
    index = model.index(0, 0)
    assert model.data(index) == "18,446,744,073,709,551,615.00"
    assert model.data(index, Qt.ItemDataRole.EditRole) == str(2**64 - 1)
    assert model.raw_value(index) == 2**64 - 1
    tooltip = model.data(index, Qt.ItemDataRole.ToolTipRole)
    assert "UInt64" in tooltip and str(2**64 - 1) in tooltip
    assert "18,446" not in tooltip
    assert (
        model.data(index, Qt.ItemDataRole.TextAlignmentRole)
        & Qt.AlignmentFlag.AlignRight
    )
    assert model.data(model.index(1, 0)) == "null"
    assert model.data(model.index(1, 0), Qt.ItemDataRole.EditRole) == ""
    assert model.page_dataframe().equals(before)
    if session:
        assert session.revision == revision
        assert not session.dirty and not session.can_undo


def test_percent_scientific_dates_and_unformatted_nested_content(formatted_model):
    model = formatted_model
    model.set_column_format("ratio", "percent", 1)
    assert model.data(model.index(0, 1)) == "12.5%"
    assert model.data(model.index(0, 1), Qt.ItemDataRole.EditRole) == "0.125"
    model.set_column_format("ratio", "scientific", 2)
    assert model.data(model.index(0, 1)) == "1.25E-1"
    model.set_column_format("timestamp", "date")
    assert model.data(model.index(0, 2)) == "2024-01-02"
    assert "03:04:05" in model.data(model.index(0, 2), Qt.ItemDataRole.EditRole)
    assert "&lt;b&gt;" in model.data(model.index(0, 3), Qt.ItemDataRole.ToolTipRole)
    assert model.data(model.index(0, 4)) == "[1, null]"
    assert model.data(model.index(1, 3)) == ""


def test_format_preferences_and_page_access_are_copies(formatted_model):
    model = formatted_model
    options = model.column_format("ratio")
    options["mode"] = "percent"
    assert model.column_format("ratio")["mode"] == "auto"
    snapshot = model.page_dataframe()
    snapshot.drop_in_place("ratio")
    assert "ratio" in model.get_column_names()
    with pytest.raises(ValueError):
        model.set_column_format("missing")
    with pytest.raises(ValueError):
        model.set_column_format("ratio", "unsupported")
    with pytest.raises(ValueError):
        model.set_column_format("ratio", precision=16)


def test_edit_preserves_selection_and_persistent_index_without_reset(qtbot, qtlog):
    model = PolarsTableModel(pl.DataFrame({"a": [1, 2, 3]}), chunk_size=2)
    table = QTableView()
    qtbot.addWidget(table)
    table.setModel(model)
    tester = QAbstractItemModelTester(
        model, QAbstractItemModelTester.FailureReportingMode.Warning, table
    )
    index = model.index(1, 0)
    table.setCurrentIndex(index)
    table.selectionModel().select(
        index, QItemSelectionModel.SelectionFlag.ClearAndSelect
    )
    persistent = QPersistentModelIndex(index)
    resets = QSignalSpy(model.modelReset)
    changes = QSignalSpy(model.dataChanged)
    datasets = QSignalSpy(model.dataset_changed)
    assert model.setData(index, "7")
    assert persistent.isValid() and persistent.row() == 1
    assert table.currentIndex() == index
    assert table.selectionModel().selectedIndexes() == [index]
    assert len(resets) == 0 and len(changes) == 1 and len(datasets) == 1
    assert model.data(index, Qt.ItemDataRole.EditRole) == "7"
    assert tester.model() is model
    assert not [record for record in qtlog.records if "FAIL!" in record.message]
    model.load_next_page()
    assert model.headerData(0, Qt.Orientation.Vertical) == "3"


def test_rename_is_validated_single_undoable_commit_and_keeps_format(qapp):
    model = PolarsTableModel(pl.DataFrame({"a": [1], "b": [2]}))
    model.set_column_format("a", "number", 3)
    model.rename_column("a", "renamed")
    assert model.get_column_names() == ["renamed", "b"]
    assert model.session.revision == 1 and len(model._undo_stack) == 1
    assert model.column_format("renamed")["precision"] == 3
    model.undo()
    assert model.get_column_names() == ["a", "b"]
    assert model.column_format("a")["precision"] == 3
    model.redo()
    assert model.get_column_names() == ["renamed", "b"]
    before = model.session.revision
    for old, new in [("missing", "c"), ("renamed", "b"), ("renamed", " ")]:
        with pytest.raises(ValueError):
            model.rename_column(old, new)
    assert model.session.revision == before


def test_preview_is_read_only_and_formats_survive_page_changes(qapp):
    model = PreviewTableModel()
    model.replace_page(pl.DataFrame({"a": [1.25]}), 0)
    model.set_column_format("a", "number", 1)
    model.replace_page(pl.DataFrame({"a": [2.75]}), 1000)
    index = model.index(0, 0)
    assert model.data(index) == "2.8"
    assert model.headerData(0, Qt.Orientation.Vertical) == "1001"
    assert not model.flags(index) & Qt.ItemFlag.ItemIsEditable
    assert not model.setData(index, "3")


def test_native_timestamp_string_retains_nanoseconds(qapp):
    model = PolarsTableModel(
        pl.DataFrame({"t": pl.Series([1], dtype=pl.Datetime("ns"))})
    )
    index = model.index(0, 0)
    assert model.data(index, Qt.ItemDataRole.EditRole).endswith(".000000001")
    assert ".000000001" in model.data(index, Qt.ItemDataRole.ToolTipRole)


def test_boolean_raw_text_roundtrips_through_typed_editor(qapp):
    model = PolarsTableModel(pl.DataFrame({"flag": [True, False, None]}))
    assert model.data(model.index(0, 0), Qt.ItemDataRole.EditRole) == "true"
    assert model.setData(model.index(0, 0), "false")
    assert model.get_dataframe()["flag"].dtype == pl.Boolean
    assert model.get_dataframe()["flag"][0] is False
    assert model.data(model.index(2, 0)) == "null"
