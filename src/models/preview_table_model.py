"""Read-only page model sharing the editor's view-only value formatting."""

import polars as pl
from PyQt6.QtCore import QAbstractTableModel, QModelIndex, Qt

from models.table_presentation import TablePresentation


class PreviewTableModel(QAbstractTableModel, TablePresentation):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._init_presentation()
        self.frame = pl.DataFrame()
        self.row_offset = 0

    def _presentation_frame(self) -> pl.DataFrame:
        return self.frame

    def replace_page(self, frame: pl.DataFrame, row_offset: int) -> None:
        if row_offset < 0:
            raise ValueError("Row offset must be non-negative")
        self.beginResetModel()
        self.frame = frame.clone()
        self.row_offset = row_offset
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else self.frame.height

    def columnCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else self.frame.width

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        return TablePresentation.data(self, index, role)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole or section < 0:
            return None
        if orientation == Qt.Orientation.Horizontal:
            if section >= self.frame.width:
                return None
            return f"{self.frame.columns[section]}\n({self.frame.dtypes[section]})"
        return (
            str(self.row_offset + section + 1) if section < self.frame.height else None
        )

    def flags(self, index):
        if not self._valid_cell(index):
            return Qt.ItemFlag.NoItemFlags
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
