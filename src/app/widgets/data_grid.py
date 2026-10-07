"""Shared spreadsheet interactions for editable and read-only dataset pages."""

from __future__ import annotations

import csv
from collections.abc import Iterable
from decimal import Decimal, InvalidOperation, localcontext
import hashlib
import io
import json
from typing import Any, cast

import polars as pl
from PyQt6.QtCore import (
    QEvent,
    QItemSelectionModel,
    QItemSelectionRange,
    QModelIndex,
    QSettings,
    Qt,
    QTimer,
    pyqtSlot,
)
from PyQt6.QtGui import QAction, QKeySequence, QPalette
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTableView,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.background_tasks import TaskHandle, cancel_tasks, run_in_background
from app.preferences import settings
from app.widgets.row_insertion_header import RowInsertionHeader
from parqcel.core.grid import column_profile, find_match, raw_cell_text, raw_column_text
from parqcel.core.rows import MAX_PASTE_BYTES, insert_tsv_rows

MAX_COPY_CELLS = 100_000
MAX_COPY_BYTES = 10 * 1024 * 1024
MAX_AGGREGATE_CELLS = 50_000
MAX_INSPECTOR_CHARACTERS = 100_000


def _selection_statistics(frame: pl.DataFrame, cells: list[tuple[int, int]]) -> str:
    nulls = 0
    numbers: list[Decimal] = []
    series = [frame.to_series(column) for column in range(frame.width)]
    for row, column in cells:
        value = series[column][row]
        if value is None:
            nulls += 1
        elif series[column].dtype.is_numeric():
            try:
                numeric = Decimal(raw_cell_text(series[column], row))
                if numeric.is_finite():
                    numbers.append(numeric)
            except InvalidOperation:
                pass
    summary = (
        f"Selected {len(cells):,} · Non-null {len(cells) - nulls:,} · Nulls {nulls:,}"
    )
    if numbers:
        with localcontext() as context:
            context.prec = 80
            total = sum(numbers, Decimal(0))
            average = total / len(numbers)
        summary += (
            f" · Finite numbers {len(numbers):,} · Sum {total:g}"
            f" · Average {average:.12g} · Min {min(numbers):g} · Max {max(numbers):g}"
        )
    return summary


class ColumnsDialog(QDialog):
    def __init__(self, grid: DataGrid) -> None:
        super().__init__(grid)
        self.setWindowTitle("Columns")
        self.resize(420, 480)
        self._grid = grid
        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel("Choose visible columns. Drag grid headers to reorder.")
        )
        self.search = QLineEdit()
        self.search.setPlaceholderText("Find a column…")
        layout.addWidget(self.search)
        self.columns = QListWidget()
        names = grid._column_names()
        for logical in grid._visual_columns(include_hidden=True):
            item = QListWidgetItem(names[logical], self.columns)
            item.setData(Qt.ItemDataRole.UserRole, logical)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Unchecked
                if grid.table_view.isColumnHidden(logical)
                else Qt.CheckState.Checked
            )
        layout.addWidget(self.columns)
        self.search.textChanged.connect(self._filter)
        show_all = QPushButton("Show all")
        show_all.clicked.connect(self._show_all)
        layout.addWidget(show_all)
        self.fit = QCheckBox("Fit visible columns to sampled values")
        layout.addWidget(self.fit)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _filter(self, text: str) -> None:
        for index in range(self.columns.count()):
            item = self.columns.item(index)
            if item is not None:
                item.setHidden(text.casefold() not in item.text().casefold())

    def _show_all(self) -> None:
        for index in range(self.columns.count()):
            item = self.columns.item(index)
            if item is not None:
                item.setCheckState(Qt.CheckState.Checked)

    def accept(self) -> None:
        states = []
        for index in range(self.columns.count()):
            item = self.columns.item(index)
            if item is not None:
                states.append(
                    (
                        item.data(Qt.ItemDataRole.UserRole),
                        item.checkState() == Qt.CheckState.Checked,
                    )
                )
        if states and not any(visible for _, visible in states):
            QMessageBox.warning(self, "Columns", "Keep at least one column visible.")
            return
        for logical, visible in states:
            self._grid.table_view.setColumnHidden(logical, not visible)
        if self.fit.isChecked():
            self._grid.auto_fit_columns()
        self._grid.save_view_state()
        self._grid._selection_changed()
        super().accept()


