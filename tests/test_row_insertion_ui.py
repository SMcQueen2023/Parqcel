import threading

import polars as pl
import pytest
from PyQt6.QtCore import QModelIndex, QPoint, Qt
from PyQt6.QtWidgets import QApplication

from app.background_tasks import has_active_tasks
from app.widgets.data_grid import DataGrid
from models.polars_table_model import PolarsTableModel
from models.preview_table_model import PreviewTableModel


@pytest.fixture
def grid(qtbot):
    widget = DataGrid()
    qtbot.addWidget(widget)
    widget.resize(800, 450)
    widget.show()
    yield widget
    widget.prepare_close()
    widget.close()
    qtbot.waitUntil(lambda: not has_active_tasks(widget))


def menu_action(grid, text):
    assert grid._row_insert_menu is not None
    return next(
        action for action in grid._row_insert_menu.actions() if action.text() == text
    )


def test_hover_plus_is_centered_on_boundary_and_click_inserts_there(grid, qtbot):
    model = PolarsTableModel(pl.DataFrame({"value": [10, 20, 30]}))
    grid.set_model(model)
    header = grid.row_header
    y = header.sectionViewportPosition(1)
    qtbot.mouseMove(header.viewport(), QPoint(2, y - 1))
    qtbot.waitUntil(lambda: header.boundary == 1)
    button = header.insert_button
    center = header.viewport().mapFromGlobal(
        button.mapToGlobal(QPoint(button.width() // 2, button.height() // 2))
    )
    assert center.y() == y
    assert abs(center.x() - header.viewport().width() // 2) <= 1
    assert grid._row_boundary_line.isVisible()
    assert grid._row_boundary_line.geometry().y() == y - 1
    assert button.accessibleName() == "Insert above row 2"
    qtbot.mouseClick(button, Qt.MouseButton.LeftButton)
    assert grid._row_insert_menu.actions()[0].text() == "Before row 2"
    menu_action(grid, "Insert blank row").trigger()
    assert model.get_dataframe()["value"].to_list() == [10, None, 20, 30]
    assert grid.table_view.currentIndex().row() == 1
    assert model.session.revision == 1
    model.undo()
    assert model.get_dataframe()["value"].to_list() == [10, 20, 30]


def test_row_centers_keep_native_selection_and_no_insertion_button(grid, qtbot):
    model = PolarsTableModel(pl.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]}))
    grid.set_model(model)
    header = grid.row_header
    y = header.sectionViewportPosition(1) + header.sectionSize(1) // 2
    qtbot.mouseMove(header.viewport(), QPoint(2, y))
    assert header.insert_button.isHidden()
    qtbot.mouseClick(header.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(2, y))
    assert grid.table_view.selectionModel().isRowSelected(1, QModelIndex())
    assert not header.isSortIndicatorShown()
    assert not header.sectionsMovable()


@pytest.mark.parametrize("boundary", [0, 1])
def test_page_endpoints_translate_to_dataset_boundaries(grid, qtbot, boundary):
    model = PolarsTableModel(pl.DataFrame({"value": [0, 1, 2, 3, 4]}), chunk_size=2)
    grid.set_model(model)
    model.jump_to_page(2)
    assert grid.row_header.show_boundary(boundary)
    qtbot.mouseClick(grid.row_header.insert_button, Qt.MouseButton.LeftButton)
    placement = "Before row 5" if boundary == 0 else "After row 5"
    assert grid._row_insert_menu.actions()[0].text() == placement
    menu_action(grid, "Insert blank row").trigger()
    expected = [0, 1, 2, 3, 4]
    expected.insert(4 + boundary, None)
    assert model.get_dataframe()["value"].to_list() == expected
    assert model.get_current_page() == 2
    assert grid.table_view.currentIndex().row() == boundary


