import csv
import io
import threading

import polars as pl
import pytest
from PyQt6.QtCore import QItemSelection, QItemSelectionModel, QSettings
from PyQt6.QtWidgets import QApplication

from app.background_tasks import has_active_tasks
from app.widgets.data_grid import DataGrid
from models.polars_table_model import PolarsTableModel


@pytest.fixture
def grid(qtbot, tmp_path):
    preferences = QSettings(str(tmp_path / "grid.ini"), QSettings.Format.IniFormat)
    widget = DataGrid(settings_store=preferences)
    qtbot.addWidget(widget)
    widget.resize(900, 500)
    widget.show()
    yield widget
    widget.close()
    qtbot.waitUntil(lambda: not has_active_tasks(widget))


def select(grid, top, left, bottom, right):
    model = grid.table_view.model()
    selection = QItemSelection(model.index(top, left), model.index(bottom, right))
    grid.table_view.selectionModel().select(
        selection, QItemSelectionModel.SelectionFlag.ClearAndSelect
    )


def clipboard_rows():
    return list(
        csv.reader(io.StringIO(QApplication.clipboard().text()), delimiter="\t")
    )


def test_copy_uses_raw_values_visible_visual_order_and_tsv_quoting(grid):
    frame = pl.DataFrame(
        {
            "id": pl.Series([2**63 + 1, 2**63 + 3], dtype=pl.UInt64),
            "hidden": [1.5, 2.5],
            "text": ["embedded\ttab", 'line one\n"line two"'],
        }
    )
    model = PolarsTableModel(frame)
    grid.set_model(model)
    grid.set_column_format("id", "number", 2, True)
    grid.table_view.horizontalHeader().moveSection(2, 0)
    grid.table_view.setColumnHidden(1, True)
    select(grid, 0, 0, 1, 2)
    assert grid.copy_selection(include_headers=True)
    assert clipboard_rows() == [
        ["text", "id"],
        ["embedded\ttab", str(2**63 + 1)],
        ['line one\n"line two"', str(2**63 + 3)],
    ]
    assert model.session.revision == 0
    assert not model.session.dirty


def test_copy_preserves_float_and_nanosecond_precision_despite_display_format(grid):
    frame = pl.DataFrame(
        {
            "value": [0.12345678912345678],
            "when": pl.Series([1_700_000_000_123456789]).cast(pl.Datetime("ns")),
        }
    )
    model = PolarsTableModel(frame)
    grid.set_model(model)
    grid.set_column_format("value", "number", 2)
    assert model.data(model.index(0, 0)) == "0.12"
    select(grid, 0, 0, 0, 1)
    assert grid.copy_selection()
    row = clipboard_rows()[0]
    assert float(row[0]) == frame["value"][0]
    assert row[1].endswith(".123456789")


def test_nonrectangular_and_oversized_copy_leave_clipboard_unchanged(grid, monkeypatch):
    messages = []
    monkeypatch.setattr(
        "app.widgets.data_grid.QMessageBox.warning",
        lambda *args: messages.append(args[2]),
    )
    model = PolarsTableModel(pl.DataFrame({"a": [1, 2], "b": [3, 4]}))
    grid.set_model(model)
    QApplication.clipboard().setText("unchanged")
    selection = grid.table_view.selectionModel()
    selection.select(model.index(0, 0), QItemSelectionModel.SelectionFlag.Select)
    selection.select(model.index(1, 1), QItemSelectionModel.SelectionFlag.Select)
    assert not grid.copy_selection()
    assert "rectangular" in messages[-1]
    monkeypatch.setattr("app.widgets.data_grid.MAX_COPY_CELLS", 2)
    select(grid, 0, 0, 1, 1)
    assert not grid.copy_selection()
    assert "at most 2 cells" in messages[-1]
    assert QApplication.clipboard().text() == "unchanged"


def test_selection_aggregates_exclude_null_and_boolean(grid, qtbot):
    model = PolarsTableModel(
        pl.DataFrame({"number": [1, None, 3], "flag": [True, False, None]})
    )
    grid.set_model(model)
    select(grid, 0, 0, 2, 1)
    qtbot.waitUntil(lambda: "Sum 4" in grid.selection_summary.text())
    text = grid.selection_summary.text()
    assert "Selected 6" in text
    assert "Nulls 2" in text
    assert "Finite numbers 2" in text
    assert "Average 2" in text
    assert "Min 1" in text and "Max 3" in text