class DataGrid(QWidget):
    """Bounded page interactions plus asynchronous dataset search and profiling."""

    def __init__(self, parent=None, *, settings_store: QSettings | None = None) -> None:
        super().__init__(parent)
        self._settings = settings_store if settings_store is not None else settings()
        self._model: Any = None
        self._identity = ""
        self._scope_label = "Dataset"
        self._view_state: dict[str, Any] = {}
        self._column_widths: dict[str, int] = {}
        self._restoring = False
        self._closing = False
        self._active_column = 0
        self._generation = 0
        self._find_generation = 0
        self._summary_generation = 0
        self._profile_generation = 0
        self._find_task: TaskHandle | None = None
        self._profile_task: TaskHandle | None = None
        self._summary_task: TaskHandle | None = None
        self._row_task: TaskHandle | None = None
        self._row_generation = 0
        self._row_result_applied = False
        self._row_insert_menu: QMenu | None = None
        self._pending_find: bool | None = None
        self._pending_profile = False
        self._pending_summary = False
        self._previous_column_names: list[str] = []
        self._last_find_match: tuple[int, int] | None = None
        self._last_find_query = None

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(200)
        self._save_timer.timeout.connect(self.save_view_state)
        self._summary_timer = QTimer(self)
        self._summary_timer.setSingleShot(True)
        self._summary_timer.setInterval(80)
        self._summary_timer.timeout.connect(self._update_selection_summary)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.find_bar = QWidget()
        find_layout = QHBoxLayout(self.find_bar)
        find_layout.setContentsMargins(0, 0, 0, 0)
        self.find_input = QLineEdit()
        self.find_input.setPlaceholderText("Find a value…")
        self.find_input.setClearButtonEnabled(True)
        self.find_column = QComboBox()
        self.find_column.setMinimumWidth(140)
        self.find_case = QCheckBox("Match case")
        self.find_previous_button = QPushButton("Previous")
        self.find_next_button = QPushButton("Next")
        self.find_scope = QLabel(self._scope_label)
        self.find_scope.setObjectName("secondaryText")
        self.find_close_button = QPushButton("Close")
        for widget in (
            self.find_input,
            self.find_column,
            self.find_case,
            self.find_previous_button,
            self.find_next_button,
            self.find_scope,
            self.find_close_button,
        ):
            find_layout.addWidget(widget)
        layout.addWidget(self.find_bar)
        self.find_bar.hide()
        self.find_status = QLabel()
        self.find_status.setObjectName("secondaryText")
        self.find_status.setWordWrap(True)
        self.find_status.hide()
        layout.addWidget(self.find_status)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.table_view = QTableView()
        self.table_view.setAlternatingRowColors(True)
        self.table_view.setSelectionMode(QTableView.SelectionMode.ExtendedSelection)
        self.table_view.setSelectionBehavior(QTableView.SelectionBehavior.SelectItems)
        self.table_view.setWordWrap(False)
        self.row_header = RowInsertionHeader(self.table_view, overlay_parent=self)
        self.table_view.setVerticalHeader(self.row_header)
        self.row_header.insertion_requested.connect(self._request_page_insertion)
        viewport = self.table_view.viewport()
        assert viewport is not None
        viewport.installEventFilter(self)
        self._row_boundary_line = QWidget(viewport)
        self._row_boundary_line.setObjectName("rowInsertionLine")
        self._row_boundary_line.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents
        )
        self._row_boundary_line.setAutoFillBackground(True)
        self._row_boundary_line.setBackgroundRole(QPalette.ColorRole.Highlight)
        self._row_boundary_line.hide()
        self.row_header.boundary_changed.connect(self._show_insertion_line)
        scrollbar = self.table_view.verticalScrollBar()
        assert scrollbar is not None
        scrollbar.valueChanged.connect(self.row_header.refresh_boundary)
        header = self.table_view.horizontalHeader()
        assert header is not None
        header.setSectionsMovable(True)
        header.setMinimumSectionSize(48)
        header.setDefaultSectionSize(140)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.sectionMoved.connect(self._schedule_save)
        header.sectionResized.connect(self._column_resized)
        header.sectionClicked.connect(self.set_current_column)
        self.splitter.addWidget(self.table_view)
        self.inspector = self._make_inspector()
        self.splitter.addWidget(self.inspector)
        self.inspector.hide()
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)
        layout.addWidget(self.splitter, 1)
        self.row_status = QLabel()
        self.row_status.setObjectName("secondaryText")
        self.row_status.setWordWrap(True)
        self.row_status.hide()
        self.row_cancel_button = QPushButton("Cancel insertion")
        self.row_cancel_button.setToolTip(
            "Discard the prepared rows; allow the active calculation to finish."
        )
        self.row_cancel_button.clicked.connect(self.cancel_row_insertion)
        self.row_cancel_button.hide()
        row_status_layout = QHBoxLayout()
        row_status_layout.setContentsMargins(0, 0, 0, 0)
        row_status_layout.addWidget(self.row_status, 1)
        row_status_layout.addWidget(self.row_cancel_button)
        layout.addLayout(row_status_layout)
        self.selection_summary = QLabel("Select cells to see a summary.")
        self.selection_summary.setObjectName("secondaryText")
        self.selection_summary.setWordWrap(True)
        layout.addWidget(self.selection_summary)

        self.copy_action = self._action(
            "Copy", self.copy_selection, QKeySequence.StandardKey.Copy
        )
        self.copy_headers_action = self._action(
            "Copy with headers", lambda: self.copy_selection(True), "Ctrl+Shift+C"
        )
        self.columns_action = self._action("Columns…", self.show_columns)
        self.format_action = self._action("Column format…", self.show_format)
        self.find_action = self._action(
            "Find…", self.show_find, QKeySequence.StandardKey.Find
        )
        self.go_to_action = self._action("Go to row…", self.show_go_to, "Ctrl+G")
        self.inspector_action = self._action("Inspector", None)
        self.inspector_action.setCheckable(True)
        self.inspector_action.toggled.connect(self._toggle_inspector)
        self.rename_action = self._action("Rename column…", self.show_rename)
        self.add_row_action = self._action("Add row…", self._request_default_insertion)
        self.add_row_action.setToolTip(
            "Insert before the selected row, or at the dataset end when no row is selected."
        )
        self.paste_rows_action = self._action(
            "Paste as new rows", self.paste_rows, "Ctrl+Shift+V"
        )
        self.paste_rows_action.setToolTip(
            "Insert clipboard rows before the selected row, starting at the first visible column. No header row is skipped."
        )
        self.find_input.returnPressed.connect(lambda: self.start_find())
        self.find_input.textChanged.connect(self._invalidate_find)
        self.find_column.currentIndexChanged.connect(self._invalidate_find)
        self.find_case.toggled.connect(self._invalidate_find)
        self.find_next_button.clicked.connect(lambda: self.start_find())
        self.find_previous_button.clicked.connect(lambda: self.start_find(True))
        self.find_close_button.clicked.connect(self.hide_find)
        self.find_escape_action = self._action("Close find", self.hide_find, "Escape")
        self.find_escape_action.setEnabled(False)
        self._update_actions()
        owner_window = self.window()
        if owner_window is not None and owner_window is not self:
            owner_window.installEventFilter(self)

    def _action(self, text: str, slot, shortcut=None) -> QAction:
        action = QAction(text, self)
        if slot is not None:
            action.triggered.connect(lambda checked=False: slot())
        if shortcut is not None:
            action.setShortcut(QKeySequence(shortcut))
            action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.addAction(action)
        return action

    def _make_inspector(self) -> QWidget:
        panel = QWidget()
        panel.setMinimumWidth(260)
        layout = QVBoxLayout(panel)
        title = QLabel("Cell inspector")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)
        self.cell_location = QLabel("Select a cell.")
        self.cell_location.setWordWrap(True)
        layout.addWidget(self.cell_location)
        self.cell_value = QPlainTextEdit()
        self.cell_value.setReadOnly(True)
        self.cell_value.setMaximumHeight(130)
        layout.addWidget(self.cell_value)
        self.schema_tree = QTreeWidget()
        self.schema_tree.setHeaderLabels(["Column", "Type"])
        self.schema_tree.setRootIsDecorated(False)
        self.schema_tree.setMinimumHeight(100)
        self.schema_tree.itemClicked.connect(self._schema_clicked)
        layout.addWidget(self.schema_tree, 1)
        self.profile_button = QPushButton("Profile selected column")
        self.profile_button.clicked.connect(self.profile_current_column)
        layout.addWidget(self.profile_button)
        self.profile_status = QLabel("Profile scope: Dataset")
        self.profile_status.setWordWrap(True)
        self.profile_status.setObjectName("secondaryText")
        layout.addWidget(self.profile_status)
        self.profile_tree = QTreeWidget()
        self.profile_tree.setHeaderLabels(["Metric", "Value"])
        self.profile_tree.setRootIsDecorated(False)
        layout.addWidget(self.profile_tree, 1)
        return panel

    def set_model(
        self, model, identity: str = "", scope_label: str = "Dataset"
    ) -> None:
        if self._model is not None:
            self.save_view_state()
            self._model.modelAboutToBeReset.disconnect(self._before_reset)
            self._model.modelReset.disconnect(self._after_reset)
            self._model.dataChanged.disconnect(self._data_changed)
            selection = self.table_view.selectionModel()
            if selection is not None:
                selection.selectionChanged.disconnect(self._selection_changed)
                selection.currentChanged.disconnect(self._current_changed)
        self._invalidate_all()
        self._model = model
        self._identity = identity
        self._scope_label = scope_label
        self._column_widths = {}
        self._previous_column_names = []
        self._view_state = self._load_view_state()
        self.table_view.setModel(model)
        if model is not None:
            model.modelAboutToBeReset.connect(self._before_reset)
            model.modelReset.connect(self._after_reset)
            model.dataChanged.connect(self._data_changed)
            selection = self.table_view.selectionModel()
            assert selection is not None
            selection.selectionChanged.connect(self._selection_changed)
            selection.currentChanged.connect(self._current_changed)
        self.refresh_view()

    def set_identity(self, identity: str) -> None:
        """Persist the current view under a saved path without resetting selection."""
        self.save_view_state()
        self._identity = identity
        self.save_view_state()

    def _column_names(self) -> list[str]:
        return self._model.get_column_names() if self._model is not None else []

    def _page_frame(self) -> pl.DataFrame:
        return self._model.page_dataframe()

    def _dataset_frame(self) -> pl.DataFrame:
        if hasattr(self._model, "get_dataframe"):
            return self._model.get_dataframe()
        return self._page_frame()

    def _signature(self):
        session = getattr(self._model, "session", None)
        if session is not None:
            return id(self._model), session.id, session.revision, self._generation
        return id(self._model), self._generation

    def _visual_columns(self, include_hidden: bool = False) -> list[int]:
        header = self.table_view.horizontalHeader()
        assert header is not None
        return [
            header.logicalIndex(visual)
            for visual in range(header.count())
            if include_hidden
            or not self.table_view.isColumnHidden(header.logicalIndex(visual))
        ]

    def _before_reset(self) -> None:
        # An opening preview has no schema yet; retain preferences loaded for
        # its identity until the first page arrives.
        if self._column_names():
            self._view_state = self._capture_view_state()
        self._previous_column_names = self._column_names()
        self._invalidate_all()

    def _after_reset(self) -> None:
        names = self._column_names()
        previous = self._previous_column_names
        if len(names) == len(previous):
            changed = [(old, new) for old, new in zip(previous, names) if old != new]
            if len(changed) == 1:
                old, new = changed[0]
                # Carry column presentation through rename and its undo/redo.
                for key in ("widths", "formats"):
                    values = self._view_state.get(key, {})
                    if isinstance(values, dict) and old in values:
                        values[new] = values.pop(old)
                for key in ("order", "hidden"):
                    values = self._view_state.get(key, [])
                    if isinstance(values, list):
                        self._view_state[key] = [
                            new if name == old else name for name in values
                        ]
        self.refresh_view()

    def _data_changed(self, *args) -> None:
        if self._restoring:
            return
        self._invalidate_all()
        self._selection_changed()
        self._update_cell_inspector()

    def refresh_view(self) -> None:
        names = self._column_names()
        self._active_column = min(self._active_column, max(0, len(names) - 1))
        self._restoring = True
        try:
            previous = self.find_column.currentData()
            self.find_column.clear()
            self.find_column.addItem("All columns", None)
            for name in names:
                self.find_column.addItem(name, name)
            if previous in names:
                self.find_column.setCurrentIndex(names.index(previous) + 1)
            self.find_scope.setText(self._scope_label)
            self.profile_status.setText(f"Profile scope: {self._scope_label}")
            self.schema_tree.clear()
            if self._model is not None:
                schema = self._page_frame().schema
                for name in names:
                    self.schema_tree.addTopLevelItem(
                        QTreeWidgetItem([name, str(schema[name])])
                    )
                self._apply_view_state()
        finally:
            self._restoring = False
        self._update_actions()
        self._selection_changed()
        self._update_cell_inspector()

    def _update_actions(self) -> None:
        names = self._column_names()
        selection = self.table_view.selectionModel()
        selected = selection is not None and selection.hasSelection()
        self.copy_action.setEnabled(selected)
        self.copy_headers_action.setEnabled(selected)
        for action in (
            self.columns_action,
            self.format_action,
            self.find_action,
            self.go_to_action,
        ):
            action.setEnabled(bool(names))
        self.rename_action.setEnabled(
            bool(names) and hasattr(self._model, "rename_column")
        )
        self.profile_button.setEnabled(bool(names))
        can_insert = self._can_insert_rows()
        self.add_row_action.setEnabled(can_insert)
        self.paste_rows_action.setEnabled(can_insert)
        self.row_header.set_insertion_enabled(can_insert, self._row_offset())
        row_running = self._row_task is not None and self._row_task.is_running
        self.row_cancel_button.setVisible(row_running and not self._closing)
        self.row_cancel_button.setEnabled(
            row_running and self._row_task is not None and not self._row_task.cancelled
        )

    def _invalidate_find(self, *args) -> None:
        self._find_generation += 1
        self._pending_find = None
        self._last_find_match = None
        self._last_find_query = None
        if self._find_task is not None:
            self._find_task.cancel()
        self.find_status.clear()

    def _invalidate_all(self) -> None:
        self._generation += 1
        self._invalidate_find()
        self._summary_generation += 1
        self._profile_generation += 1
        self._pending_summary = False
        self._pending_profile = False
        self._row_generation += 1
        if self._row_insert_menu is not None:
            self._row_insert_menu.close()
        self.row_header.hide_boundary()
        if self._row_task is not None and self._row_task.is_running:
            self.row_status.setText(
                "Row insertion cancelled; waiting for work to finish."
            )
        self._summary_timer.stop()
        cancel_tasks(self)
        self.profile_tree.clear()
        self.profile_status.setText(f"Profile scope: {self._scope_label}")

    def _can_insert_rows(self) -> bool:
        return (
            not self._closing
            and bool(self._column_names())
            and hasattr(self._model, "insert_rows")
            and hasattr(self._model, "commit_inserted_frame")
            and (self._row_task is None or not self._row_task.is_running)
        )

    def _show_insertion_line(self, y: int | None) -> None:
        viewport = self.table_view.viewport()
        if y is None or viewport is None:
            self._row_boundary_line.hide()
            return
        self._row_boundary_line.setGeometry(
            0, min(max(0, y - 1), max(0, viewport.height() - 2)), viewport.width(), 2
        )
        self._row_boundary_line.show()
        self._row_boundary_line.raise_()

    def _default_insertion_position(self) -> int:
        index = self.table_view.currentIndex()
        if index.isValid():
            return self._row_offset() + index.row()
        return self._dataset_frame().height

    def _request_default_insertion(self) -> None:
        if self._can_insert_rows():
            self.request_row_insertion(self._default_insertion_position())

    def _request_page_insertion(self, boundary: int) -> None:
        self.request_row_insertion(self._row_offset() + boundary)

    def request_row_insertion(self, position: int) -> None:
        """Open row actions at an explicit zero-based boundary in the dataset."""
        if not self._can_insert_rows():
            return
        height = self._dataset_frame().height
        if not 0 <= position <= height:
            return
        if self._row_insert_menu is not None:
            self._row_insert_menu.close()
            self._row_insert_menu.deleteLater()
        menu = QMenu(self)
        self._row_insert_menu = menu
        placement = (
            f"Before row {position + 1:,}"
            if position < height
            else (f"After row {height:,}" if height else "First row")
        )
        menu.addSection(placement)
        blank = menu.addAction("Insert blank row")
        paste = menu.addAction("Paste clipboard as new rows")
        assert blank is not None and paste is not None
        signature = self._signature()
        blank.triggered.connect(
            lambda: (
                self.insert_blank_row(position)
                if signature == self._signature()
                else None
            )
        )
        paste.triggered.connect(
            lambda: (
                self.paste_rows(position) if signature == self._signature() else None
            )
        )
        if self.row_header.boundary is not None:
            point = self.row_header.insertion_menu_position()
        else:
            viewport = self.table_view.viewport()
            assert viewport is not None
            index = self.table_view.currentIndex()
            point = viewport.mapToGlobal(
                self.table_view.visualRect(index).topLeft()
                if index.isValid()
                else viewport.rect().topLeft()
            )
        menu.popup(point)

    def _select_inserted_row(self, position: int) -> None:
        self._model.jump_to_page(position // self._model.chunk_size)
        local_row = position % self._model.chunk_size
        columns = self._visual_columns()
        if not columns:
            return
        column = next(
            (
                column
                for column in columns
                if self._model.flags(self._model.index(local_row, column))
                & Qt.ItemFlag.ItemIsEditable
            ),
            columns[0],
        )
        self._select_match(position, column)
        self.table_view.setFocus()

    def insert_blank_row(self, position: int | None = None) -> bool:
        if not self._can_insert_rows():
            return False
        position = self._default_insertion_position() if position is None else position
        try:
            self._model.insert_rows(position, count=1)
            self._select_inserted_row(position)
        except (ValueError, pl.exceptions.PolarsError) as exc:
            QMessageBox.warning(self, "Insert row", str(exc))
            return False
        self.row_status.setText(f"Inserted one blank row at row {position + 1:,}.")
        self.row_status.show()
        return True

    def paste_rows(self, position: int | None = None) -> bool:
        """Insert typed TSV rows; the first field maps to the first visible column."""
        if not self._can_insert_rows():
            return False
        position = self._default_insertion_position() if position is None else position
        clipboard = QApplication.clipboard()
        assert clipboard is not None
        text = clipboard.text()
        if not text:
            QMessageBox.warning(self, "Paste rows", "The clipboard has no text rows.")
            return False
        if len(text) > MAX_PASTE_BYTES or len(text.encode("utf-8")) > MAX_PASTE_BYTES:
            QMessageBox.warning(
                self, "Paste rows", "Clipboard text exceeds 10 MiB. Paste fewer rows."
            )
            return False
        model = self._model
        frame = self._dataset_frame()
        if not 0 <= position <= frame.height:
            QMessageBox.warning(
                self, "Paste rows", "The insertion row is out of range."
            )
            return False
        names = self._column_names()
        columns = [names[column] for column in self._visual_columns()]
        self._row_generation += 1
        generation, signature = self._row_generation, self._signature()
        self._row_result_applied = False
        self.row_status.setText(f"Preparing clipboard rows at row {position + 1:,}…")
        self.row_status.show()

        def completed(inserted: pl.DataFrame) -> None:
            if (
                self._closing
                or generation != self._row_generation
                or signature != self._signature()
            ):
                return
            count = inserted.height - frame.height
            model.commit_inserted_frame(inserted, position)
            self._select_inserted_row(position)
            self._row_result_applied = True
            self.row_status.setText(
                f"Inserted {count:,} clipboard rows at row {position + 1:,}. Undo restores the previous data."
            )

        def failed(exc: Exception) -> None:
            if (
                not self._closing
                and generation == self._row_generation
                and signature == self._signature()
            ):
                self.row_status.setText("No rows inserted.")
                QMessageBox.warning(self, "Paste rows", str(exc))

        self._row_task = run_in_background(
            self,
            lambda: insert_tsv_rows(frame, position, text, columns),
            completed,
            failed,
        )
        self._row_task.finished.connect(self._row_task_finished)
        self._update_actions()
        return True

    @pyqtSlot()
    def _row_task_finished(self) -> None:
        if (
            not self._closing
            and self._row_task is not None
            and self._row_task.cancelled
            and not self._row_result_applied
        ):
            self.row_status.setText("Row insertion cancelled. No rows inserted.")
        self._update_actions()

    def cancel_row_insertion(self) -> None:
        """Discard the pending paste without cancelling other grid operations."""
        if self._row_task is not None and self._row_task.is_running:
            self._row_generation += 1
            self._row_task.cancel()
            self.row_status.setText(
                "Row insertion cancelled; waiting for work to finish."
            )
            self._update_actions()

    def _selected_cells(self, limit: int) -> list[tuple[int, int]]:
        selection = self.table_view.selectionModel()
        if selection is None:
            return []
        # The runtime selection is iterable; PyQt6 6.9 omits that from its stub.
        ranges = list(cast(Iterable[QItemSelectionRange], selection.selection()))
        if sum(part.width() * part.height() for part in ranges) > limit:
            raise ValueError(f"Select at most {limit:,} cells for this operation.")
        return sorted(
            {
                (row, column)
                for part in ranges
                for column in range(part.left(), part.right() + 1)
                if not self.table_view.isColumnHidden(column)
                for row in range(part.top(), part.bottom() + 1)
            }
        )

    def copy_selection(self, include_headers: bool = False) -> bool:
        if self._model is None:
            return False
        try:
            cells = self._selected_cells(MAX_COPY_CELLS)
            if not cells:
                return False
            rows = sorted({row for row, _ in cells})
            selected_columns = {column for _, column in cells}
            visual_columns = self._visual_columns()
            columns = [
                column for column in visual_columns if column in selected_columns
            ]
            positions = [visual_columns.index(column) for column in columns]
            if (
                len(cells) != len(rows) * len(columns)
                or rows[-1] - rows[0] + 1 != len(rows)
                or positions[-1] - positions[0] + 1 != len(positions)
            ):
                raise ValueError("Select one rectangular range to copy.")
            frame = self._page_frame()
            selected_frame = frame.slice(rows[0], len(rows)).select(
                [frame.columns[column] for column in columns]
            )
            if selected_frame.estimated_size() > MAX_COPY_BYTES:
                raise ValueError(
                    "Selected values exceed the 10 MiB clipboard memory budget. Select a smaller range."
                )
            series = [
                raw_column_text(selected_frame.to_series(column))
                for column in range(selected_frame.width)
            ]
            output = io.StringIO(newline="")
            writer = csv.writer(output, delimiter="\t", lineterminator="\n")
            byte_count = 0
            records = (
                [[self._column_names()[column] for column in columns]]
                if include_headers
                else []
            )
            for record in records:
                writer.writerow(record)
            for row in range(len(rows)):
                values = [column[row] for column in series]
                byte_count += sum(len(value.encode("utf-8")) for value in values)
                if byte_count > MAX_COPY_BYTES:
                    raise ValueError(
                        "Clipboard output exceeds 10 MiB. Select a smaller range."
                    )
                writer.writerow(values)
            text = output.getvalue()
            if len(text.encode("utf-8")) > MAX_COPY_BYTES:
                raise ValueError(
                    "Clipboard output exceeds 10 MiB. Select a smaller range."
                )
            clipboard = QApplication.clipboard()
            assert clipboard is not None
            clipboard.setText(text)
            return True
        except ValueError as exc:
            QMessageBox.warning(self, "Copy cells", str(exc))
            return False

    def _selection_changed(self, *args) -> None:
        self._summary_generation += 1
        if self._summary_task is not None:
            self._summary_task.cancel()
        self._update_actions()
        if not self._closing:
            self._summary_timer.start()

    def _update_selection_summary(self) -> None:
        if self._closing:
            return
        if self._summary_task is not None and self._summary_task.is_running:
            self._pending_summary = True
            return
        self._pending_summary = False
        if self._model is None:
            self.selection_summary.setText("Select cells to see a summary.")
            return
        try:
            cells = self._selected_cells(MAX_AGGREGATE_CELLS)
        except ValueError as exc:
            self.selection_summary.setText(f"Selection summary unavailable. {exc}")
            return
        if not cells:
            self.selection_summary.setText("Select cells to see a summary.")
            return
        frame = self._page_frame()
        generation, signature = self._summary_generation, self._signature()
        self.selection_summary.setText(
            f"Summarizing {len(cells):,} selected cells on this page…"
        )

        def completed(text):
            if (
                generation == self._summary_generation
                and signature == self._signature()
            ):
                self.selection_summary.setText(text)
                self.selection_summary.setToolTip(
                    "Selected visible cells on the current page. Nulls and non-finite numbers are excluded from numeric aggregates."
                )

        self._summary_task = run_in_background(
            self,
            lambda: _selection_statistics(frame, cells),
            completed,
            lambda exc: completed(f"Selection summary unavailable: {exc}"),
        )
        self._summary_task.finished.connect(self._resume_pending_work)

    def set_current_column(self, column: int) -> None:
        if 0 <= column < len(self._column_names()):
            self._active_column = column
            self.profile_tree.clear()
            self._profile_generation += 1
            self._pending_profile = False
            if self._profile_task is not None:
                self._profile_task.cancel()
            self.profile_status.setText(f"Profile scope: {self._scope_label}")

    def _current_changed(self, current: QModelIndex, previous: QModelIndex) -> None:
        if current.isValid():
            self.set_current_column(current.column())
        self._update_cell_inspector()

    def _schema_clicked(self, item, column) -> None:
        names = self._column_names()
        if item.text(0) in names:
            self.set_current_column(names.index(item.text(0)))

    def _toggle_inspector(self, visible: bool) -> None:
        self.inspector.setVisible(visible)
        if visible:
            self.splitter.setSizes([700, 300])
            self._update_cell_inspector()
        self._schedule_save()

    def _update_cell_inspector(self) -> None:
        index = self.table_view.currentIndex()
        if self._model is None or not index.isValid():
            self.cell_location.setText("Select a cell.")
            self.cell_value.clear()
            return
        frame = self._page_frame()
        if index.row() >= frame.height or index.column() >= frame.width:
            return
        offset = self._row_offset()
        series = frame.to_series(index.column())
        value = raw_cell_text(series, index.row(), null_text="NULL")
        state = "null" if series[index.row()] is None else str(series.dtype)
        self.cell_location.setText(
            f"Row {offset + index.row() + 1:,} · {series.name} · {state}"
        )
        if len(value) > MAX_INSPECTOR_CHARACTERS:
            value = (
                value[:MAX_INSPECTOR_CHARACTERS]
                + "\n[Value preview truncated at 100,000 characters]"
            )
        self.cell_value.setPlainText(value)

    def profile_current_column(self) -> None:
        names = self._column_names()
        if self._closing or not names:
            return
        if self._profile_task is not None and self._profile_task.is_running:
            self._profile_task.cancel()
            self._pending_profile = True
            self.profile_status.setText("Waiting for the previous profile to finish…")
            return
        self._pending_profile = False
        column = names[self._active_column]
        frame = self._dataset_frame()
        self._profile_generation += 1
        generation, signature = self._profile_generation, self._signature()
        if self._profile_task is not None:
            self._profile_task.cancel()
        self.profile_status.setText(f"Profiling {column} · {self._scope_label}…")

        def completed(profile):
            if generation != self._profile_generation or signature != self._signature():
                return
            self.profile_tree.clear()
            for key, value in profile.items():
                if key == "top_values":
                    for item in value:
                        self.profile_tree.addTopLevelItem(
                            QTreeWidgetItem(
                                [
                                    f"Value: {item['value']}",
                                    f"{item['count']:,} rows",
                                ]
                            )
                        )
                else:
                    self.profile_tree.addTopLevelItem(
                        QTreeWidgetItem([key.replace("_", " ").title(), str(value)])
                    )
            self.profile_status.setText(f"{column} · {self._scope_label}")

        def failed(exc):
            if (
                generation == self._profile_generation
                and signature == self._signature()
            ):
                self.profile_status.setText(f"Profile unavailable: {exc}")

        self._profile_task = run_in_background(
            self, lambda: column_profile(frame, column), completed, failed
        )
        self._profile_task.finished.connect(self._resume_pending_work)

    def show_find(self) -> None:
        self.find_bar.show()
        self.find_status.show()
        self.find_escape_action.setEnabled(True)
        self.find_input.setFocus()
        self.find_input.selectAll()

    def hide_find(self) -> None:
        self._invalidate_find()
        self.find_bar.hide()
        self.find_status.hide()
        self.find_escape_action.setEnabled(False)
        self.table_view.setFocus()

    def start_find(self, backwards: bool = False) -> None:
        if self._closing or self._model is None or not self.find_input.text():
            return
        if self._find_task is not None and self._find_task.is_running:
            self._find_task.cancel()
            self._pending_find = backwards
            self.find_status.setText("Waiting for the previous search to finish…")
            return
        self._pending_find = None
        text, column, case_sensitive = (
            self.find_input.text(),
            self.find_column.currentData(),
            self.find_case.isChecked(),
        )
        query = (text, column, case_sensitive)
        after = self._last_find_match if query == self._last_find_query else None
        frame = self._dataset_frame()
        columns = [column] if column is not None else None
        self._find_generation += 1
        generation, signature = self._find_generation, self._signature()
        if self._find_task is not None:
            self._find_task.cancel()
        self.find_status.show()
        self.find_status.setText(f"Searching · {self._scope_label}…")

        def completed(match):
            if generation != self._find_generation or signature != self._signature():
                return
            if match is None:
                self.find_status.setText(f"No matches · {self._scope_label}")
                return
            self._select_match(*match)
            # Navigating to another page resets the model and invalidates old requests.
            self._last_find_match, self._last_find_query = match, query
            self.find_status.setText(
                f"Row {match[0] + 1 + (0 if hasattr(self._model, 'session') else self._row_offset()):,} · {frame.columns[match[1]]} · {self._scope_label}"
            )

        def failed(exc):
            if generation == self._find_generation and signature == self._signature():
                self.find_status.setText(f"Search failed: {exc}")

        self._find_task = run_in_background(
            self,
            lambda: find_match(
                frame,
                text,
                columns=columns,
                case_sensitive=case_sensitive,
                after=after,
                backwards=backwards,
            ),
            completed,
            failed,
        )
        self._find_task.finished.connect(self._resume_pending_work)

    @pyqtSlot()
    def _resume_pending_work(self) -> None:
        # Cancellation suppresses results but lets native operations complete.
        # Coalesce rapid input so each operation owns at most one active worker.
        if self._closing:
            return
        if self._pending_find is not None and (
            self._find_task is None or not self._find_task.is_running
        ):
            self.start_find(self._pending_find)
        if self._pending_profile and (
            self._profile_task is None or not self._profile_task.is_running
        ):
            self.profile_current_column()
        if self._pending_summary and (
            self._summary_task is None or not self._summary_task.is_running
        ):
            self._update_selection_summary()

    def _row_offset(self) -> int:
        if hasattr(self._model, "get_current_page"):
            return self._model.get_current_page() * self._model.chunk_size
        return getattr(self._model, "row_offset", 0)

    def _select_match(self, row: int, column: int) -> None:
        if hasattr(self._model, "jump_to_page"):
            self._model.jump_to_page(row // self._model.chunk_size)
            row %= self._model.chunk_size
        self.table_view.setColumnHidden(column, False)
        index = self._model.index(row, column)
        self.table_view.setCurrentIndex(index)
        selection = self.table_view.selectionModel()
        assert selection is not None
        selection.select(index, QItemSelectionModel.SelectionFlag.ClearAndSelect)
        self.table_view.scrollTo(index)

    def go_to_row(self, row_number: int) -> bool:
        if self._model is None:
            return False
        rows = self._dataset_frame().height
        if not 1 <= row_number <= rows:
            return False
        self._select_match(row_number - 1, self._active_column)
        self.table_view.setFocus()
        return True

    def show_go_to(self) -> None:
        if self._model is None:
            return
        rows = self._dataset_frame().height
        scope = "dataset" if hasattr(self._model, "session") else "current preview page"
        value, accepted = QInputDialog.getText(
            self, "Go to row", f"Row in {scope} (1–{rows:,}):"
        )
        if accepted:
            try:
                if not self.go_to_row(int(value)):
                    raise ValueError()
            except ValueError:
                QMessageBox.warning(
                    self, "Go to row", f"Enter a row between 1 and {rows:,}."
                )

    def show_columns(self) -> None:
        if self._model is not None:
            ColumnsDialog(self).exec()

    def auto_fit_columns(self, columns: list[int] | None = None) -> None:
        if self._model is None:
            return
        columns = self._visual_columns() if columns is None else columns
        if len(columns) > 1000:
            QMessageBox.warning(
                self, "Fit columns", "Show at most 1,000 columns before fitting widths."
            )
            return
        rows = min(
            self._model.rowCount(), max(1, min(100, 10_000 // max(1, len(columns))))
        )
        metrics = self.table_view.fontMetrics()
        names = self._column_names()
        for column in columns:
            width = metrics.horizontalAdvance(names[column][:200]) + 30
            for row in range(rows):
                value = str(self._model.data(self._model.index(row, column)) or "")
                width = max(
                    width, metrics.horizontalAdvance(value[:200].split("\n")[0]) + 24
                )
            self.table_view.setColumnWidth(column, min(420, max(72, width)))
        self._schedule_save()

    def show_rename(self) -> None:
        names = self._column_names()
        if not names or not hasattr(self._model, "rename_column"):
            return
        old = names[self._active_column]
        new, accepted = QInputDialog.getText(
            self, "Rename column", "Column name:", text=old
        )
        if accepted:
            try:
                self.rename_column(old, new)
            except (ValueError, pl.exceptions.PolarsError) as exc:
                QMessageBox.warning(self, "Rename column", str(exc))

    def rename_column(self, old: str, new: str) -> None:
        if not hasattr(self._model, "rename_column"):
            raise ValueError("This preview is read-only.")
        self._model.rename_column(old, new)
        self.save_view_state()

    def set_column_format(
        self, name: str, mode: str = "auto", precision: int = 2, thousands: bool = False
    ) -> None:
        if self._model is None:
            return
        self._model.set_column_format(
            name, mode=mode, precision=precision, thousands=thousands
        )
        self.save_view_state()

    def show_format(self) -> None:
        names = self._column_names()
        if not names:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Column display format")
        layout = QFormLayout(dialog)
        column = QComboBox()
        column.addItems(names)
        column.setCurrentIndex(self._active_column)
        mode = QComboBox()
        for option in ("auto", "number", "percent", "scientific", "date", "datetime"):
            mode.addItem(option.title(), option)
        precision = QSpinBox()
        precision.setRange(0, 15)
        grouping = QCheckBox("Thousands separator")
        layout.addRow("Column", column)
        layout.addRow("Display", mode)
        layout.addRow("Decimal places", precision)
        layout.addRow(grouping)
        note = QLabel(
            "Display only. Source values and copied precision stay unchanged."
        )
        note.setWordWrap(True)
        layout.addRow(note)

        def load_format():
            current = self._model.column_format(column.currentText())
            mode.setCurrentIndex(max(0, mode.findData(current.get("mode", "auto"))))
            precision.setValue(current.get("precision", 2))
            grouping.setChecked(current.get("thousands", False))

        column.currentIndexChanged.connect(load_format)
        load_format()
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.set_column_format(
                column.currentText(),
                mode.currentData(),
                precision.value(),
                grouping.isChecked(),
            )

    def _settings_key(self) -> str:
        return "grids/" + hashlib.sha256(self._identity.encode("utf-8")).hexdigest()

    def _load_view_state(self) -> dict:
        if not self._identity:
            return {}
        try:
            state = json.loads(str(self._settings.value(self._settings_key(), "{}")))
            return state if isinstance(state, dict) else {}
        except (ValueError, TypeError):
            return {}

    def _capture_view_state(self) -> dict[str, Any]:
        if self._model is None:
            return {}
        names = self._column_names()
        return {
            "order": [names[column] for column in self._visual_columns(True)],
            "hidden": [
                name
                for column, name in enumerate(names)
                if self.table_view.isColumnHidden(column)
            ],
            "widths": {
                name: self.table_view.columnWidth(column)
                or self._column_widths.get(name, 140)
                for column, name in enumerate(names)
            },
            "formats": {name: self._model.column_format(name) for name in names},
            "inspector": self.inspector_action.isChecked(),
        }

    def _apply_view_state(self) -> None:
        names = self._column_names()
        state = self._view_state
        header = self.table_view.horizontalHeader()
        assert header is not None
        order = state.get("order", [])
        if isinstance(order, list):
            known = list(
                dict.fromkeys(
                    name for name in order if isinstance(name, str) and name in names
                )
            )
            for visual, name in enumerate(known):
                header.moveSection(header.visualIndex(names.index(name)), visual)
        hidden = state.get("hidden", [])
        widths = state.get("widths", {})
        formats = state.get("formats", {})
        for logical, name in enumerate(names):
            self.table_view.setColumnHidden(
                logical, isinstance(hidden, list) and name in hidden
            )
            if isinstance(widths, dict) and type(widths.get(name)) is int:
                self.table_view.setColumnWidth(
                    logical, min(2000, max(48, widths[name]))
                )
            if isinstance(formats, dict) and isinstance(formats.get(name), dict):
                try:
                    self._model.set_column_format(name, **formats[name])
                except (ValueError, TypeError):
                    pass
        if names and not self._visual_columns():
            self.table_view.setColumnHidden(0, False)
        self.inspector_action.setChecked(state.get("inspector") is True)

    def _schedule_save(self, *args) -> None:
        if not self._restoring and not self._closing:
            self._save_timer.start()

    def _column_resized(self, logical: int, old: int, new: int) -> None:
        names = self._column_names()
        if 0 <= logical < len(names):
            if new > 0:
                self._column_widths[names[logical]] = new
            elif old > 0:
                self._column_widths[names[logical]] = old
        self._schedule_save()
        if not self._restoring and (old == 0 or new == 0):
            self._selection_changed()

    def save_view_state(self) -> None:
        self._save_timer.stop()
        if self._model is None or self._restoring or not self._column_names():
            return
        self._view_state = self._capture_view_state()
        if self._identity:
            self._settings.setValue(self._settings_key(), json.dumps(self._view_state))

    def eventFilter(self, watched, event) -> bool:
        if (
            watched is self.table_view.viewport()
            and event.type() == QEvent.Type.Resize
            and hasattr(self, "row_header")
        ):
            self.row_header.refresh_boundary()
        if event.type() == QEvent.Type.Close:
            self.save_view_state()
        return super().eventFilter(watched, event)

    def cancel_pending_work(self) -> None:
        """Cancel queued summaries as well as already submitted grid tasks."""
        self._invalidate_all()
        self._update_actions()
        self.selection_summary.setText("Selection summary cancelled.")

    def prepare_close(self) -> None:
        """Called by the owning window after its unsaved-changes confirmation."""
        self.save_view_state()
        self._closing = True
        self._save_timer.stop()
        self.cancel_pending_work()

    def closeEvent(self, event) -> None:
        self.prepare_close()
        super().closeEvent(event)
