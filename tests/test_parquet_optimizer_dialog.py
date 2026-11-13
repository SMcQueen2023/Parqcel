import os
import threading
from types import SimpleNamespace

import polars as pl
import pytest
from PyQt6 import sip
from PyQt6.QtCore import QItemSelectionModel, QThread, Qt
from PyQt6.QtWidgets import QMessageBox

from app.background_tasks import has_active_tasks
from app.widgets import parquet_optimizer_dialog as optimizer_ui
from app.widgets.parquet_optimizer_dialog import ParquetOptimizerDialog
from models.polars_table_model import PolarsTableModel
from parqcel.core.io import DEFAULT_PARQUET_OPTIONS
from parqcel.core.parquet_optimizer import (
    CandidateResult,
    OptimizationReport,
    sorted_frame,
)


@pytest.fixture
def frame():
    return pl.DataFrame(
        {"key": [3, 1, 2, 1], "value": ["third", "first", "second", "last"]}
    )


@pytest.fixture
def report(frame):
    baseline = CandidateResult((), 1000, 2000, 0.01)
    best = CandidateResult(("key",), 600, 1500, 0.01)
    sample_only = CandidateResult(("value",), 500, None, 0.01)
    return OptimizationReport(
        (baseline, best, sample_only),
        baseline,
        best,
        frame.height,
        frame.height,
        DEFAULT_PARQUET_OPTIONS,
    )


@pytest.fixture
def make_dialog(qtbot, frame):
    dialogs = []

    def create(*, source_path=None):
        model = PolarsTableModel(frame, source_path=source_path)
        active_model = [model]
        dialog = ParquetOptimizerDialog(
            model, current_model=lambda: active_model[0], source_path=source_path
        )
        # This fixture owns cleanup because WA_DeleteOnClose intentionally
        # deletes widgets in the lifetime tests before pytest-qt teardown.
        dialog.show()
        dialogs.append(dialog)
        return dialog, model, active_model

    yield create
    for dialog in dialogs:
        if not sip.isdeleted(dialog):
            dialog.prepare_close()
            dialog.close()
        qtbot.waitUntil(lambda: not has_active_tasks(dialog))


def analyze_ready(dialog, qtbot):
    assert dialog.analyze()
    qtbot.waitUntil(lambda: not dialog.is_busy)
    assert dialog._report is not None


def test_analysis_is_explicit_and_only_full_measurements_are_exportable(
    make_dialog, qtbot, monkeypatch, report
):
    calls = []
    monkeypatch.setattr(
        optimizer_ui,
        "analyze_parquet",
        lambda *args, **kwargs: calls.append(args) or report,
    )
    dialog, model, _ = make_dialog(source_path="<b>data.parquet")
    assert dialog.windowModality() == Qt.WindowModality.WindowModal
    assert calls == []
    assert not dialog.export_button.isEnabled()
    assert dialog.source_label.textFormat() == Qt.TextFormat.PlainText
    assert dialog.result_summary.textFormat() == Qt.TextFormat.PlainText
    assert dialog.status.textFormat() == Qt.TextFormat.PlainText
    assert "zstd level 3" in dialog.settings_label.text()
    assert "estimated working memory" in dialog.settings_label.text()
    qtbot.mouseClick(dialog.analyze_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: not dialog.is_busy)
    assert len(calls) == 1
    assert dialog.result_table.rowCount() == 3
    assert dialog.result_table.currentRow() == 1
    assert dialog.export_button.isEnabled()
    assert dialog.result_table.item(0, 0).text() == "Original row order"
    assert dialog.result_table.item(1, 3).text() == "25.0%"
    assert dialog.result_table.item(2, 2).text() == "Not fully tested"
    assert not dialog.result_table.item(2, 0).flags() & Qt.ItemFlag.ItemIsSelectable
    index = dialog.result_table.model().index(2, 0)
    dialog.result_table.selectionModel().setCurrentIndex(
        index, QItemSelectionModel.SelectionFlag.NoUpdate
    )
    assert dialog._selected_candidate() is None
    assert not dialog.export_selected("unmeasured.parquet")
    assert "Sample: 4 of 4 rows" in dialog.result_summary.text()
    assert model.session.revision == 0 and not model.session.dirty
    dialog.preferred_column.setCurrentIndex(1)
    assert dialog._report is None
    assert dialog.result_summary.text() == dialog._INITIAL_SUMMARY


