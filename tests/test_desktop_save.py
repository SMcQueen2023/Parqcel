"""Desktop save/open/close regressions using real worker threads and Qt delivery."""

import threading

import polars as pl
import pytest
from PyQt6.QtWidgets import QFileDialog, QMessageBox
from PyQt6.QtTest import QAbstractItemModelTester

import app.main_window as window_module
from app.background_tasks import has_active_tasks
from app.main_window import MainWindow
from models.polars_table_model import PolarsTableModel
from parqcel.core.io import write_dataset_atomic


@pytest.fixture
def desktop(qtbot, monkeypatch, tmp_path):
    errors = []
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Discard,
    )
    monkeypatch.setattr(
        QMessageBox, "critical", lambda *args, **kwargs: errors.append(args[2])
    )
    output = tmp_path / "saved.parquet"
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName", lambda *args, **kwargs: (str(output), "")
    )
    window = MainWindow()
    qtbot.addWidget(window)
    window.set_model(
        PolarsTableModel(pl.DataFrame({"a": [1, 2]}), source_path="original.parquet")
    )
    assert window.model.setData(window.model.index(0, 0), "10")
    window.show()
    yield window, output, errors
    # Keep widget destruction behind real worker completion even if an assertion
    # fails, so a failed test cannot leave a running QThread behind.
    qtbot.waitUntil(lambda: not has_active_tasks(window), timeout=10000)
    window._close_ready = True
    window.close()


@pytest.fixture
def delayed_writer(monkeypatch):
    started = threading.Event()
    release = threading.Event()
    calls = []

    def write(frame, path):
        calls.append(frame.clone())
        started.set()
        if not release.wait(5):
            raise TimeoutError("Test did not release its writer")
        write_dataset_atomic(frame, path)

    monkeypatch.setattr(window_module, "write_dataset_atomic", write)
    yield started, release, calls
    release.set()


def test_edit_during_save_keeps_newer_revision_dirty(desktop, delayed_writer, qtbot):
    window, output, errors = desktop
    started, release, _calls = delayed_writer
    proceeded = []
    window.save_parquet(on_saved=lambda: proceeded.append(True))
    qtbot.waitUntil(started.is_set)
    window.model.setData(window.model.index(0, 0), "20")
    release.set()
    qtbot.waitUntil(lambda: not has_active_tasks(window))
    assert pl.read_parquet(output)["a"].to_list() == [10, 2]
    assert window.model.get_dataframe()["a"].to_list() == [20, 2]
    assert window.model.session.dirty
    assert window.model.session.source_path == "original.parquet"
    assert not proceeded and not errors


def test_save_completion_cannot_relabel_newly_opened_dataset(
    desktop, delayed_writer, qtbot, monkeypatch, tmp_path
):
    window, output, errors = desktop
    started, release, _calls = delayed_writer
    new_path = tmp_path / "new.parquet"
    pl.DataFrame({"new": [7]}).write_parquet(new_path)
    monkeypatch.setattr(
        QFileDialog, "getOpenFileName", lambda *args, **kwargs: (str(new_path), "")
    )
    window.save_parquet()
    qtbot.waitUntil(started.is_set)
    old_model = window.model
    window.open_file()
    qtbot.waitUntil(lambda: window.model is not old_model)
    release.set()
    qtbot.waitUntil(lambda: not has_active_tasks(window))
    assert window.model.session.source_path == str(new_path)
    assert window.model.get_dataframe().columns == ["new"]
    assert not window.model.session.dirty
    assert pl.read_parquet(output)["a"].to_list() == [10, 2]
    assert not errors


def test_duplicate_saves_do_not_race_and_latest_revision_can_be_saved_later(
    desktop, delayed_writer, qtbot
):
    window, output, errors = desktop
    started, release, calls = delayed_writer
    window.save_parquet()
    qtbot.waitUntil(started.is_set)
    window.model.setData(window.model.index(0, 0), "20")
    assert window.save_parquet() is None
    assert len(calls) == 1
    release.set()
    qtbot.waitUntil(lambda: not has_active_tasks(window))
    assert window.model.session.dirty
    window.save_parquet()
    qtbot.waitUntil(lambda: not has_active_tasks(window))
    assert len(calls) == 2
    assert pl.read_parquet(output)["a"].to_list() == [20, 2]
    assert not window.model.session.dirty
    assert not errors


