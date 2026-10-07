"""Measured Parquet layout experiments that export a separate, verified copy."""

from __future__ import annotations

from collections.abc import Callable
import os
from pathlib import Path
from threading import Event
from typing import Any

from PyQt6 import sip
from PyQt6.QtCore import QObject, Qt, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.background_tasks import TaskHandle, run_in_background
from parqcel.core.io import (
    ParquetOperationCancelled,
    write_parquet_verified_atomic,
)
from parqcel.core.parquet_optimizer import (
    CandidateResult,
    OptimizationOptions,
    OptimizationReport,
    analyze_parquet,
    check_working_budget,
    sortable_columns,
    sorted_frame,
)


class _ProgressBridge(QObject):
    # Parentless: a worker can retain and emit this bridge after the dialog's
    # native widget is deleted. Qt disconnects the deleted receiving dialog.
    message = pyqtSignal(int, str)


def _size_text(size: int | None) -> str:
    if size is None:
        return "Not fully tested"
    if size < 1024:
        return f"{size:,} B"
    for unit, divisor in (("GiB", 1024**3), ("MiB", 1024**2), ("KiB", 1024)):
        if size >= divisor:
            return f"{size / divisor:,.2f} {unit}"
    return str(size)


def _order_text(candidate: CandidateResult) -> str:
    return " → ".join(candidate.keys) if candidate.keys else "Original row order"


def _same_file(first: str | Path, second: str | Path) -> bool:
    left, right = Path(first).expanduser(), Path(second).expanduser()
    if os.path.normcase(str(left.resolve())) == os.path.normcase(str(right.resolve())):
        return True
    try:
        return os.path.samefile(left, right)
    except OSError:
        return False