def test_find_navigates_whole_editor_dataset_and_wraps(grid, qtbot):
    frame = pl.DataFrame({"value": ["no"] * 7 + ["needle", "needle", "no"]})
    model = PolarsTableModel(frame, chunk_size=3)
    grid.set_model(model)
    grid.find_input.setText("needle")
    grid.start_find()
    qtbot.waitUntil(lambda: model.get_current_page() == 2)
    assert grid.table_view.currentIndex().row() == 1
    grid.start_find()
    qtbot.waitUntil(lambda: grid.table_view.currentIndex().row() == 2)
    grid.start_find()
    qtbot.waitUntil(lambda: grid.table_view.currentIndex().row() == 1)
    grid.start_find(backwards=True)
    qtbot.waitUntil(lambda: grid.table_view.currentIndex().row() == 2)


def test_edit_discards_late_find_result(grid, qtbot, monkeypatch):
    from app.widgets import data_grid

    started = threading.Event()
    release = threading.Event()
    original_find = data_grid.find_match

    def delayed_find(*args, **kwargs):
        started.set()
        if not release.wait(5):
            raise RuntimeError("Search was not released")
        return original_find(*args, **kwargs)

    monkeypatch.setattr(data_grid, "find_match", delayed_find)
    model = PolarsTableModel(
        pl.DataFrame({"value": ["a", "b", "needle"]}), chunk_size=1
    )
    grid.set_model(model)
    grid.find_input.setText("needle")
    try:
        grid.start_find()
        qtbot.waitUntil(started.is_set)
        assert model.setData(model.index(0, 0), "edited")
        release.set()
        qtbot.waitUntil(lambda: not has_active_tasks(grid))
        assert model.get_current_page() == 0
        assert model.get_dataframe()["value"][0] == "edited"
    finally:
        release.set()
        qtbot.waitUntil(lambda: not has_active_tasks(grid))


def test_go_to_row_uses_dataset_coordinates(grid):
    model = PolarsTableModel(pl.DataFrame({"id": range(25)}), chunk_size=10)
    grid.set_model(model)
    assert grid.go_to_row(23)
    assert model.get_current_page() == 2
    assert grid.table_view.currentIndex().row() == 2
    assert not grid.go_to_row(0)
    assert not grid.go_to_row(26)


def test_view_preferences_survive_new_model_without_mutating_data(grid):
    frame = pl.DataFrame({"a": [1.234], "b": [2], "c": [3]})
    first = PolarsTableModel(frame)
    grid.set_model(first, identity="saved.parquet")
    grid.set_column_format("a", "number", 3, True)
    grid.table_view.setColumnWidth(1, 219)
    grid.table_view.setColumnHidden(1, True)
    grid.table_view.horizontalHeader().moveSection(2, 0)
    grid.save_view_state()
    second = PolarsTableModel(frame)
    grid.set_model(second, identity="saved.parquet")
    assert second.column_format("a") == {
        "mode": "number",
        "precision": 3,
        "thousands": True,
    }
    assert grid.table_view.isColumnHidden(1)
    assert grid.table_view.horizontalHeader().logicalIndex(0) == 2
    grid.table_view.setColumnHidden(1, False)
    assert grid.table_view.columnWidth(1) == 219
    assert second.session.revision == 0 and not second.session.dirty


def test_set_identity_preserves_current_selection_and_saves_preferences(grid):
    model = PolarsTableModel(pl.DataFrame({"value": [1.23, 4.56]}))
    grid.set_model(model)
    select(grid, 1, 0, 1, 0)
    grid.set_column_format("value", "percent", 1)
    grid.set_identity("new.parquet")
    assert grid.table_view.selectionModel().isSelected(model.index(1, 0))
    assert model.session.revision == 0
    assert grid._settings.value(grid._settings_key())


