from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QAbstractTableModel, Qt, QModelIndex, pyqtSignal
import polars as pl

from parqcel.core.statistics import (
    get_column_types,
    get_page_data,
    calculate_max_pages,
    get_column_statistics,
)
from parqcel.core.session import DatasetSession
from parqcel.core.values import is_editable_dtype


class PolarsTableModel(QAbstractTableModel):
    """Qt presentation and pagination for a GUI-independent dataset session."""

    dataset_changed = pyqtSignal()
    pagination_changed = pyqtSignal()

    def __init__(
        self,
        data: pl.DataFrame,
        chunk_size: int = 10000,
        *,
        source_path: str | Path | None = None,
        session: DatasetSession | None = None,
    ) -> None:
        super().__init__()
        if chunk_size <= 0:
            raise ValueError("Page size must be positive")
        self.session = (
            session if session is not None else DatasetSession(data, source_path)
        )
        self.chunk_size = chunk_size
        self._current_page = 0
        self._refresh_cache()

    @property
    def _data(self) -> pl.DataFrame:
        """Compatibility snapshot for older read-only callers."""
        return self.session.get_dataframe()

    @property
    def _undo_stack(self) -> tuple[pl.DataFrame, ...]:
        return self.session.undo_history

    @property
    def _redo_stack(self) -> tuple[pl.DataFrame, ...]:
        return self.session.redo_history

    def _refresh_cache(self, reset_page: bool = False) -> None:
        frame = self.get_dataframe()
        self._max_pages = calculate_max_pages(frame.height, self.chunk_size)
        self._current_page = (
            0 if reset_page else min(self._current_page, max(0, self._max_pages - 1))
        )
        self._current_data = get_page_data(frame, self._current_page, self.chunk_size)
        self._column_types = get_column_types(frame)

    def _notify_commit(self, reset_page: bool = False) -> None:
        self.beginResetModel()
        self._refresh_cache(reset_page)
        self.endResetModel()
        self.dataset_changed.emit()
        self.pagination_changed.emit()

    def _replace_data(self, new_df: pl.DataFrame, reset_page: bool = False) -> None:
        self.session.commit(new_df)
        self._notify_commit(reset_page)

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else self._current_data.height

    def columnCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else self._current_data.width

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            try:
                value = self._current_data[index.row(), index.column()]
                return str(value) if value is not None else ""
            except IndexError:
                return None
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole or section < 0:
            return None
        if orientation == Qt.Orientation.Horizontal:
            if section >= self.columnCount():
                return None
            col_name = self._current_data.columns[section]
            return f"{col_name}\n({self._column_types[col_name]})"
        return str(section + self._current_page * self.chunk_size)

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if is_editable_dtype(self._current_data.dtypes[index.column()]):
            flags |= Qt.ItemFlag.ItemIsEditable
        return flags

    def setData(
        self, index: QModelIndex, value: object, role: int = Qt.ItemDataRole.EditRole
    ) -> bool:
        if (
            role != Qt.ItemDataRole.EditRole
            or not index.isValid()
            or index.row() >= self.rowCount()
            or index.column() >= self.columnCount()
        ):
            return False
        try:
            self.session.set_cell(
                index.row() + self._current_page * self.chunk_size,
                self._current_data.columns[index.column()],
                value,
            )
        except (
            ValueError,
            TypeError,
            IndexError,
            OverflowError,
            pl.exceptions.PolarsError,
        ):
            return False
        self._notify_commit()
        return True

    def load_next_page(self) -> None:
        self.jump_to_page(self._current_page + 1)

    def load_previous_page(self) -> None:
        self.jump_to_page(self._current_page - 1)

    def jump_to_page(self, page_number: int) -> None:
        if 0 <= page_number < self._max_pages and page_number != self._current_page:
            self.beginResetModel()
            self._current_page = page_number
            self._refresh_cache()
            self.endResetModel()
            self.pagination_changed.emit()

    def get_current_page(self) -> int:
        return self._current_page

    def get_max_pages(self) -> int:
        return self._max_pages

    def sort_column(self, column_name: str, ascending: bool = True) -> None:
        self.sort_multiple_columns([column_name], [ascending])

    def sort_multiple_columns(self, columns: list[str], directions: list[bool]) -> None:
        self._replace_data(
            self.get_dataframe().sort(
                by=columns, descending=[not d for d in directions]
            )
        )

    def drop_column(self, column_name: str) -> None:
        frame = self.get_dataframe()
        if column_name in frame.columns:
            self._replace_data(frame.drop(column_name))

    def add_column(self, column_name: str, default_value: object | None = None) -> None:
        frame = self.get_dataframe()
        if column_name not in frame.columns:
            self._replace_data(
                frame.with_columns(pl.lit(default_value).alias(column_name))
            )

    def get_column_statistics(self, column_name: str) -> str:
        return get_column_statistics(self.get_dataframe(), column_name)

    def undo(self) -> None:
        if self.session.undo():
            self._notify_commit()

    def redo(self) -> None:
        if self.session.redo():
            self._notify_commit()

    def update_data(self, new_df: pl.DataFrame) -> None:
        self._replace_data(new_df, reset_page=True)

    def get_column_names(self) -> list[str]:
        return list(self._current_data.columns)

    def get_dataframe(self) -> pl.DataFrame:
        return self.session.get_dataframe()

    def replace_dataframe(self, new_df: pl.DataFrame) -> None:
        self.update_data(new_df)

    def mark_saved(self, revision: int, path: str | Path) -> bool:
        return self.session.mark_saved(revision, path)