class ParquetOptimizerDialog(QDialog):
    """One captured dataset, one operation at a time, no changes to the editor."""

    export_started = pyqtSignal(object)

    _INITIAL_SUMMARY = (
        "Analyze starts with a row sample, then fully measures the original order and a shortlist. "
        "Only fully measured candidates can be exported."
    )

    def __init__(
        self,
        model: Any,
        parent: QWidget | None = None,
        *,
        current_model: Callable[[], Any] | None = None,
        source_path: str | Path | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Optimize Parquet export")
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.resize(920, 590)
        self._model = model
        self._current_model = (
            current_model if current_model is not None else lambda: model
        )
        self._frame = model.get_dataframe()
        self._session_id = model.session.id
        self._revision = model.session.revision
        self._session_source_path = model.session.source_path
        self._source_path = (
            source_path if source_path is not None else self._session_source_path
        )
        self._report: OptimizationReport | None = None
        self._options = OptimizationOptions()
        self._task: TaskHandle | None = None
        self._cancel_event = Event()
        self._generation = 0
        self._closing = False
        self._snapshot_valid = True
        self._cancel_requested = False
        self._progress_active = False
        self._operation: str | None = None
        self._destination: Path | None = None
        self._progress_bridge = _ProgressBridge()
        self._progress_bridge.message.connect(  # type: ignore[call-arg]
            self._show_progress, type=Qt.ConnectionType.QueuedConnection
        )
        # Event.set does not access a deleted widget, unlike a closure over self.
        self.destroyed.connect(self._cancel_event.set)
        model.dataset_changed.connect(self.validate_snapshot)
        model.destroyed.connect(self.invalidate)

        layout = QVBoxLayout(self)
        title = QLabel("Optimize Parquet export")
        title.setObjectName("workspaceTitle")
        layout.addWidget(title)
        explanation = QLabel(
            "Compare Parquet sizes for a few whole-row sort orders, then export a new copy. "
            "Sorting can change row order in the exported file. Your editor data and saved state stay unchanged."
        )
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        source = (
            Path(self._source_path).name if self._source_path else "Unsaved dataset"
        )
        self.source_label = QLabel(
            f"{source} · {self._frame.height:,} rows · {self._frame.width:,} columns"
        )
        self.source_label.setObjectName("secondaryText")
        self.source_label.setTextFormat(Qt.TextFormat.PlainText)
        self.source_label.setWordWrap(True)
        layout.addWidget(self.source_label)

        self.settings_label = QLabel()
        self.settings_label.setObjectName("secondaryText")
        self.settings_label.setTextFormat(Qt.TextFormat.PlainText)
        self.settings_label.setWordWrap(True)
        self._update_settings_label()
        layout.addWidget(self.settings_label)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Preferred sort column"))
        self.preferred_column = QComboBox()
        self.preferred_column.addItem("No preference", None)
        for column in sortable_columns(self._frame):
            self.preferred_column.addItem(column, column)
        self.preferred_column.currentIndexChanged.connect(self._clear_report)
        controls.addWidget(self.preferred_column, 1)
        self.analyze_button = QPushButton("Analyze")
        self.analyze_button.clicked.connect(self.analyze)
        controls.addWidget(self.analyze_button)
        layout.addLayout(controls)
        tradeoff = QLabel(
            "Consider downstream filtering needs when choosing a preferred column; size alone may not decide the best layout."
        )
        tradeoff.setObjectName("secondaryText")
        tradeoff.setWordWrap(True)
        layout.addWidget(tradeoff)

        self.result_table = QTableWidget(0, 4)
        self.result_table.setHorizontalHeaderLabels(
            ["Row order", "Sample size", "Full size", "Savings vs full baseline"]
        )
        self.result_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.result_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.result_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.result_table.setAlternatingRowColors(True)
        vertical_header = self.result_table.verticalHeader()
        assert vertical_header is not None
        vertical_header.hide()
        header = self.result_table.horizontalHeader()
        assert header is not None
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in (1, 2, 3):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        self.result_table.itemSelectionChanged.connect(self._update_controls)
        layout.addWidget(self.result_table, 1)

        baseline_note = QLabel(
            "Full baseline: original row order rewritten with the same settings, not the current source file size."
        )
        baseline_note.setObjectName("secondaryText")
        baseline_note.setWordWrap(True)
        layout.addWidget(baseline_note)
        self.result_summary = QLabel(self._INITIAL_SUMMARY)
        self.result_summary.setObjectName("secondaryText")
        self.result_summary.setTextFormat(Qt.TextFormat.PlainText)
        self.result_summary.setWordWrap(True)
        layout.addWidget(self.result_summary)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.progress.hide()
        layout.addWidget(self.progress)
        self.status = QLabel("Choose Analyze to compare export sizes.")
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        buttons = QHBoxLayout()
        self.cancel_button = QPushButton("Cancel operation")
        self.cancel_button.clicked.connect(self.cancel_work)
        self.cancel_button.hide()
        buttons.addWidget(self.cancel_button)
        buttons.addStretch()
        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.close)
        buttons.addWidget(self.close_button)
        self.export_button = QPushButton("Export selected…")
        self.export_button.clicked.connect(lambda: self.export_selected())
        buttons.addWidget(self.export_button)
        layout.addLayout(buttons)

        self._validity_timer = QTimer(self)
        self._validity_timer.setInterval(150)
        self._validity_timer.timeout.connect(self.validate_snapshot)
        self._validity_timer.start()
        self._update_controls()

    @property
    def is_busy(self) -> bool:
        return self._task is not None and self._task.is_running

    @property
    def export_destination(self) -> Path | None:
        return (
            self._destination if self.is_busy and self._operation == "export" else None
        )

    def _is_current(self) -> bool:
        if self._closing or not self._snapshot_valid or sip.isdeleted(self._model):
            return False
        try:
            return (
                self._current_model() is self._model
                and self._model.session.id == self._session_id
                and self._model.session.revision == self._revision
                and self._model.session.source_path == self._session_source_path
            )
        except (RuntimeError, AttributeError):
            return False

    @pyqtSlot()
    def validate_snapshot(self) -> bool:
        if self._snapshot_valid and not self._is_current():
            self.invalidate()
        return self._snapshot_valid and not self._closing

    def invalidate(self, reason: object = None) -> None:
        if not self._snapshot_valid:
            return
        self._snapshot_valid = False
        self._generation += 1
        self._progress_active = False
        self._cancel_event.set()
        if self._task is not None:
            self._task.cancel()
        self._report = None
        self.result_table.clearSelection()
        message = (
            reason
            if isinstance(reason, str) and reason
            else (
                "The dataset or source changed. Close and reopen the optimizer to analyze the current data."
            )
        )
        self.status.setText(message)
        self._update_controls()

    def _selected_candidate(self) -> CandidateResult | None:
        row = self.result_table.currentRow()
        if self._report is None or not 0 <= row < len(self._report.candidates):
            return None
        candidate = self._report.candidates[row]
        return candidate if candidate.full_bytes is not None else None

    def _update_controls(self) -> None:
        ready = self._snapshot_valid and not self._closing and not self.is_busy
        self.preferred_column.setEnabled(ready)
        self.analyze_button.setEnabled(ready)
        self.export_button.setEnabled(ready and self._selected_candidate() is not None)
        self.result_table.setEnabled(ready and self._report is not None)
        self.cancel_button.setVisible(self.is_busy and not self._closing)
        self.cancel_button.setEnabled(
            self.is_busy and not self._cancel_event.is_set() and self._snapshot_valid
        )

    def _clear_report(self, *args) -> None:
        if self.is_busy:
            return
        self._report = None
        self.result_table.setRowCount(0)
        self.result_summary.setText(self._INITIAL_SUMMARY)
        self.status.setText("Choose Analyze to compare export sizes.")
        self._update_controls()

    def _update_settings_label(self) -> None:
        options = self._options
        writer = options.write_options
        codec = writer.compression
        if writer.compression_level is not None:
            codec += f" level {writer.compression_level}"
        self.settings_label.setText(
            f"Writer: {codec} · statistics {'on' if writer.statistics else 'off'} · "
            f"row groups {writer.row_group_size:,} · pages {_size_text(writer.data_page_size)}.\n"
            f"Limits: {options.sample_rows:,} sample rows · {options.max_candidates} candidates · "
            f"{options.finalists} finalists · {_size_text(options.max_working_bytes)} estimated working memory · "
            f"{_size_text(options.max_temporary_bytes)} temporary files."
        )

    def _start_operation(self, name: str) -> int:
        self._generation += 1
        self._operation = name
        self._cancel_requested = False
        self._cancel_event.clear()
        self._progress_active = True
        self.progress.show()
        return self._generation

    @pyqtSlot(int, str)
    def _show_progress(self, generation: int, message: str) -> None:
        if (
            generation == self._generation
            and self._progress_active
            and not self._closing
            and self._snapshot_valid
        ):
            self.status.setText(message)

    def analyze(self) -> bool:
        if self.is_busy or not self.validate_snapshot():
            return False
        self._clear_report()
        self._options = OptimizationOptions(
            preferred_column=self.preferred_column.currentData()
        )
        self._update_settings_label()
        generation = self._start_operation("analysis")
        self.status.setText("Preparing size comparisons…")
        frame, options, cancel, bridge = (
            self._frame,
            self._options,
            self._cancel_event,
            self._progress_bridge,
        )

        def completed(report: OptimizationReport) -> None:
            if generation != self._generation or not self.validate_snapshot():
                return
            self._progress_active = False
            self._report = report
            self._populate_results(report)

        def failed(exc: Exception) -> None:
            if generation != self._generation or not self.validate_snapshot():
                return
            self._progress_active = False
            self.status.setText("Analysis did not finish.")
            if not isinstance(exc, ParquetOperationCancelled):
                QMessageBox.warning(self, "Parquet analysis", str(exc))

        self._task = run_in_background(
            self,
            lambda: analyze_parquet(
                frame,
                options,
                cancel=cancel,
                progress=lambda message: bridge.message.emit(generation, message),
            ),
            completed,
            failed,
        )
        self._task.finished.connect(self._task_finished)
        self._update_controls()
        return True

    def _populate_results(self, report: OptimizationReport) -> None:
        self.result_table.setRowCount(len(report.candidates))
        baseline_bytes = report.baseline.full_bytes
        selected = 0
        for row, candidate in enumerate(report.candidates):
            savings = "—"
            if candidate.full_bytes is not None and baseline_bytes:
                difference = (
                    100 * (baseline_bytes - candidate.full_bytes) / baseline_bytes
                )
                savings = (
                    f"{difference:.1f}%"
                    if difference >= 0
                    else f"{abs(difference):.1f}% larger"
                )
            values = (
                _order_text(candidate),
                _size_text(candidate.sample_bytes),
                _size_text(candidate.full_bytes),
                savings,
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                flags = Qt.ItemFlag.ItemIsEnabled
                if candidate.full_bytes is not None:
                    flags |= Qt.ItemFlag.ItemIsSelectable
                item.setFlags(flags)
                if column in (1, 2):
                    size = (
                        candidate.sample_bytes if column == 1 else candidate.full_bytes
                    )
                    if size is not None:
                        item.setToolTip(f"{size:,} bytes")
                self.result_table.setItem(row, column, item)
            if candidate.keys == report.best.keys:
                selected = row
        self.result_table.selectRow(selected)
        best = report.best
        self.result_summary.setText(
            f"Sample: {report.sample_rows:,} of {report.row_count:,} rows. "
            f"Smallest tested full export: {_order_text(best)} · {_size_text(best.full_bytes)}. "
            "This is the smallest tested candidate, not a guarantee of the global minimum. "
            "Sample-only candidates cannot be exported."
        )
        self.status.setText(
            "Original row order was best or tied; it is selected."
            if not best.keys
            else "Analysis complete. Choose a fully measured row order to export."
        )

    def _default_destination(self) -> str:
        if self._source_path:
            source = Path(self._source_path)
            return str(source.with_name(source.stem + ".optimized.parquet"))
        return "dataset.optimized.parquet"

    def export_selected(self, destination: str | Path | None = None) -> bool:
        if self.is_busy or not self.validate_snapshot():
            return False
        candidate = self._selected_candidate()
        if candidate is None or self._report is None:
            return False
        report = self._report
        from_picker = destination is None
        if destination is None:
            chosen, _ = QFileDialog.getSaveFileName(
                self,
                "Export optimized Parquet copy",
                self._default_destination(),
                "Parquet files (*.parquet)",
            )
            if not chosen:
                return False
            destination = chosen
        target = Path(destination).expanduser()
        appended = target.suffix.lower() != ".parquet"
        if appended:
            target = target.with_name(target.name + ".parquet")
        if not self.validate_snapshot():
            return False
        protected = tuple(
            path
            for path in (self._source_path, self._model.session.source_path)
            if path
        )
        if any(_same_file(target, path) for path in protected):
            QMessageBox.warning(
                self,
                "Choose a new copy",
                "The active source file cannot be overwritten. Choose a different export path.",
            )
            return False
        # The standard save picker confirms an exact existing filename. Appending
        # a missing extension changes that filename and needs its own confirmation.
        if target.exists() and (appended or not from_picker):
            answer = QMessageBox.question(
                self,
                "Replace existing file?",
                f"Replace {target.name}?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return False
        if not self.validate_snapshot() or self._report is not report:
            return False
        generation = self._start_operation("export")
        self._destination = target
        self.status.setText("Sorting and writing a verified new copy…")
        frame, keys, options, cancel, optimizer_options = (
            self._frame,
            candidate.keys,
            report.write_options,
            self._cancel_event,
            self._options,
        )

        def export() -> int:
            if cancel.is_set():
                raise ParquetOperationCancelled()
            check_working_budget(frame, optimizer_options, sorting=bool(keys))
            ordered = sorted_frame(frame, keys)
            return write_parquet_verified_atomic(
                ordered,
                target,
                options=options,
                cancel=cancel,
                max_temporary_bytes=optimizer_options.max_temporary_bytes,
                protected_paths=protected,
            )

        def completed(size: int) -> None:
            if generation != self._generation or not self.validate_snapshot():
                return
            self._progress_active = False
            self.status.setText(
                f"Exported {target.name} · {_size_text(size)}. Editor data is unchanged."
            )

        def failed(exc: Exception) -> None:
            if generation != self._generation or not self.validate_snapshot():
                return
            self._progress_active = False
            self.status.setText("No optimized copy was published.")
            if not isinstance(exc, ParquetOperationCancelled):
                QMessageBox.warning(self, "Parquet export", str(exc))

        self._task = run_in_background(self, export, completed, failed)
        self._task.finished.connect(self._task_finished)
        self.export_started.emit(self._task)
        self._update_controls()
        return True

    @pyqtSlot()
    def _task_finished(self) -> None:
        self._progress_active = False
        self.progress.hide()
        if self._cancel_requested and self._snapshot_valid and not self._closing:
            self.status.setText(
                "Operation cancelled. No further result will be applied."
            )
        self._operation = None
        self._destination = None
        self._update_controls()

    def cancel_work(self) -> None:
        if not self.is_busy:
            return
        self._cancel_requested = True
        self._generation += 1
        self._progress_active = False
        self._cancel_event.set()
        assert self._task is not None
        self._task.cancel()
        self.status.setText(
            "Cancelling; waiting for the current native operation to finish…"
        )
        self._update_controls()

    def prepare_close(self) -> None:
        self._closing = True
        self._validity_timer.stop()
        self._cancel_event.set()
        self._generation += 1
        if self._task is not None:
            self._task.cancel()
        self._update_controls()

    def done(self, result: int) -> None:
        self.prepare_close()
        super().done(result)