def test_rename_is_undoable_and_keeps_column_view_preferences(grid):
    model = PolarsTableModel(pl.DataFrame({"before": [1.23], "other": [7]}))
    grid.set_model(model)
    grid.set_column_format("before", "number", 1)
    grid.table_view.setColumnHidden(0, True)
    grid.table_view.horizontalHeader().moveSection(0, 1)
    grid.rename_column("before", "after")
    assert model.get_column_names() == ["after", "other"]
    assert model.column_format("after")["precision"] == 1
    assert grid.table_view.isColumnHidden(0)
    assert model.session.dirty
    model.undo()
    assert model.get_column_names() == ["before", "other"]
    assert grid.table_view.isColumnHidden(0)
    assert grid.table_view.horizontalHeader().visualIndex(0) == 1
    assert model.column_format("before")["precision"] == 1
    model.redo()
    assert grid.table_view.isColumnHidden(0)
    model.undo()
    with pytest.raises(ValueError):
        grid.rename_column("before", "")


def test_profile_runs_on_dataset_and_inspector_retains_raw_cell(grid, qtbot):
    model = PolarsTableModel(
        pl.DataFrame({"id": [2**63 + 1, 2**63 + 3]}, schema={"id": pl.UInt64}),
        chunk_size=1,
    )
    grid.set_model(model)
    grid.inspector_action.setChecked(True)
    grid.table_view.setCurrentIndex(model.index(0, 0))
    assert grid.cell_value.toPlainText() == str(2**63 + 1)
    grid.profile_current_column()
    qtbot.waitUntil(lambda: grid.profile_tree.topLevelItemCount() > 0)
    values = {
        grid.profile_tree.topLevelItem(i)
        .text(0): grid.profile_tree.topLevelItem(i)
        .text(1)
        for i in range(grid.profile_tree.topLevelItemCount())
    }
    assert values["Count"] == "2"
    assert values["Min"] == str(2**63 + 1)
    assert values["Max"] == str(2**63 + 3)


def test_preview_scope_search_go_to_and_profile_only_use_current_page(grid, qtbot):
    from models.preview_table_model import PreviewTableModel

    model = PreviewTableModel()
    grid.set_model(model, scope_label="Current preview page")
    model.replace_page(pl.DataFrame({"text": ["first", "needle"]}), 100)
    assert not grid.rename_action.isEnabled()
    assert grid.find_scope.text() == "Current preview page"
    grid.find_input.setText("needle")
    grid.start_find()
    qtbot.waitUntil(lambda: "Row 102" in grid.find_status.text())
    assert grid.table_view.currentIndex().row() == 1
    assert grid.go_to_row(1)
    assert not grid.go_to_row(101)
    grid.profile_current_column()
    qtbot.waitUntil(lambda: grid.profile_tree.topLevelItemCount() > 0)
    values = {
        grid.profile_tree.topLevelItem(i)
        .text(0): grid.profile_tree.topLevelItem(i)
        .text(1)
        for i in range(grid.profile_tree.topLevelItemCount())
    }
    assert values["Count"] == "2"


def test_preview_initial_empty_model_does_not_erase_saved_preferences(grid):
    from models.preview_table_model import PreviewTableModel

    editor = PolarsTableModel(pl.DataFrame({"value": [1.23]}))
    grid.set_model(editor, identity="shared.parquet")
    grid.set_column_format("value", "number", 1)
    grid.table_view.setColumnWidth(0, 260)
    grid.save_view_state()
    preview = PreviewTableModel()
    grid.set_model(
        preview, identity="shared.parquet", scope_label="Current preview page"
    )
    preview.replace_page(pl.DataFrame({"value": [2.34]}), 50)
    assert preview.column_format("value")["precision"] == 1
    assert grid.table_view.columnWidth(0) == 260