def test_cancelled_save_does_not_acknowledge_but_allows_a_later_save(
    desktop, delayed_writer, qtbot
):
    window, output, errors = desktop
    started, release, _calls = delayed_writer
    proceeded = []
    window.save_parquet(on_saved=lambda: proceeded.append(True))
    qtbot.waitUntil(started.is_set)
    window.cancel_work()
    release.set()
    qtbot.waitUntil(lambda: not has_active_tasks(window))
    # Cancellation suppresses completion actions, not an already running write.
    assert output.exists()
    assert window.model.session.dirty
    assert not proceeded
    window.save_parquet()
    qtbot.waitUntil(lambda: not has_active_tasks(window))
    assert not window.model.session.dirty
    assert not errors


def test_save_before_close_waits_for_saved_revision(
    desktop, delayed_writer, qtbot, monkeypatch
):
    window, output, errors = desktop
    started, release, _calls = delayed_writer
    monkeypatch.setattr(
        QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Save
    )
    window.close()
    qtbot.waitUntil(started.is_set)
    assert window.isVisible()
    assert not window._close_ready
    release.set()
    qtbot.waitUntil(lambda: window._close_ready)
    assert not window.isVisible()
    assert not window.model.session.dirty
    assert pl.read_parquet(output)["a"].to_list() == [10, 2]
    assert not errors


def test_failed_save_preserves_dirty_document_and_does_not_continue(
    desktop, qtbot, monkeypatch
):
    window, output, errors = desktop
    proceeded = []

    def fail_write(_frame, _path):
        raise PermissionError("Destination is read-only")

    monkeypatch.setattr(window_module, "write_dataset_atomic", fail_write)
    window.save_parquet(on_saved=lambda: proceeded.append(True))
    qtbot.waitUntil(lambda: not has_active_tasks(window))
    assert window.model.session.dirty
    assert window.model.session.source_path == "original.parquet"
    assert not proceeded and not output.exists()
    assert errors == ["Destination is read-only"]


def test_dirty_open_and_close_cancel_leave_document_untouched(
    desktop, monkeypatch, tmp_path
):
    window, _output, errors = desktop
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Cancel,
    )
    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileName",
        lambda *args, **kwargs: (str(tmp_path / "missing.parquet"), ""),
    )
    model = window.model
    window.open_file()
    window.close()
    assert window.model is model
    assert model.session.dirty
    assert window.isVisible()
    assert not has_active_tasks(window)
    assert not errors


def test_dirty_open_after_save_loads_only_after_success(
    desktop, delayed_writer, qtbot, monkeypatch, tmp_path
):
    window, output, errors = desktop
    started, release, _calls = delayed_writer
    path = tmp_path / "next.parquet"
    pl.DataFrame({"next": [8]}).write_parquet(path)
    monkeypatch.setattr(
        QFileDialog, "getOpenFileName", lambda *args, **kwargs: (str(path), "")
    )
    monkeypatch.setattr(
        QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Save
    )
    original = window.model
    window.open_file()
    qtbot.waitUntil(started.is_set)
    assert window.model is original
    release.set()
    qtbot.waitUntil(lambda: window.model is not original)
    qtbot.waitUntil(lambda: not has_active_tasks(window))
    assert window.model.session.source_path == str(path)
    assert not window.model.session.dirty
    assert pl.read_parquet(output)["a"].to_list() == [10, 2]
    assert not errors


def test_model_reset_contract_during_desktop_mutations(desktop, qtlog):
    window, _output, _errors = desktop
    model = window.model
    tester = QAbstractItemModelTester(
        model, QAbstractItemModelTester.FailureReportingMode.Warning, window
    )
    model.add_column("b", 3)
    model.drop_column("a")
    model.undo()
    model.setData(model.index(1, 0), "4")
    model.sort_column("a", ascending=False)
    model.undo()
    model.redo()
    assert tester.model() is model
    assert not [record for record in qtlog.records if "FAIL!" in record.message]