def test_boundary_overlay_tracks_resize_and_scroll_and_clips_outside_page(grid, qtbot):
    grid.set_model(PolarsTableModel(pl.DataFrame({"value": range(100)})))
    header = grid.row_header
    assert header.show_boundary(2)
    header.resizeSection(0, header.sectionSize(0) + 10)
    qtbot.waitUntil(
        lambda: grid._row_boundary_line.geometry().y()
        == header.sectionViewportPosition(2) - 1
    )
    grid.resize(700, 400)
    qtbot.waitUntil(
        lambda: grid._row_boundary_line.width() == grid.table_view.viewport().width()
    )
    grid.table_view.verticalScrollBar().setValue(20)
    qtbot.waitUntil(lambda: header.insert_button.isHidden())
    assert grid._row_boundary_line.isHidden()
    assert not header.show_boundary(0)
    assert header.show_boundary(22)
    assert header.insert_button.toolTip() == "Insert above row 23"


def test_empty_typed_dataset_has_accessible_add_row_action(grid):
    model = PolarsTableModel(pl.DataFrame(schema={"id": pl.Int64, "label": pl.String}))
    grid.set_model(model)
    assert grid.add_row_action.isEnabled()
    assert grid.paste_rows_action.isEnabled()
    assert not grid.row_header.show_boundary(0)
    grid.add_row_action.trigger()
    assert grid._row_insert_menu.actions()[0].text() == "First row"
    menu_action(grid, "Insert blank row").trigger()
    assert model.get_dataframe().rows() == [(None, None)]
    assert grid.table_view.currentIndex().isValid()
    assert grid.table_view.currentIndex().row() == 0


