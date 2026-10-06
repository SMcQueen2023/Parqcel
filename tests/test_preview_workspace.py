import threading

import polars as pl
import pytest
from PyQt6.QtCore import QItemSelectionModel, Qt

from app.background_tasks import has_active_tasks
from app.main_window import MainWindow
from app.preview_window import PreviewTableModel, PreviewWindow
from app.widgets.data_grid import DataGrid
from models.preview_table_model import PreviewTableModel as SharedPreviewTableModel


def _open(qtbot, tmp_path, monkeypatch):
    path = tmp_path / "sales.parquet"
    pl.DataFrame(
        {"order": ["a", "b", "c", "d"], "amount": [10, 20, 30, 40]}
    ).write_parquet(path)
    monkeypatch.setattr(
        pl,
        "read_parquet",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("Preview must stay lazy")),
    )
    window = PreviewWindow(path, page_size=2)
    qtbot.addWidget(window)
    window.show()
    qtbot.waitUntil(lambda: not has_active_tasks(window), timeout=5000)
    return window


def test_preview_uses_shared_read_only_workspace_and_scoped_actions(
    qtbot, tmp_path, monkeypatch
):
    window = _open(qtbot, tmp_path, monkeypatch)
    assert isinstance(window.grid, DataGrid)
    assert PreviewTableModel is SharedPreviewTableModel
    assert window.table_view is window.grid.table_view
    assert window.table_view.model() is window.model
    assert window.title_label.text() == "sales.parquet"
    assert "Read-only" in window.mode_badge.text()
    assert "current preview page" in window.subtitle_label.text()
    assert window.model.rowCount() == 2
    assert not window.model.flags(window.model.index(0, 0)) & Qt.ItemFlag.ItemIsEditable
    actions = window.toolbar.actions()
    for action in (
        window.grid.copy_action,
        window.grid.find_action,
        window.grid.columns_action,
        window.grid.inspector_action,
    ):
        assert action in actions
    assert window.grid.rename_action not in actions
    assert window.page_label.text() == "Page 1 of 2"
    assert window.table_view.verticalHeader().defaultSectionSize() == 27


def test_preview_copy_uses_only_selected_current_page_cells(
    qtbot, qapp, tmp_path, monkeypatch
):
    window = _open(qtbot, tmp_path, monkeypatch)
    window.load_page(1)
    qtbot.waitUntil(lambda: not has_active_tasks(window), timeout=5000)
    selection = window.table_view.selectionModel()
    selection.select(
        window.model.index(0, 1), QItemSelectionModel.SelectionFlag.ClearAndSelect
    )
    window.grid.copy_action.trigger()
    assert qapp.clipboard().text().strip() == "30"
    assert window.model.frame.height == 2
    assert window.page_label.text() == "Page 2 of 2"
    assert window.page_input.text() == "2"


def test_preview_close_discards_pending_page_delivery(qtbot, tmp_path, monkeypatch):
    window = _open(qtbot, tmp_path, monkeypatch)
    source = window.source
    real_fetch = source.fetch_page
    started, release = threading.Event(), threading.Event()
    fetched = []

    def fetch(page):
        fetched.append(page)
        started.set()
        if not release.wait(3):
            raise RuntimeError("Page test timed out")
        return real_fetch(page)

    monkeypatch.setattr(source, "fetch_page", fetch)
    try:
        window.load_page(1)
        qtbot.waitUntil(started.is_set, timeout=3000)
        window.load_page(0)
        window.close()
        release.set()
        qtbot.waitUntil(lambda: not has_active_tasks(window), timeout=5000)
        assert fetched == [1]
    finally:
        release.set()
        qtbot.waitUntil(lambda: not has_active_tasks(), timeout=5000)


@pytest.mark.parametrize("first_fails", [False, True])
def test_preview_navigation_coalesces_to_one_latest_pending_page(
    qtbot, tmp_path, monkeypatch, first_fails
):
    path = tmp_path / "pages.parquet"
    pl.DataFrame({"value": range(50)}).write_parquet(path)
    window = PreviewWindow(path, page_size=10)
    qtbot.addWidget(window)
    qtbot.waitUntil(lambda: not has_active_tasks(window), timeout=5000)
    source = window.source
    real_fetch = source.fetch_page
    started, release = threading.Event(), threading.Event()
    fetched = []
    active = 0
    maximum_active = 0
    lock = threading.Lock()

    def fetch(page):
        nonlocal active, maximum_active
        with lock:
            active += 1
            maximum_active = max(maximum_active, active)
            fetched.append(page)
        try:
            if page == 1:
                started.set()
                if not release.wait(3):
                    raise RuntimeError("Page test timed out")
                if first_fails:
                    raise OSError("Superseded page failed")
            return real_fetch(page)
        finally:
            with lock:
                active -= 1

    monkeypatch.setattr(source, "fetch_page", fetch)
    try:
        window.load_page(1)
        qtbot.waitUntil(started.is_set, timeout=3000)
        for page in (2, 3, 4, 2, 3):
            window.load_page(page)
        assert window.page_index == 0
        release.set()
        qtbot.waitUntil(lambda: not has_active_tasks(window), timeout=5000)
        assert maximum_active == 1
        assert fetched == [1, 3]
        assert window.page_index == 3
        assert window.model.frame["value"].to_list() == list(range(30, 40))
        assert window.page_label.text() == "Page 4 of 5"
    finally:
        release.set()
        qtbot.waitUntil(lambda: not has_active_tasks(window), timeout=5000)


def test_main_window_cancellation_drops_queued_preview_and_allows_later_navigation(
    qtbot, tmp_path, monkeypatch
):
    path = tmp_path / "pages.parquet"
    pl.DataFrame({"value": range(30)}).write_parquet(path)
    parent = MainWindow()
    qtbot.addWidget(parent)
    window = PreviewWindow(path, parent=parent, page_size=10)
    qtbot.addWidget(window)
    qtbot.waitUntil(lambda: not has_active_tasks(parent), timeout=5000)
    source = window.source
    real_fetch = source.fetch_page
    started, release = threading.Event(), threading.Event()
    fetched = []

    def fetch(page):
        fetched.append(page)
        if page == 1:
            started.set()
            if not release.wait(3):
                raise RuntimeError("Page test timed out")
        return real_fetch(page)

    monkeypatch.setattr(source, "fetch_page", fetch)
    try:
        window.load_page(1)
        qtbot.waitUntil(started.is_set, timeout=3000)
        window.load_page(2)
        parent.cancel_work()
        release.set()
        qtbot.waitUntil(lambda: not has_active_tasks(parent), timeout=5000)
        assert fetched == [1]
        assert window.page_index == 0
        assert not window._page_fetch_active
        assert window._pending_page is None
        window.load_page(2)
        qtbot.waitUntil(lambda: not has_active_tasks(parent), timeout=5000)
        assert fetched == [1, 2]
        assert window.page_index == 2
        assert window.model.frame["value"].to_list() == list(range(20, 30))
    finally:
        release.set()
        qtbot.waitUntil(lambda: not has_active_tasks(parent), timeout=5000)
