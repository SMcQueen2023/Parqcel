"""File workflows of the spreadsheet workspace, including real async output."""

import polars as pl
import pytest
from pathlib import Path
from threading import Event
from PyQt6.QtCore import QMimeData, QPoint, Qt, QUrl
from PyQt6.QtGui import QDragEnterEvent, QDropEvent
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QApplication, QFileDialog, QMessageBox
from PyQt6 import sip

from app.background_tasks import has_active_tasks, run_in_background
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
    assert not window.optimize_action.isEnabled()
    assert not window.next_button.isEnabled()
    assert window.workspace_stack.currentWidget() is window.empty_state
    window.set_model(PolarsTableModel(pl.DataFrame({"a": [1, 2, 3]}), chunk_size=2))
    assert window.save_action.isEnabled()
    assert window.optimize_action.isEnabled()
    assert window.workspace_stack.currentWidget() is window.grid
    assert window.next_button.isEnabled() and not window.prev_button.isEnabled()
    window.load_next_page()
    assert not window.next_button.isEnabled() and window.prev_button.isEnabled()


def test_insert_and_paste_rows_integrate_with_save_history_and_paging(
    workspace, tmp_path, qtbot
):
    window, errors = workspace
    source = tmp_path / "rows.parquet"
    frame = pl.DataFrame({"number": [1, 2], "label": ["a", "b"]})
    frame.write_parquet(source)
    window.set_model(PolarsTableModel(frame, source_path=source, chunk_size=2))
    assert window.grid.add_row_action in window.toolbar.actions()
    assert window.grid.add_row_action.isEnabled()

    window.grid.insert_blank_row(1)
    assert window.model.get_dataframe()["number"].to_list() == [1, None, 2]
    assert "3" in window.row_count_label.text()
    assert window.model.session.dirty
    assert window.undo_action.isEnabled()

    window.save_current()
    qtbot.waitUntil(lambda: not has_active_tasks(window))
    assert pl.read_parquet(source)["number"].to_list() == [1, None, 2]
    assert not window.model.session.dirty
    window.undo()
    assert window.model.get_dataframe().equals(frame)
    assert window.model.session.dirty
    window.redo()
    assert not window.model.session.dirty

    QApplication.clipboard().setText("3\tc\n4\td\n")
    window.grid.paste_rows(2)
    qtbot.waitUntil(lambda: not has_active_tasks(window))
    assert window.model.get_dataframe()["number"].to_list() == [1, None, 3, 4, 2]
    assert window.model.get_current_page() == 1
    assert "5" in window.row_count_label.text()
    assert window.model.session.dirty
    window.undo()
    assert window.model.get_dataframe()["number"].to_list() == [1, None, 2]
    assert not window.model.session.dirty
    assert not errors


def test_optimizer_exports_current_edits_without_mutating_session(
    workspace, tmp_path, qtbot
):
    window, errors = workspace
    source = tmp_path / "source.parquet"
    destination = tmp_path / "optimized.parquet"
    original = pl.DataFrame({"id": [3, 1, 2, 1], "label": ["c", "a", "b", "a"]})
    original.write_parquet(source)
    source_bytes = source.read_bytes()
    window.set_model(PolarsTableModel(original, source_path=source))
    window.model.setData(window.model.index(0, 1), "edited")
    snapshot = window.model.get_dataframe()
    revision = window.model.session.revision
    dialog = window.open_parquet_optimizer()
    assert dialog.windowModality() == Qt.WindowModality.WindowModal
    assert window.open_parquet_optimizer() is dialog
    assert dialog.analyze()
    qtbot.waitUntil(lambda: not has_active_tasks(window), timeout=10000)
    assert dialog.export_button.isEnabled()
    candidate = dialog._selected_candidate()
    expected = (
        snapshot.sort(list(candidate.keys), nulls_last=True, maintain_order=True)
        if candidate.keys
        else snapshot
    )
    assert dialog.export_selected(destination)
    qtbot.waitUntil(lambda: not has_active_tasks(window), timeout=10000)
    assert pl.read_parquet(destination).equals(expected)
    assert source.read_bytes() == source_bytes
    assert window.model.get_dataframe().equals(snapshot)
    assert window.model.session.revision == revision
    assert window.model.session.source_path == str(source)
    assert window.model.session.dirty
    dialog.close()
    window.undo()
    assert window.model.get_dataframe().equals(original)
    assert not window.model.session.dirty
    assert not errors


