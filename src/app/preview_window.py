"""An asynchronous, read-only Parquet preview independent of the edit session."""

from __future__ import annotations

from pathlib import Path

import polars as pl
from PyQt6.QtCore import Qt, pyqtSlot
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QToolBar,
    QVBoxLayout,
)

from app.background_tasks import TaskHandle, cancel_tasks, run_in_background
from app.icons import line_icon
from app.widgets.data_grid import DataGrid
from models.preview_table_model import PreviewTableModel
from parqcel.core.parquet_source import ParquetSource


class PreviewWindow(QDialog):
    def __init__(self, path: str | Path, parent=None, *, page_size: int = 1000) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle(f"{Path(path).name} — Parqcel Preview")
        self.resize(1080, 700)
        self.setMinimumSize(640, 420)
        self.path = Path(path)
        self.source: ParquetSource | None = None
        self.page_index = 0
        self._requested_page = 0
        self._generation = 0
        self._closing = False
        # Cancellation suppresses delivery but cannot stop a Parquet decode.
        # Keep at most one decode running and replace the queued destination.
        self._page_fetch_active = True
        self._page_task: TaskHandle | None = None
        self._pending_page: tuple[int, int] | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 12)
        layout.setSpacing(10)
        heading = QHBoxLayout()
        self.title_label = QLabel(self.path.name)
        self.title_label.setObjectName("workspaceTitle")
        self.title_label.setTextFormat(Qt.TextFormat.PlainText)
        self.title_label.setWordWrap(True)
        self.title_label.setToolTip(str(self.path))
        self.mode_badge = QLabel("Read-only preview")
        self.mode_badge.setObjectName("modeBadge")
        heading.addWidget(self.title_label, 1)
        heading.addWidget(self.mode_badge)
        layout.addLayout(heading)
        self.subtitle_label = QLabel(
            "Search, selection summaries, and column profiles use the current preview page."
        )
        self.subtitle_label.setObjectName("workspaceSubtitle")
        self.subtitle_label.setWordWrap(True)
        layout.addWidget(self.subtitle_label)

        self.grid = DataGrid(self)
        self.table_view = self.grid.table_view
        self.table_view.verticalHeader().setDefaultSectionSize(27)
        self.model = PreviewTableModel(self)
        self.grid.set_model(
            self.model,
            identity=str(self.path.resolve()),
            scope_label="Current preview page",
        )
        self.toolbar = QToolBar("Preview actions", self)
        self.toolbar.setMovable(False)
        self.toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        for action, name in (
            (self.grid.copy_action, "copy"),
            (self.grid.copy_headers_action, "copy"),
            (self.grid.find_action, "find"),
            (self.grid.columns_action, "columns"),
            (self.grid.inspector_action, "inspector"),
        ):
            action.setIcon(line_icon(name))
        self.toolbar.addAction(self.grid.copy_action)
        self.toolbar.addAction(self.grid.copy_headers_action)
        self.toolbar.addSeparator()
        self.toolbar.addAction(self.grid.find_action)
        self.toolbar.addAction(self.grid.go_to_action)
        self.toolbar.addSeparator()
        self.toolbar.addAction(self.grid.columns_action)
        self.toolbar.addAction(self.grid.format_action)
        self.toolbar.addAction(self.grid.inspector_action)
        layout.addWidget(self.toolbar)
        layout.addWidget(self.grid, 1)
        self.status_label = QLabel("Opening Parquet preview…")
        self.status_label.setObjectName("secondaryText")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        buttons = QHBoxLayout()
        buttons.setSpacing(7)
        self.previous_button = QPushButton("Previous")
        self.next_button = QPushButton("Next")
        self.previous_button.setIcon(line_icon("previous"))
        self.next_button.setIcon(line_icon("next"))
        self.page_label = QLabel("Page —")
        self.page_label.setObjectName("secondaryText")
        self.page_input = QLineEdit()
        self.page_input.setPlaceholderText("Page number")
        self.page_input.setAccessibleName("Preview page number")
        self.page_input.setMaximumWidth(100)
        self.jump_button = QPushButton("Go")
        self.close_button = QPushButton("Close")
        for widget in (self.previous_button, self.next_button, self.page_label):
            buttons.addWidget(widget)
        buttons.addStretch(1)
        for control in (self.page_input, self.jump_button, self.close_button):
            buttons.addWidget(control)
        layout.addLayout(buttons)
        self.previous_button.clicked.connect(
            lambda: self.load_page(self._requested_page - 1)
        )
        self.next_button.clicked.connect(
            lambda: self.load_page(self._requested_page + 1)
        )
        self.jump_button.clicked.connect(self._jump)
        self.page_input.returnPressed.connect(self._jump)
        self.close_button.clicked.connect(self.accept)
        self._update_controls()

        self._generation += 1
        generation = self._generation

        def open_source():
            source = ParquetSource(path, page_size=page_size)
            return source, source.fetch_page(0)

        def opened(result):
            if self._closing or generation != self._generation:
                return
            self.source, frame = result
            self._display_page(0, frame)

        self._page_task = run_in_background(
            self,
            open_source,
            opened,
            lambda exc: self._error(exc, generation),
        )
        self._page_task.finished.connect(self._page_fetch_finished)

    def _update_controls(self) -> None:
        pages = self.source.page_count if self.source is not None else 0
        self.previous_button.setEnabled(not self._closing and self._requested_page > 0)
        self.next_button.setEnabled(
            not self._closing and self._requested_page + 1 < pages
        )
        self.page_input.setEnabled(not self._closing and pages > 0)
        self.jump_button.setEnabled(not self._closing and pages > 0)
        self.toolbar.setEnabled(not self._closing and self.source is not None)

    def _display_page(self, page_index: int, frame: pl.DataFrame) -> None:
        assert self.source is not None
        self.page_index = self._requested_page = page_index
        self.model.replace_page(frame, page_index * self.source.page_size)
        if self.source.page_count:
            page_text = f"Page {page_index + 1:,} of {self.source.page_count:,}"
        else:
            page_text = "Empty dataset"
        self.page_label.setText(page_text)
        self.page_input.setText(str(page_index + 1) if self.source.page_count else "")
        self.status_label.setText(
            f"{self.source.row_count:,} rows · {len(self.source.schema):,} columns"
            f" · {frame.height:,} rows on this page"
            if self.source.page_count
            else f"Empty dataset · {len(self.source.schema):,} columns"
        )
        self._update_controls()

    def load_page(self, page_index: int) -> None:
        source = self.source
        if self._closing or source is None or not 0 <= page_index < source.page_count:
            return
        self._generation += 1
        generation = self._generation
        self._requested_page = page_index
        self.status_label.setText(f"Loading page {page_index + 1:,}…")
        self._update_controls()
        if self._page_fetch_active:
            self._pending_page = (page_index, generation)
        else:
            self._start_page_fetch(page_index, generation)

    def _start_page_fetch(self, page_index: int, generation: int) -> None:
        source = self.source
        if self._closing or source is None:
            return
        self._page_fetch_active = True

        def loaded(frame):
            if not self._closing and generation == self._generation:
                self._display_page(page_index, frame)

        self._page_task = run_in_background(
            self,
            lambda: source.fetch_page(page_index),
            loaded,
            lambda exc: self._error(exc, generation),
        )
        self._page_task.finished.connect(self._page_fetch_finished)

    @pyqtSlot()
    def _page_fetch_finished(self) -> None:
        # Unlike result callbacks, this signal also runs after parent-level
        # cancellation. A bound Qt slot disconnects when the window is deleted.
        task, self._page_task = self._page_task, None
        self._page_fetch_active = False
        pending, self._pending_page = self._pending_page, None
        if self._closing:
            return
        if task is not None and task.cancelled:
            self._requested_page = self.page_index
            self.status_label.setText("Preview loading cancelled.")
            self._update_controls()
            return
        if not self._closing and pending is not None:
            self._start_page_fetch(*pending)

    def _jump(self) -> None:
        try:
            page = int(self.page_input.text()) - 1
        except ValueError:
            return
        self.load_page(page)

    def _error(self, exc: Exception, generation: int) -> None:
        if self._closing or generation != self._generation:
            return
        self._requested_page = self.page_index
        self.status_label.setText("Could not load preview page.")
        self._update_controls()
        QMessageBox.warning(self, "Parquet Preview", str(exc))

    def done(self, result: int) -> None:
        self._closing = True
        self._generation += 1
        self._pending_page = None
        self.grid.prepare_close()
        cancel_tasks(self)
        super().done(result)