def test_preserved_order_is_selected_when_it_is_the_best_full_result(
    make_dialog, qtbot, monkeypatch, report
):
    baseline_report = OptimizationReport(
        report.candidates,
        report.baseline,
        report.baseline,
        report.row_count,
        report.sample_rows,
        report.write_options,
    )
    monkeypatch.setattr(
        optimizer_ui, "analyze_parquet", lambda *args, **kwargs: baseline_report
    )
    dialog, _, _ = make_dialog()
    analyze_ready(dialog, qtbot)
    assert dialog.result_table.currentRow() == 0
    assert "Original row order was best or tied" in dialog.status.text()


def test_real_analysis_and_verified_export_leave_editor_and_source_unchanged(
    make_dialog, qtbot, tmp_path, frame
):
    source = tmp_path / "source.parquet"
    frame.write_parquet(source)
    original_source = source.read_bytes()
    dialog, model, _ = make_dialog(source_path=source)
    analyze_ready(dialog, qtbot)
    selected = dialog._selected_candidate()
    assert selected is not None
    destination = tmp_path / "chosen_copy"
    assert dialog.export_selected(destination)
    qtbot.waitUntil(lambda: not dialog.is_busy)
    exported = tmp_path / "chosen_copy.parquet"
    assert exported.exists()
    assert pl.read_parquet(exported).equals(sorted_frame(frame, selected.keys))
    assert source.read_bytes() == original_source
    assert model.get_dataframe().equals(frame)
    assert model.session.revision == 0 and not model.session.dirty
    assert not model.session.undo_history
    assert "Exported chosen_copy.parquet" in dialog.status.text()


def test_progress_uses_gui_thread_and_cancelled_analysis_recovers_controls(
    make_dialog, qtbot, qapp, monkeypatch, report
):
    started, release = threading.Event(), threading.Event()
    calls, cancel_events, progress_threads = [], [], []

    def gated(frame, options, *, cancel, progress):
        calls.append(threading.get_ident())
        cancel_events.append(cancel)
        progress("Measuring sample 2/3: key")
        started.set()
        if len(calls) == 1 and not release.wait(5):
            raise RuntimeError("Analysis was not released")
        return report

    monkeypatch.setattr(optimizer_ui, "analyze_parquet", gated)
    dialog, _, _ = make_dialog()
    set_text = dialog.status.setText

    def record_status(text):
        progress_threads.append(QThread.currentThread() == qapp.thread())
        set_text(text)

    monkeypatch.setattr(dialog.status, "setText", record_status)
    try:
        assert dialog.analyze()
        qtbot.waitUntil(started.is_set)
        qtbot.waitUntil(lambda: "Measuring sample 2/3" in dialog.status.text())
        assert not dialog.analyze()
        assert len(calls) == 1
        assert not dialog.analyze_button.isEnabled()
        assert not dialog.memory_budget_combo.isEnabled()
        assert not dialog.temporary_budget_combo.isEnabled()
        qtbot.mouseClick(dialog.cancel_button, Qt.MouseButton.LeftButton)
        assert cancel_events[0].is_set()
        assert not dialog.cancel_button.isEnabled()
        assert dialog.is_busy
        release.set()
        qtbot.waitUntil(lambda: not dialog.is_busy)
        assert dialog._report is None
        assert dialog.analyze_button.isEnabled()
        assert dialog.memory_budget_combo.isEnabled()
        assert dialog.temporary_budget_combo.isEnabled()
        assert dialog.progress.isHidden()
        assert dialog.cancel_button.isHidden()
        analyze_ready(dialog, qtbot)
        assert len(calls) == 2
        assert calls[0] != threading.get_ident()
        assert all(progress_threads)
    finally:
        release.set()
        qtbot.waitUntil(lambda: not has_active_tasks(dialog))


