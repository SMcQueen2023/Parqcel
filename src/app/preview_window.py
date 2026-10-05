"""An asynchronous, read-only Parquet preview independent of the edit session."""

from __future__ import annotations

from pathlib import Path

import polars as pl
from PyQt6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableView,
    QVBoxLayout,
)

from app.background_tasks import cancel_tasks, run_in_background
from parqcel.core.parquet_source import ParquetSource


class PreviewTableModel(QAbstractTableModel):
    """Present a single page without an editable dataset or history buffer."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.frame = pl.DataFrame()
        self.row_offset = 0

    def replace_page(self, frame: pl.DataFrame, row_offset: int) -> None:
        self.beginResetModel()
        self.frame = frame
        self.row_offset = row_offset
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else self.frame.height

    def columnCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else self.frame.width

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if (
            role != Qt.ItemDataRole.DisplayRole
            or not index.isValid()
            or index.row() >= self.frame.height
            or index.column() >= self.frame.width
        ):
            return None
        value = self.frame[index.row(), index.column()]
        return "" if value is None else str(value)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole or section < 0:
            return None
        if orientation == Qt.Orientation.Horizontal:
            if section >= self.frame.width:
                return None
            return f"{self.frame.columns[section]}\n({self.frame.dtypes[section]})"
        return str(self.row_offset + section + 1)

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable


class PreviewWindow(QDialog):
    def __init__(self, path: str | Path, parent=None, *, page_size: int = 1000) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle(f"Parquet Preview — {Path(path).name}")
        self.resize(900, 600)
        self.source: ParquetSource | None = None
        self.page_index = 0
        self._requested_page = 0
        self._generation = 0
        self._closing = False

        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel("Read-only preview. Open the file in the editor to make changes.")
        )
        self.table_view = QTableView(self)
        self.model = PreviewTableModel(self)
        self.table_view.setModel(self.model)
        layout.addWidget(self.table_view)
        self.status_label = QLabel("Opening Parquet preview…")
        layout.addWidget(self.status_label)
        buttons = QHBoxLayout()
        self.previous_button = QPushButton("Previous")
        self.next_button = QPushButton("Next")
        self.page_input = QLineEdit()
        self.page_input.setPlaceholderText("Page number")
        self.page_input.setMaximumWidth(120)
        self.jump_button = QPushButton("Go")
        self.close_button = QPushButton("Close")
        for widget in (
            self.previous_button,
            self.next_button,
            self.page_input,
            self.jump_button,
            self.close_button,
        ):
            buttons.addWidget(widget)
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

        run_in_background(
            self, open_source, opened, lambda exc: self._error(exc, generation)
        )

    def _update_controls(self) -> None:
        pages = self.source.page_count if self.source is not None else 0
        self.previous_button.setEnabled(not self._closing and self._requested_page > 0)
        self.next_button.setEnabled(
            not self._closing and self._requested_page + 1 < pages
        )
        self.page_input.setEnabled(not self._closing and pages > 0)
        self.jump_button.setEnabled(not self._closing and pages > 0)

    def _display_page(self, page_index: int, frame: pl.DataFrame) -> None:
        assert self.source is not None
        self.page_index = self._requested_page = page_index
        self.model.replace_page(frame, page_index * self.source.page_size)
        if self.source.page_count:
            page_text = f"Page {page_index + 1:,} of {self.source.page_count:,}"
        else:
            page_text = "Empty dataset"
        self.status_label.setText(
            f"{page_text} · {self.source.row_count:,} rows · {len(self.source.schema):,} columns"
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

        def loaded(frame):
            if not self._closing and generation == self._generation:
                self._display_page(page_index, frame)

        run_in_background(
            self,
            lambda: source.fetch_page(page_index),
            loaded,
            lambda exc: self._error(exc, generation),
        )

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
        cancel_tasks(self)
        super().done(result)