def test_optimizer_waits_for_pending_file_work(workspace, qtbot):
    window, _ = workspace
    window.set_model(PolarsTableModel(pl.DataFrame({"a": [1]})))
    release = Event()
    try:
        run_in_background(
            window, lambda: release.wait(5), lambda _: None, lambda _: None
        )
        assert window.open_parquet_optimizer() is None
        assert "Wait for active work" in window.statusBar().currentMessage()
    finally:
        release.set()
        qtbot.waitUntil(lambda: not has_active_tasks(window))
    dialog = window.open_parquet_optimizer()
    assert dialog is not None
    dialog.close()


def test_optimizer_invalidated_before_model_or_source_identity_changes(
    workspace, tmp_path, qtbot
):
    window, _ = workspace
    window.set_model(PolarsTableModel(pl.DataFrame({"a": [1]})))
    first = window.open_parquet_optimizer()
    window.set_model(PolarsTableModel(pl.DataFrame({"a": [2]})))
    assert not first.analyze_button.isEnabled()
    assert first._cancel_event.is_set()
    first.close()
    second = window.open_parquet_optimizer()
    window._save_to(str(tmp_path / "new-source.parquet"))
    qtbot.waitUntil(lambda: not has_active_tasks(window))
    assert not second.analyze_button.isEnabled()
    assert second._cancel_event.is_set()
    second.close()


@pytest.mark.parametrize("close_parent", [False, True])
def test_parent_cancellation_reaches_optimizer_and_waits_for_worker(
    workspace, qtbot, monkeypatch, close_parent
):
    window, _ = workspace
    window.set_model(PolarsTableModel(pl.DataFrame({"a": [1]})))
    started, release, cancelled = Event(), Event(), Event()

    def analyze(frame, options, *, cancel, progress):
        started.set()
        if cancel.wait(5):
            cancelled.set()
        release.wait(5)
        raise RuntimeError("A cancelled worker must not deliver this error")

    monkeypatch.setattr("app.widgets.parquet_optimizer_dialog.analyze_parquet", analyze)
    dialog = window.open_parquet_optimizer()
    try:
        assert dialog.analyze()
        qtbot.waitUntil(started.is_set)
        if close_parent:
            window.close()
            assert not window._close_ready
        else:
            window.cancel_work()
        qtbot.waitUntil(cancelled.is_set)
        assert has_active_tasks(window)
    finally:
        release.set()
        qtbot.waitUntil(lambda: not has_active_tasks(window))
    if close_parent:
        qtbot.waitUntil(lambda: window._close_ready)
    else:
        assert dialog.analyze_button.isEnabled()
        dialog.close()


def test_closed_optimizer_blocks_source_changes_until_export_publication_finishes(
    workspace, qtbot, monkeypatch, tmp_path
):
    from parqcel.core import io

    window, _ = workspace
    source = tmp_path / "source.parquet"
    output = tmp_path / "optimized.parquet"
    frame = pl.DataFrame({"id": [2, 1]})
    frame.write_parquet(source)
    model = PolarsTableModel(frame, source_path=source)
    window.set_model(model)
    dialog = window.open_parquet_optimizer()
    assert dialog.analyze()
    qtbot.waitUntil(lambda: not has_active_tasks(window))
    replacing, release = Event(), Event()
    original_replace = io.os.replace

    def replace(temporary, destination):
        replacing.set()
        release.wait(5)
        original_replace(temporary, destination)

    monkeypatch.setattr(io.os, "replace", replace)
    try:
        assert dialog.export_selected(output)
        qtbot.waitUntil(replacing.is_set)
        dialog.close()
        qtbot.waitUntil(lambda: sip.isdeleted(dialog))
        assert window.load_file(str(output)) is None
        window.set_model(PolarsTableModel(pl.DataFrame({"other": [0]})))
        assert window._save_to(str(output)) is None
        assert window.model is model
        assert model.session.source_path == str(source)
        assert "optimized export" in window.statusBar().currentMessage()
    finally:
        release.set()
        qtbot.waitUntil(lambda: not has_active_tasks(window))
    assert output.is_file()
    assert not window._optimizer_export_tasks
    assert pl.read_parquet(source).equals(frame)
    window.load_file(str(output))
    qtbot.waitUntil(lambda: not has_active_tasks(window))
    assert window.model.session.source_path == str(output)