@pytest.mark.parametrize("change", ["edit", "replacement", "source"])
def test_dataset_changes_invalidate_report_and_prevent_export(
    make_dialog, qtbot, monkeypatch, report, tmp_path, change
):
    monkeypatch.setattr(optimizer_ui, "analyze_parquet", lambda *args, **kwargs: report)
    dialog, model, active = make_dialog()
    analyze_ready(dialog, qtbot)
    if change == "edit":
        assert model.setData(model.index(0, 0), "99")
    elif change == "replacement":
        active[0] = PolarsTableModel(pl.DataFrame({"key": [8]}))
    else:
        model.mark_saved(model.session.revision, tmp_path / "new_source.parquet")
    qtbot.waitUntil(lambda: not dialog._snapshot_valid)
    assert dialog._report is None
    assert not dialog.export_button.isEnabled()
    assert not dialog.analyze_button.isEnabled()
    assert not dialog.memory_budget_combo.isEnabled()
    assert not dialog.temporary_budget_combo.isEnabled()
    assert not dialog.export_selected(tmp_path / "stale.parquet")
    assert not (tmp_path / "stale.parquet").exists()


def test_edit_discards_late_analysis_result(make_dialog, qtbot, monkeypatch, report):
    started, release = threading.Event(), threading.Event()
    cancellations = []

    def gated(*args, cancel, **kwargs):
        cancellations.append(cancel)
        started.set()
        if not release.wait(5):
            raise RuntimeError("Analysis was not released")
        return report

    monkeypatch.setattr(optimizer_ui, "analyze_parquet", gated)
    dialog, model, _ = make_dialog()
    try:
        assert dialog.analyze()
        qtbot.waitUntil(started.is_set)
        assert model.setData(model.index(0, 0), "42")
        assert cancellations[0].is_set()
        release.set()
        qtbot.waitUntil(lambda: not dialog.is_busy)
        assert dialog._report is None
        assert dialog.result_table.rowCount() == 0
        assert "dataset or source changed" in dialog.status.text()
    finally:
        release.set()
        qtbot.waitUntil(lambda: not has_active_tasks(dialog))


def test_dialog_deletion_cancels_worker_and_late_progress_is_safe(
    make_dialog, qtbot, monkeypatch, report
):
    started, release = threading.Event(), threading.Event()
    cancellations = []

    def gated(*args, cancel, progress, **kwargs):
        cancellations.append(cancel)
        started.set()
        if not release.wait(5):
            raise RuntimeError("Analysis was not released")
        progress("Late message after the dialog closed")
        return report

    monkeypatch.setattr(optimizer_ui, "analyze_parquet", gated)
    dialog, _, _ = make_dialog()
    try:
        assert dialog.analyze()
        qtbot.waitUntil(started.is_set)
        dialog.close()
        qtbot.waitUntil(lambda: sip.isdeleted(dialog))
        assert cancellations[0].is_set()
        assert has_active_tasks(dialog)
        release.set()
        qtbot.waitUntil(lambda: not has_active_tasks(dialog))
    finally:
        release.set()
        qtbot.waitUntil(lambda: not has_active_tasks(dialog))


def test_analysis_failure_releases_busy_state(make_dialog, qtbot, monkeypatch):
    messages = []
    monkeypatch.setattr(
        optimizer_ui.QMessageBox, "warning", lambda *args: messages.append(args[2])
    )

    def failed(*args, **kwargs):
        raise MemoryError("Working budget exceeded")

    monkeypatch.setattr(optimizer_ui, "analyze_parquet", failed)
    dialog, _, _ = make_dialog()
    assert dialog.analyze()
    qtbot.waitUntil(lambda: not dialog.is_busy)
    assert messages == ["Working budget exceeded"]
    assert dialog.analyze_button.isEnabled()
    assert not dialog.export_button.isEnabled()
    assert dialog.progress.isHidden()


def test_file_picker_cancel_is_noop_and_suggests_optimized_copy(
    make_dialog, qtbot, monkeypatch, report, tmp_path
):
    monkeypatch.setattr(optimizer_ui, "analyze_parquet", lambda *args, **kwargs: report)
    choices = []

    def cancelled(*args):
        choices.append(args)
        return "", ""

    monkeypatch.setattr(optimizer_ui.QFileDialog, "getSaveFileName", cancelled)
    dialog, _, _ = make_dialog(source_path=tmp_path / "source.parquet")
    analyze_ready(dialog, qtbot)
    assert not dialog.export_selected()
    assert choices[0][2] == str(tmp_path / "source.optimized.parquet")
    assert not dialog.is_busy
    assert dialog.export_button.isEnabled()