def test_last_boundary_button_is_fully_visible_beyond_table_edge(grid, qtbot):
    grid.set_model(PolarsTableModel(pl.DataFrame({"value": range(100)})))
    grid.table_view.setVerticalScrollMode(grid.table_view.ScrollMode.ScrollPerPixel)
    scrollbar = grid.table_view.verticalScrollBar()
    scrollbar.setValue(scrollbar.maximum())
    qtbot.waitUntil(lambda: scrollbar.value() == scrollbar.maximum())
    header = grid.row_header
    assert header.show_boundary(100)
    button = header.insert_button
    assert button.parentWidget() is grid
    assert grid.rect().contains(button.geometry())
    boundary = header.sectionViewportPosition(99) + header.sectionSize(99)
    center = header.viewport().mapFromGlobal(
        button.mapToGlobal(QPoint(button.width() // 2, button.height() // 2))
    )
    assert center.y() == boundary
    assert button.accessibleName() == "Insert below row 100"


def test_preview_has_no_row_insertion_controls(grid):
    model = PreviewTableModel()
    model.replace_page(pl.DataFrame({"value": [1, 2]}), 50)
    grid.set_model(model, scope_label="Current preview page")
    assert not grid.add_row_action.isEnabled()
    assert not grid.paste_rows_action.isEnabled()
    assert not grid.row_header.show_boundary(1)
    assert not grid.insert_blank_row(0)
    assert not grid.paste_rows(0)
    grid.request_row_insertion(1)
    assert grid._row_insert_menu is None
    assert model.frame["value"].to_list() == [1, 2]


def test_insert_selects_first_visible_editable_column(grid):
    model = PolarsTableModel(
        pl.DataFrame({"nested": [[1]], "id": [2], "text": ["original"]})
    )
    grid.set_model(model)
    grid.table_view.setColumnHidden(1, True)
    assert grid.insert_blank_row(0)
    assert grid.table_view.currentIndex().column() == 2


def test_paste_uses_visible_visual_order_and_is_one_undo_step(grid, qtbot):
    original = pl.DataFrame(
        {"id": [1, 2], "hidden": [[3], [4]], "text": ["old", "last"]}
    )
    model = PolarsTableModel(original, chunk_size=2)
    grid.set_model(model)
    grid.table_view.setColumnHidden(1, True)
    grid.table_view.horizontalHeader().moveSection(2, 0)
    QApplication.clipboard().setText('"first\tvalue"\t7\n"second\nvalue"\t8\n')
    assert grid.paste_rows(2)
    qtbot.waitUntil(lambda: not has_active_tasks(grid))
    assert model.get_dataframe().rows() == [
        (1, [3], "old"),
        (2, [4], "last"),
        (7, None, "first\tvalue"),
        (8, None, "second\nvalue"),
    ]
    assert model.session.revision == 1
    assert len(model.session.undo_history) == 1
    assert model.get_current_page() == 1
    assert grid.table_view.currentIndex().column() == 2
    assert grid.table_view.currentIndex().row() == 0
    model.undo()
    assert model.get_dataframe().equals(original)


def test_paste_action_defaults_before_current_row_without_header_inference(grid, qtbot):
    model = PolarsTableModel(pl.DataFrame({"text": ["old", "last"]}))
    grid.set_model(model)
    grid.table_view.setCurrentIndex(model.index(1, 0))
    QApplication.clipboard().setText("text\nvalue")
    grid.paste_rows_action.trigger()
    qtbot.waitUntil(lambda: not has_active_tasks(grid))
    assert model.get_dataframe()["text"].to_list() == ["old", "text", "value", "last"]
    assert grid.paste_rows_action.shortcut().toString() == "Ctrl+Shift+V"


def test_invalid_or_oversized_paste_preserves_data_and_history(
    grid, qtbot, monkeypatch
):
    messages = []
    monkeypatch.setattr(
        "app.widgets.data_grid.QMessageBox.warning",
        lambda *args: messages.append(args[2]),
    )
    original = pl.DataFrame({"id": [1, 2]})
    model = PolarsTableModel(original)
    grid.set_model(model)
    QApplication.clipboard().setText("3\nnot an integer")
    assert grid.paste_rows(1)
    qtbot.waitUntil(lambda: not has_active_tasks(grid))
    assert "row 2" in messages[-1]
    assert model.get_dataframe().equals(original)
    assert model.session.revision == 0
    assert not model.session.undo_history
    monkeypatch.setattr("app.widgets.data_grid.MAX_PASTE_BYTES", 2)
    QApplication.clipboard().setText("123")
    assert not grid.paste_rows(1)
    assert "10 MiB" in messages[-1]
    assert not has_active_tasks(grid)


@pytest.mark.parametrize(
    "change", ["edit", "replace_model", "cancel", "row_cancel", "close"]
)
def test_late_paste_is_discarded_and_repeat_requests_do_not_start_workers(
    grid, qtbot, monkeypatch, change
):
    from app.widgets import data_grid

    started, release = threading.Event(), threading.Event()
    calls = []
    original_insert = data_grid.insert_tsv_rows

    def gated(*args):
        calls.append(args)
        started.set()
        if not release.wait(5):
            raise RuntimeError("Paste was not released")
        return original_insert(*args)

    monkeypatch.setattr(data_grid, "insert_tsv_rows", gated)
    model = PolarsTableModel(pl.DataFrame({"id": [1, 2]}))
    grid.set_model(model)
    QApplication.clipboard().setText("3\n4")
    try:
        assert grid.paste_rows(1)
        qtbot.waitUntil(started.is_set)
        assert not grid.add_row_action.isEnabled()
        assert not grid.paste_rows_action.isEnabled()
        assert grid.row_cancel_button.isVisible()
        assert not grid.row_header.show_boundary(1)
        assert not grid.paste_rows(1)
        assert not grid.insert_blank_row(1)
        if change == "edit":
            assert model.setData(model.index(0, 0), "99")
        elif change == "replace_model":
            grid.set_model(PolarsTableModel(pl.DataFrame({"id": [88]})))
        elif change == "close":
            grid.prepare_close()
        elif change == "row_cancel":
            find_generation = grid._find_generation
            qtbot.mouseClick(grid.row_cancel_button, Qt.MouseButton.LeftButton)
            assert grid._find_generation == find_generation
            assert not grid.row_cancel_button.isEnabled()
            assert not grid.add_row_action.isEnabled()
        else:
            grid.cancel_pending_work()
        release.set()
        qtbot.waitUntil(lambda: not has_active_tasks(grid))
        assert len(calls) == 1
        assert model.get_dataframe()["id"].to_list() == (
            [99, 2] if change == "edit" else [1, 2]
        )
        assert len(model.session.undo_history) == (1 if change == "edit" else 0)
        assert grid.add_row_action.isEnabled() is (change != "close")
        assert grid.row_cancel_button.isHidden()
    finally:
        release.set()
        qtbot.waitUntil(lambda: not has_active_tasks(grid))