def test_preview_page_change_discards_late_profile(grid, qtbot, monkeypatch):
    from app.widgets import data_grid
    from models.preview_table_model import PreviewTableModel

    started = threading.Event()
    release = threading.Event()
    original = data_grid.column_profile

    def delayed_profile(*args):
        started.set()
        if not release.wait(5):
            raise RuntimeError("Profile was not released")
        return original(*args)

    monkeypatch.setattr(data_grid, "column_profile", delayed_profile)
    model = PreviewTableModel()
    model.replace_page(pl.DataFrame({"value": [1, 2]}), 0)
    grid.set_model(model, scope_label="Current preview page")
    try:
        grid.profile_current_column()
        qtbot.waitUntil(started.is_set)
        model.replace_page(pl.DataFrame({"value": [99]}), 2)
        release.set()
        qtbot.waitUntil(lambda: not has_active_tasks(grid))
        assert grid.profile_tree.topLevelItemCount() == 0
        assert grid.profile_status.text() == "Profile scope: Current preview page"
    finally:
        release.set()
        qtbot.waitUntil(lambda: not has_active_tasks(grid))


def test_prepare_close_prevents_pending_summary_and_new_work(grid, qtbot, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "app.widgets.data_grid.run_in_background",
        lambda *args, **kwargs: calls.append(args),
    )
    grid.set_model(PolarsTableModel(pl.DataFrame({"value": [1, 2]})))
    select(grid, 0, 0, 1, 0)
    assert grid._summary_timer.isActive()
    grid.prepare_close()
    grid.find_input.setText("1")
    grid.start_find()
    grid.profile_current_column()
    grid._update_selection_summary()
    qtbot.wait(100)
    assert not grid._summary_timer.isActive()
    assert calls == []


def test_oversized_clipboard_text_and_summary_are_bounded(grid, qtbot, monkeypatch):
    messages = []
    monkeypatch.setattr(
        "app.widgets.data_grid.QMessageBox.warning",
        lambda *args: messages.append(args[2]),
    )
    monkeypatch.setattr("app.widgets.data_grid.MAX_COPY_BYTES", 10)
    monkeypatch.setattr("app.widgets.data_grid.MAX_AGGREGATE_CELLS", 1)
    grid.set_model(PolarsTableModel(pl.DataFrame({"text": ["a" * 40, "b"]})))
    select(grid, 0, 0, 1, 0)
    QApplication.clipboard().setText("original")
    assert not grid.copy_selection()
    assert QApplication.clipboard().text() == "original"
    assert messages
    qtbot.waitUntil(lambda: "at most 1 cells" in grid.selection_summary.text())


@pytest.mark.parametrize("operation", ["find", "profile", "summary"])
def test_rapid_requests_use_one_worker_and_only_latest_pending_request(
    grid, qtbot, monkeypatch, operation
):
    from app.widgets import data_grid

    started = threading.Event()
    release = threading.Event()
    calls = []
    function = {
        "find": "find_match",
        "profile": "column_profile",
        "summary": "_selection_statistics",
    }[operation]
    original = getattr(data_grid, function)

    def gated(*args, **kwargs):
        calls.append(args)
        if len(calls) == 1:
            started.set()
            if not release.wait(5):
                raise RuntimeError("Operation was not released")
        return original(*args, **kwargs)

    monkeypatch.setattr(data_grid, function, gated)
    model = PolarsTableModel(
        pl.DataFrame({"a": ["needle", "other", "latest"], "b": [1, 2, 3]})
    )
    grid.set_model(model)
    if operation == "find":
        grid.find_input.setText("needle")
        submit = grid.start_find
    elif operation == "profile":
        submit = grid.profile_current_column
    else:
        select(grid, 0, 1, 0, 1)
        grid._summary_timer.stop()
        submit = grid._update_selection_summary
    try:
        submit()
        qtbot.waitUntil(started.is_set)
        if operation == "find":
            grid.find_input.setText("latest")
        elif operation == "profile":
            grid.set_current_column(1)
        else:
            select(grid, 0, 1, 2, 1)
            grid._summary_timer.stop()
        for _ in range(4):
            submit()
        qtbot.wait(50)
        assert len(calls) == 1
        release.set()
        qtbot.waitUntil(lambda: not has_active_tasks(grid))
        assert len(calls) == 2
        if operation == "find":
            assert grid.table_view.currentIndex().row() == 2
        elif operation == "profile":
            assert grid.profile_status.text().startswith("b ")
        else:
            assert "Selected 3" in grid.selection_summary.text()
            assert "Sum 6" in grid.selection_summary.text()
    finally:
        release.set()
        grid.cancel_pending_work()
        qtbot.waitUntil(lambda: not has_active_tasks(grid))