def test_source_path_and_hardlink_alias_are_rejected(
    make_dialog, qtbot, monkeypatch, report, tmp_path, frame
):
    source = tmp_path / "source.parquet"
    frame.write_parquet(source)
    alias = tmp_path / "alias.parquet"
    os.link(source, alias)
    before = source.read_bytes()
    messages = []
    monkeypatch.setattr(
        optimizer_ui.QMessageBox, "warning", lambda *args: messages.append(args[2])
    )
    monkeypatch.setattr(optimizer_ui, "analyze_parquet", lambda *args, **kwargs: report)
    dialog, _, _ = make_dialog(source_path=source)
    analyze_ready(dialog, qtbot)
    assert not dialog.export_selected(source)
    assert not dialog.export_selected(tmp_path / "unused" / ".." / "source.parquet")
    assert not dialog.export_selected(alias)
    if os.name == "nt":
        assert not dialog.export_selected(str(source).upper())
    assert len(messages) >= 3
    assert all("active source file cannot be overwritten" in text for text in messages)
    assert source.read_bytes() == before
    assert alias.read_bytes() == before


def test_appended_extension_confirms_actual_overwrite_and_decline_is_safe(
    make_dialog, qtbot, monkeypatch, report, tmp_path
):
    target = tmp_path / "existing.parquet"
    target.write_bytes(b"previous destination")
    monkeypatch.setattr(optimizer_ui, "analyze_parquet", lambda *args, **kwargs: report)
    monkeypatch.setattr(
        optimizer_ui.QFileDialog,
        "getSaveFileName",
        lambda *args: (str(tmp_path / "existing"), ""),
    )
    questions = []
    monkeypatch.setattr(
        optimizer_ui.QMessageBox,
        "question",
        lambda *args: questions.append(args[2]) or QMessageBox.StandardButton.No,
    )
    dialog, _, _ = make_dialog()
    analyze_ready(dialog, qtbot)
    assert not dialog.export_selected()
    assert questions == ["Replace existing.parquet?"]
    assert target.read_bytes() == b"previous destination"


def test_changes_during_overwrite_confirmation_prevent_export(
    make_dialog, qtbot, monkeypatch, report, tmp_path
):
    target = tmp_path / "existing.parquet"
    target.write_bytes(b"previous destination")
    monkeypatch.setattr(optimizer_ui, "analyze_parquet", lambda *args, **kwargs: report)
    dialog, model, _ = make_dialog()
    analyze_ready(dialog, qtbot)

    def confirm(*args):
        assert model.setData(model.index(0, 0), "77")
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(optimizer_ui.QMessageBox, "question", confirm)
    assert not dialog.export_selected(target)
    assert target.read_bytes() == b"previous destination"
    assert not dialog.is_busy


