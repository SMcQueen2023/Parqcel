"""File workflows of the spreadsheet workspace, including real async output."""

import polars as pl
import pytest
from pathlib import Path
from PyQt6.QtCore import QMimeData, QPoint, Qt, QUrl
from PyQt6.QtGui import QDragEnterEvent, QDropEvent
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QFileDialog, QMessageBox

from app.background_tasks import has_active_tasks
from app.main_window import MainWindow
from models.polars_table_model import PolarsTableModel


@pytest.fixture
def workspace(qtbot, monkeypatch):
    errors = []
    monkeypatch.setattr(QMessageBox, "critical", lambda *a: errors.append(a[2]))
    window = MainWindow()
    qtbot.addWidget(window)
    yield window, errors
    qtbot.waitUntil(lambda: not has_active_tasks(window), timeout=10000)
    window._close_ready = True
    window.close()


def test_save_current_updates_existing_parquet_without_prompt(
    workspace, tmp_path, monkeypatch, qtbot
):
    window, errors = workspace
    path = tmp_path / "current.parquet"
    frame = pl.DataFrame({"value": [1, 2]})
    frame.write_parquet(path)
    window.set_model(PolarsTableModel(frame, source_path=path))
    window.model.setData(window.model.index(0, 0), "42")
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        lambda *a: pytest.fail("Save unexpectedly prompted"),
    )
    window.save_current()
    qtbot.waitUntil(lambda: not has_active_tasks(window))
    assert pl.read_parquet(path)["value"].to_list() == [42, 2]
    assert not window.model.session.dirty
    assert not errors


def test_csv_export_preserves_parquet_identity_and_dirty_history(
    workspace, tmp_path, monkeypatch, qtbot
):
    window, errors = workspace
    path = tmp_path / "data.parquet"
    output = tmp_path / "export.csv"
    window.set_model(PolarsTableModel(pl.DataFrame({"a": [1, 2]}), source_path=path))
    window.model.setData(window.model.index(0, 0), "5")
    revision = window.model.session.revision
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a: (str(output), ""))
    window.export_csv()
    qtbot.waitUntil(lambda: not has_active_tasks(window))
    assert pl.read_csv(output)["a"].to_list() == [5, 2]
    assert window.model.session.dirty
    assert window.model.session.source_path == str(path)
    assert window.model.session.revision == revision
    window.undo()
    assert window.model.get_dataframe()["a"].to_list() == [1, 2]
    assert not errors


def test_save_imported_csv_creates_parquet(workspace, tmp_path, monkeypatch, qtbot):
    window, errors = workspace
    source, output = tmp_path / "source.csv", tmp_path / "output"
    frame = pl.DataFrame({"a": [1]})
    frame.write_csv(source)
    window.set_model(PolarsTableModel(frame, source_path=source))
    window.model.setData(window.model.index(0, 0), "2")
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a: (str(output), ""))
    window.save_current()
    qtbot.waitUntil(lambda: not has_active_tasks(window))
    assert pl.read_csv(source)["a"].to_list() == [1]
    assert pl.read_parquet(output.with_suffix(".parquet"))["a"].to_list() == [2]
    assert window.model.session.source_path == str(output.with_suffix(".parquet"))
    assert not errors


def test_recent_files_preserve_mode_and_are_deduplicated(
    workspace, tmp_path, monkeypatch
):
    window, _ = workspace
    path = tmp_path / "sales.parquet"
    window._remember_file(path, "preview")
    window._remember_file(path, "editor")
    assert window._recent_files() == [{"path": str(path), "mode": "editor"}]
    opened = []
    monkeypatch.setattr(window, "_open_path", opened.append)
    window.recent_menu.actions()[0].trigger()
    assert opened == [str(path)]


def test_parquet_drop_opens_read_only_preview(workspace, tmp_path, monkeypatch):
    window, _ = workspace
    path = tmp_path / "large.parquet"
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(path))])
    opened = []
    monkeypatch.setattr(window, "_show_preview", opened.append)
    enter = QDragEnterEvent(
        QPoint(5, 5),
        Qt.DropAction.CopyAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    window.dragEnterEvent(enter)
    assert enter.isAccepted()
    drop = QDropEvent(
        QPointF(5, 5),
        Qt.DropAction.CopyAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    window.dropEvent(drop)
    assert drop.isAccepted()
    assert [Path(value) for value in opened] == [path]
    assert window.model is None


def test_toolbar_save_actions_and_paging_follow_dataset(workspace):
    window, _ = workspace
    assert not window.save_action.isEnabled()
    assert not window.next_button.isEnabled()
    assert window.workspace_stack.currentWidget() is window.empty_state
    window.set_model(PolarsTableModel(pl.DataFrame({"a": [1, 2, 3]}), chunk_size=2))
    assert window.save_action.isEnabled()
    assert window.workspace_stack.currentWidget() is window.grid
    assert window.next_button.isEnabled() and not window.prev_button.isEnabled()
    window.load_next_page()
    assert not window.next_button.isEnabled() and window.prev_button.isEnabled()
