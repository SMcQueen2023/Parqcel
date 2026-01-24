from __future__ import annotations

from typing import List, Dict

from PyQt6.QtCore import QAbstractTableModel, Qt, QModelIndex
import polars as pl
from logic.stats import (
    get_column_types,
    get_page_data,
    calculate_max_pages,
    get_column_statistics,
)
from datetime import datetime, date
import logging

logger = logging.getLogger(__name__)


class PolarsTableModel(QAbstractTableModel):
    def __init__(self, data: pl.DataFrame, chunk_size: int = 10000) -> None:
        super().__init__()
        self._data: pl.DataFrame = data
        self.chunk_size: int = chunk_size
        self._current_page: int = 0
        self._max_pages: int = calculate_max_pages(data.height, chunk_size)
        self._current_data: pl.DataFrame = get_page_data(
            data, self._current_page, chunk_size
        )
        self._column_types: Dict[str, str] = get_column_types(data)
        self._undo_stack: List[pl.DataFrame] = []
        self._redo_stack: List[pl.DataFrame] = []

    def save_state(self) -> None:
        self._undo_stack.append(self._data.clone())
        self._redo_stack.clear()

    def rowCount(self, parent=None) -> int:
        return self._current_data.height

    def columnCount(self, parent=None) -> int:
        return self._current_data.width

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            try:
                value = self._current_data[index.row(), index.column()]
                return str(value) if value is not None else ""
            except IndexError:
                return ""
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole:
            if orientation == Qt.Orientation.Horizontal:
                col_name = self._data.columns[section]
                col_type = self._column_types[col_name]
                return f"{col_name}\n({col_type})"
            else:
                return str(section)
        return None

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        return (
            Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemIsEditable
        )

    def setData(
        self, index: QModelIndex, value: object, role: int = Qt.ItemDataRole.EditRole
    ) -> bool:
        if role == Qt.ItemDataRole.EditRole:
            self.save_state()

            row = index.row() + self._current_page * self.chunk_size
            col = index.column()
            col_name = self._data.columns[col]
            dtype = self._data.schema[col_name]

            try:
                if dtype in [pl.Int64, pl.Int32]:
                    value = int(str(value))
                elif dtype in [pl.Float64, pl.Float32]:
                    value = float(str(value))
                elif dtype == pl.Date:
                    # Try parsing string to date
                    if isinstance(value, str):
                        value = datetime.strptime(value, "%Y-%m-%d").date()
                    elif not isinstance(value, date):
                        return False
                elif dtype == pl.Datetime:
                    # Try parsing string to datetime
                    if isinstance(value, str):
                        value = datetime.fromisoformat(value)
                    elif not isinstance(value, datetime):
                        return False
                else:
                    value = str(value)
            except Exception:
                return False

            col_values = self._data[col_name].to_list()
            col_values[row] = value

            # Fix: Create series with dtype fallback
            try:
                new_col = pl.Series(name=col_name, values=col_values, dtype=dtype)
            except Exception:
                # Last-resort fallback if dtype fails, use strict=False
                new_col = pl.Series(name=col_name, values=col_values, strict=False)

            self._data = self._data.with_columns(new_col)
            self._current_data = get_page_data(
                self._data, self._current_page, self.chunk_size
            )

            self.dataChanged.emit(index, index, [Qt.ItemDataRole.DisplayRole])
            # Notify views that layout and header data (types) may have changed
            self.layoutChanged.emit()
            try:
                self.headerDataChanged.emit(Qt.Orientation.Horizontal, 0, self.columnCount() - 1)
            except Exception:
                logger.exception(
                    "Failed to emit headerDataChanged signal for columns 0 to %d",
                    self.columnCount() - 1,
                )
            return True
        return False

    def load_next_page(self) -> None:
        if self._current_page < self._max_pages - 1:
            self._current_page += 1
            self._current_data = get_page_data(
                self._data, self._current_page, self.chunk_size
            )
            self.layoutChanged.emit()

    def load_previous_page(self) -> None:
        if self._current_page > 0:
            self._current_page -= 1
            self._current_data = get_page_data(
                self._data, self._current_page, self.chunk_size
            )
            self.layoutChanged.emit()

    def jump_to_page(self, page_number: int) -> None:
        if 0 <= page_number < self._max_pages:
            self._current_page = page_number
            self._current_data = get_page_data(
                self._data, self._current_page, self.chunk_size
            )
            self.layoutChanged.emit()

    def get_current_page(self) -> int:
        return self._current_page

    def get_max_pages(self) -> int:
        return self._max_pages

    def sort_column(self, column_name: str, ascending: bool = True) -> None:
        self._data = self._data.sort(column_name, descending=not ascending)
        self._current_data = get_page_data(
            self._data, self._current_page, self.chunk_size
        )
        self.layoutChanged.emit()

    def drop_column(self, column_name: str) -> None:
        self._data = self._data.drop(column_name)
        self._current_data = get_page_data(
            self._data, self._current_page, self.chunk_size
        )
        self.layoutChanged.emit()

    def add_column(self, column_name: str, default_value: object | None = None) -> None:
        if column_name in self._data.columns:
            return

        self.save_state()

        new_series = pl.Series(
            name=column_name, values=[default_value] * self._data.height
        )
        self._data = self._data.with_columns(new_series)

        self._current_data = get_page_data(
            self._data, self._current_page, self.chunk_size
        )
        self._column_types[column_name] = str(new_series.dtype)
        self.layoutChanged.emit()
        try:
            self.headerDataChanged.emit(Qt.Orientation.Horizontal, 0, self.columnCount() - 1)
        except Exception:
            logger.exception(
                "Failed to emit headerDataChanged signal for columns 0 to %d",
                self.columnCount() - 1,
            )

    def get_column_statistics(self, column_name: str) -> str:
        return get_column_statistics(self._data, column_name)

    def undo(self) -> None:
        if self._undo_stack:
            self._redo_stack.append(self._data.clone())
            self._data = self._undo_stack.pop()
            self._current_data = get_page_data(
                self._data, self._current_page, self.chunk_size
            )
            self._column_types = get_column_types(self._data)
            self.layoutChanged.emit()
            try:
                self.headerDataChanged.emit(Qt.Orientation.Horizontal, 0, self.columnCount() - 1)
            except Exception:
                logger.exception(
                    "Failed to emit headerDataChanged signal for columns 0 to %d during undo",
                    self.columnCount() - 1,
                )

    def redo(self) -> None:
        if self._redo_stack:
            self._undo_stack.append(self._data.clone())
            self._data = self._redo_stack.pop()
            self._current_data = get_page_data(
                self._data, self._current_page, self.chunk_size
            )
            self._column_types = get_column_types(self._data)
            self.layoutChanged.emit()
            try:
                self.headerDataChanged.emit(Qt.Orientation.Horizontal, 0, self.columnCount() - 1)
            except Exception:
                logger.exception(
                    "Failed to emit headerDataChanged signal for columns 0 to %d during redo",
                    self.columnCount() - 1,
                )

    def update_data(self, new_df: pl.DataFrame) -> None:
        self.save_state()
        # Full reset so views refresh headers and cached metadata
        try:
            self.beginResetModel()
        except Exception:
            logger.exception(
                "beginResetModel failed; proceeding with manual reset/fallback signals"
            )
        self._data = new_df
        self._max_pages = calculate_max_pages(new_df.height, self.chunk_size)
        self._current_page = 0
        self._current_data = get_page_data(
            self._data, self._current_page, self.chunk_size
        )
        self._column_types = get_column_types(self._data)
        try:
            self.endResetModel()
        except Exception:
            # Fallback to layout/header signals if reset isn't available
            logger.exception("endResetModel failed; falling back to layout/header signals")
            self.layoutChanged.emit()
            try:
                self.headerDataChanged.emit(Qt.Orientation.Horizontal, 0, self.columnCount() - 1)
            except Exception:
                logger.exception(
                    "Failed to emit headerDataChanged signal during endResetModel fallback for columns 0 to %d",
                    self.columnCount() - 1,
                )

    def sort_multiple_columns(self, columns: list[str], directions: list[bool]) -> None:
        try:
            logger.info(
                "Sorting data by columns: %s with directions: %s", columns, directions
            )
            sorted_df = self._data.sort(
                by=columns, descending=[not d for d in directions]
            )
            self.update_data(
                sorted_df
            )  # <-- use update_data to handle all updates properly
            logger.debug("Sorting completed and model updated.")
        except Exception as e:
            logger.exception("Error sorting multiple columns: %s", e)

    def get_column_names(self) -> list[str]:
        return list(self._data.columns)

    # Safe accessors
    def get_dataframe(self) -> pl.DataFrame:
        """Return the underlying DataFrame (read-only intention)."""
        return self._data

    def replace_dataframe(self, new_df: pl.DataFrame) -> None:
        """Replace the underlying DataFrame with a new one (keeps undo snapshot)."""
        self.update_data(new_df)