@pytest.mark.parametrize("operation", ["cancel", "close", "edit"])
def test_export_cancellation_preserves_destination_and_stops_repeat_work(
    make_dialog, qtbot, monkeypatch, report, tmp_path, operation
):
    started, release = threading.Event(), threading.Event()
    target = tmp_path / "existing.parquet"
    target.write_bytes(b"previous destination")
    monkeypatch.setattr(optimizer_ui, "analyze_parquet", lambda *args, **kwargs: report)
    monkeypatch.setattr(
        optimizer_ui.QMessageBox,
        "question",
        lambda *args: QMessageBox.StandardButton.Yes,
    )
    original_write = optimizer_ui.write_parquet_verified_atomic
    calls, cancellations = [], []

    def gated(*args, **kwargs):
        calls.append(args)
        cancellations.append(kwargs["cancel"])
        started.set()
        if not release.wait(5):
            raise RuntimeError("Export was not released")
        return original_write(*args, **kwargs)

    monkeypatch.setattr(optimizer_ui, "write_parquet_verified_atomic", gated)
    dialog, model, _ = make_dialog()
    analyze_ready(dialog, qtbot)
    try:
        assert dialog.export_selected(target)
        qtbot.waitUntil(started.is_set)
        assert dialog.export_destination == target
        assert not dialog.export_selected(tmp_path / "second.parquet")
        assert not dialog.analyze()
        if operation == "cancel":
            dialog.cancel_work()
        elif operation == "close":
            dialog.close()
            qtbot.waitUntil(lambda: sip.isdeleted(dialog))
        else:
            assert model.setData(model.index(0, 0), "55")
        assert cancellations[0].is_set()
        release.set()
        qtbot.waitUntil(lambda: not has_active_tasks(dialog))
        assert len(calls) == 1
        assert target.read_bytes() == b"previous destination"
        assert not (tmp_path / "second.parquet").exists()
        if operation == "cancel":
            assert dialog.export_button.isEnabled()
            assert dialog.cancel_button.isHidden()
    finally:
        release.set()
        qtbot.waitUntil(lambda: not has_active_tasks(dialog))


def test_automatic_budget_resolves_at_analysis_and_export_keeps_report_options(
    make_dialog, qtbot, monkeypatch, report, tmp_path
):
    gib = 1024**3
    available_choice = [2 * gib]
    analyzed, exported, checked = [], [], []
    monkeypatch.setattr(
        optimizer_ui, "recommended_working_budget", lambda: available_choice[0]
    )
    monkeypatch.setattr(
        optimizer_ui,
        "analyze_parquet",
        lambda frame, options, **kwargs: analyzed.append(options) or report,
    )
    original_write = optimizer_ui.write_parquet_verified_atomic
    original_check = optimizer_ui.check_working_budget

    def write(*args, **kwargs):
        exported.append(kwargs)
        return original_write(*args, **kwargs)

    def check(frame, options, **kwargs):
        checked.append(options)
        return original_check(frame, options, **kwargs)

    monkeypatch.setattr(optimizer_ui, "write_parquet_verified_atomic", write)
    monkeypatch.setattr(optimizer_ui, "check_working_budget", check)
    dialog, _, _ = make_dialog()
    assert dialog.memory_budget_combo.currentData() == "auto"
    assert dialog.temporary_budget_combo.currentData() == 4 * gib
    assert dialog._options.max_working_bytes == 2 * gib
    assert "Automatic: 2.00 GiB" in dialog.resource_estimate.text()
    available_choice[0] = gib
    analyze_ready(dialog, qtbot)
    assert analyzed[0].max_working_bytes == gib
    assert analyzed[0].max_temporary_bytes == 4 * gib
    available_choice[0] = 3 * gib
    assert dialog.export_selected(tmp_path / "budgeted.parquet")
    qtbot.waitUntil(lambda: not dialog.is_busy)
    assert checked[0].max_working_bytes == gib
    assert exported[0]["max_temporary_bytes"] == 4 * gib
    assert exported[0]["verification_batch_rows"] == analyzed[0].verification_batch_rows
    assert (tmp_path / "budgeted.parquet").exists()


def test_manual_resource_choices_persist_without_truncating_large_integer_values(
    make_dialog, monkeypatch
):
    gib = 1024**3
    monkeypatch.setattr(optimizer_ui, "recommended_working_budget", lambda: gib)
    first, _, _ = make_dialog()
    first.memory_budget_combo.setCurrentIndex(
        first.memory_budget_combo.findData(8 * gib)
    )
    first.temporary_budget_combo.setCurrentIndex(
        first.temporary_budget_combo.findData(64 * gib)
    )
    assert first._options.max_working_bytes == 8 * gib
    assert first._options.max_temporary_bytes == 64 * gib
    second, _, _ = make_dialog()
    assert second.memory_budget_combo.currentData() == 8 * gib
    assert second.temporary_budget_combo.currentData() == 64 * gib
    assert second._options.max_working_bytes == 8 * gib
    assert "Manual: 8.00 GiB" in second.resource_estimate.text()


