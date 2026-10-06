import threading

import polars as pl
import pytest
from PyQt6.QtCore import QThread, Qt
from PyQt6.QtWidgets import QWidget

from app.background_tasks import has_active_tasks
from app.preview_window import PreviewWindow
from parqcel.core.parquet_source import ParquetSource


def test_source_reads_pages_and_schema_without_eager_reader(tmp_path, monkeypatch):
    path = tmp_path / "data[preview].parquet"
    frame = pl.DataFrame({"id": range(25), "value": ["x"] * 25})
    frame.write_parquet(path, row_group_size=7)

    def eager_read_forbidden(*args, **kwargs):
        raise AssertionError("Preview must not call the eager reader")

    monkeypatch.setattr(pl, "read_parquet", eager_read_forbidden)
    source = ParquetSource(path, page_size=10)
    assert source.schema == frame.schema
    assert source.row_count == 25
    assert source.page_count == 3
    assert source.fetch_page(0).equals(frame.slice(0, 10))
    assert source.fetch_page(1).equals(frame.slice(10, 10))
    assert source.fetch_page(2).equals(frame.slice(20, 10))
    with pytest.raises(IndexError):
        source.fetch_page(-1)
    with pytest.raises(IndexError):
        source.fetch_page(3)


def test_empty_source_preserves_schema(tmp_path):
    path = tmp_path / "empty.parquet"
    frame = pl.DataFrame(schema={"id": pl.Int64, "label": pl.String})
    frame.write_parquet(path)
    source = ParquetSource(path, page_size=10)
    assert source.row_count == source.page_count == 0
    assert source.fetch_page(0).equals(frame)
    with pytest.raises(IndexError):
        source.fetch_page(1)
    with pytest.raises(ValueError):
        ParquetSource(path, page_size=0)


def test_source_rejects_changed_file(tmp_path):
    path = tmp_path / "data.parquet"
    pl.DataFrame({"value": [1, 2]}).write_parquet(path)
    source = ParquetSource(path)
    pl.DataFrame({"value": range(100)}).write_parquet(path)
    with pytest.raises(OSError, match="changed"):
        source.fetch_page(0)


def test_preview_opens_metadata_off_gui_thread_and_is_read_only(
    qtbot, qapp, tmp_path, monkeypatch
):
    path = tmp_path / "data.parquet"
    pl.DataFrame({"value": range(25)}).write_parquet(path)
    constructor_threads = []
    real_source = ParquetSource

    def source(*args, **kwargs):
        constructor_threads.append(QThread.currentThread())
        return real_source(*args, **kwargs)

    monkeypatch.setattr("app.preview_window.ParquetSource", source)
    window = PreviewWindow(path, page_size=10)
    qtbot.addWidget(window)
    window.show()
    qtbot.waitUntil(lambda: not has_active_tasks(window))
    assert constructor_threads[0] != qapp.thread()
    assert window.model.rowCount() == 10
    assert "25 rows" in window.status_label.text()
    index = window.model.index(0, 0)
    assert not (window.model.flags(index) & Qt.ItemFlag.ItemIsEditable)
    assert window.model.setData(index, "999") is False
    window.load_page(2)
    qtbot.waitUntil(lambda: not has_active_tasks(window))
    assert window.page_index == 2
    assert window.model.rowCount() == 5
    assert window.model.data(window.model.index(0, 0)) == "20"
    assert not window.next_button.isEnabled()


def test_late_page_cannot_overwrite_newer_request(qtbot, tmp_path, monkeypatch):
    path = tmp_path / "data.parquet"
    pl.DataFrame({"value": range(30)}).write_parquet(path)
    window = PreviewWindow(path, page_size=10)
    qtbot.addWidget(window)
    qtbot.waitUntil(lambda: not has_active_tasks(window))
    started = threading.Event()
    release = threading.Event()
    source = window.source
    real_fetch = source.fetch_page

    def delayed_fetch(page):
        if page == 1:
            started.set()
            if not release.wait(5):
                raise RuntimeError("Test did not release page fetch")
        return real_fetch(page)

    monkeypatch.setattr(source, "fetch_page", delayed_fetch)
    try:
        window.load_page(1)
        qtbot.waitUntil(started.is_set)
        window.load_page(2)
        release.set()
        qtbot.waitUntil(lambda: not has_active_tasks(window))
        assert window.page_index == 2
        assert window.model.frame["value"].to_list() == list(range(20, 30))
    finally:
        release.set()
        qtbot.waitUntil(lambda: not has_active_tasks(window))


def test_preview_reports_open_failure(qtbot, tmp_path, monkeypatch):
    messages = []
    monkeypatch.setattr(
        "app.preview_window.QMessageBox.warning",
        lambda *args: messages.append(args[2]),
    )
    window = PreviewWindow(tmp_path / "missing.parquet")
    qtbot.addWidget(window)
    qtbot.waitUntil(lambda: not has_active_tasks(window))
    assert messages and "not found" in messages[0]
    assert window.source is None
    assert not window.next_button.isEnabled()


def test_empty_preview_disables_pagination(qtbot, tmp_path):
    path = tmp_path / "empty.parquet"
    pl.DataFrame(schema={"value": pl.Int64}).write_parquet(path)
    window = PreviewWindow(path)
    qtbot.addWidget(window)
    qtbot.waitUntil(lambda: not has_active_tasks(window))
    assert window.model.rowCount() == 0
    assert window.model.columnCount() == 1
    assert "Empty dataset" in window.status_label.text()
    assert not window.previous_button.isEnabled()
    assert not window.next_button.isEnabled()
    assert not window.jump_button.isEnabled()


def test_closing_preview_discards_pending_open(qtbot, tmp_path, monkeypatch):
    path = tmp_path / "data.parquet"
    pl.DataFrame({"value": [1, 2]}).write_parquet(path)
    started = threading.Event()
    release = threading.Event()
    messages = []

    def delayed_source(*args, **kwargs):
        started.set()
        if not release.wait(5):
            raise RuntimeError("Test did not release preview open")
        return ParquetSource(*args, **kwargs)

    monkeypatch.setattr("app.preview_window.ParquetSource", delayed_source)
    monkeypatch.setattr(
        "app.preview_window.QMessageBox.warning", lambda *args: messages.append(args)
    )
    parent = QWidget()
    qtbot.addWidget(parent)
    window = PreviewWindow(path, parent=parent)
    window.show()
    try:
        qtbot.waitUntil(started.is_set)
        window.close()
        assert has_active_tasks(parent)
        release.set()
        qtbot.waitUntil(lambda: not has_active_tasks(parent))
        assert messages == []
    finally:
        release.set()
        qtbot.waitUntil(lambda: not has_active_tasks(parent))