@pytest.mark.parametrize(
    "invalid", ["not a budget", -1, 0, True, "999999999999999999999"]
)
def test_invalid_saved_resource_choices_fall_back_to_automatic_and_default_temp(
    make_dialog, monkeypatch, invalid
):
    gib = 1024**3
    store = optimizer_ui.settings()
    store.setValue("optimizer/memory_budget", invalid)
    store.setValue("optimizer/temporary_budget", invalid)
    monkeypatch.setattr(optimizer_ui, "recommended_working_budget", lambda: gib)
    dialog, _, _ = make_dialog()
    assert dialog.memory_budget_combo.currentData() == "auto"
    assert dialog.temporary_budget_combo.currentData() == 4 * gib
    assert dialog._options.max_working_bytes == gib


@pytest.mark.parametrize("control", ["memory_budget_combo", "temporary_budget_combo"])
def test_changing_resource_limits_invalidates_measured_report(
    make_dialog, qtbot, monkeypatch, report, control
):
    monkeypatch.setattr(optimizer_ui, "analyze_parquet", lambda *args, **kwargs: report)
    dialog, _, _ = make_dialog()
    analyze_ready(dialog, qtbot)
    combo = getattr(dialog, control)
    combo.setCurrentIndex(combo.count() - 1)
    assert dialog._report is None
    assert dialog.result_table.rowCount() == 0
    assert not dialog.export_button.isEnabled()
    assert dialog.result_summary.text() == dialog._INITIAL_SUMMARY
    assert not dialog.is_busy


def test_resource_estimates_are_explicit_and_do_not_claim_a_hard_ram_cap(
    make_dialog, monkeypatch
):
    mib = 1024**2
    monkeypatch.setattr(optimizer_ui, "recommended_working_budget", lambda: 512 * mib)
    monkeypatch.setattr(
        optimizer_ui,
        "estimate_working_memory",
        lambda *args, **kwargs: SimpleNamespace(
            input_bytes=256 * mib,
            sort_bytes=300 * mib,
            write_bytes=800 * mib,
            verification_bytes=128 * mib,
            peak_bytes=1024 * mib,
        ),
    )
    dialog, _, _ = make_dialog()
    text = dialog.resource_estimate.text()
    assert "Estimated peak for a full sort/export: 1.00 GiB" in text
    assert "sort 300.00 MiB" in text
    assert "write 800.00 MiB" in text
    assert "verification 128.00 MiB" in text
    assert "Already-loaded input: 256.00 MiB" in text
    assert "undo history and other app memory are additional" in text
    assert "not hard RAM caps" in text
    assert "exceeds this budget" in text
    assert dialog.resource_estimate.textFormat() == Qt.TextFormat.PlainText


def test_resource_changes_are_ignored_during_an_active_operation(
    make_dialog, qtbot, monkeypatch, report
):
    gib = 1024**3
    started, release = threading.Event(), threading.Event()

    def gated(*args, **kwargs):
        started.set()
        if not release.wait(5):
            raise RuntimeError("Analysis was not released")
        return report

    monkeypatch.setattr(optimizer_ui, "analyze_parquet", gated)
    dialog, _, _ = make_dialog()
    dialog.memory_budget_combo.setCurrentIndex(
        dialog.memory_budget_combo.findData(2 * gib)
    )
    try:
        assert dialog.analyze()
        qtbot.waitUntil(started.is_set)
        dialog.memory_budget_combo.setCurrentIndex(
            dialog.memory_budget_combo.findData(8 * gib)
        )
        dialog.temporary_budget_combo.setCurrentIndex(
            dialog.temporary_budget_combo.findData(16 * gib)
        )
        assert dialog.memory_budget_combo.currentData() == 2 * gib
        assert dialog.temporary_budget_combo.currentData() == 4 * gib
        assert dialog._options.max_working_bytes == 2 * gib
        assert dialog._options.max_temporary_bytes == 4 * gib
        release.set()
        qtbot.waitUntil(lambda: not dialog.is_busy)
        dialog.prepare_close()
        assert not dialog.memory_budget_combo.isEnabled()
        assert not dialog.temporary_budget_combo.isEnabled()
    finally:
        release.set()
        qtbot.waitUntil(lambda: not has_active_tasks(dialog))
