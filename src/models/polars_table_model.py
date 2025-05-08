from PyQt6.QtCore import QAbstractTableModel, Qt
import polars as pl
from logic.stats import (
    get_numeric_stats,
    get_string_stats,
    generate_statistics,
    update_statistics,
    get_column_types,
    get_page_data,
    calculate_max_pages,
    get_column_statistics,
)

class PolarsTableModel(QAbstractTableModel):
    def __init__(self, data: pl.DataFrame, chunk_size=10000):
        super().__init__()
        self._data = data
        self.chunk_size = chunk_size
        self._current_page = 0
        self._max_pages = calculate_max_pages(data.height, chunk_size)
        self._current_data = get_page_data(data, self._current_page, chunk_size)
        self._column_types = get_column_types(data)
        self._undo_stack = []
        self._redo_stack = []

    def save_state(self):
        self._undo_stack.append(self._data.clone())
        self._redo_stack.clear()

    def rowCount(self, parent=None):
        return self._current_data.height

    def columnCount(self, parent=None):
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

    def setData(self, index, value, role):
        if role == Qt.ItemDataRole.EditRole:
            self.save_state()

            row = index.row() + self._current_page * self.chunk_size
            col = index.column()
            col_name = self._data.columns[col]
            dtype = self._data.schema[col_name]

            try:
                if dtype in [pl.Int64, pl.Int32]:
                    value = int(value)
                elif dtype in [pl.Float64, pl.Float32]:
                    value = float(value)
                else:
                    value = str(value)
            except ValueError:
                return False

            col_values = self._data[col_name].to_list()
            col_values[row] = value
            new_col = pl.Series(name=col_name, values=col_values)
            self._data = self._data.with_columns(new_col)

            self._current_data = get_page_data(self._data, self._current_page, self.chunk_size)

            self.dataChanged.emit(index, index, [Qt.ItemDataRole.DisplayRole])
            self.layoutChanged.emit()
            return True
        return False

    def load_next_page(self):
        if self._current_page < self._max_pages - 1:
            self._current_page += 1
            self._current_data = get_page_data(self._data, self._current_page, self.chunk_size)
            self.layoutChanged.emit()

    def load_previous_page(self):
        if self._current_page > 0:
            self._current_page -= 1
            self._current_data = get_page_data(self._data, self._current_page, self.chunk_size)
            self.layoutChanged.emit()

    def jump_to_page(self, page_number):
        if 0 <= page_number < self._max_pages:
            self._current_page = page_number
            self._current_data = get_page_data(self._data, self._current_page, self.chunk_size)
            self.layoutChanged.emit()

    def get_current_page(self):
        return self._current_page

    def get_max_pages(self):
        return self._max_pages

    def sort_column(self, column_name, ascending=True):
        self._data = self._data.sort(column_name, descending=not ascending)
        self._current_data = get_page_data(self._data, self._current_page, self.chunk_size)
        self.layoutChanged.emit()

    def drop_column(self, column_name):
        self._data = self._data.drop(column_name)
        self._current_data = get_page_data(self._data, self._current_page, self.chunk_size)
        self.layoutChanged.emit()

    def add_column(self, column_name: str, default_value=None):
        if column_name in self._data.columns:
            return

        self.save_state()

        new_series = pl.Series(name=column_name, values=[default_value] * self._data.height)
        self._data = self._data.with_columns(new_series)

        self._current_data = get_page_data(self._data, self._current_page, self.chunk_size)
        self._column_types[column_name] = str(new_series.dtype)

        self.layoutChanged.emit()

    def get_column_statistics(self, column_name):
        return get_column_statistics(self._data, column_name)

    def undo(self):
        if self._undo_stack:
            self._redo_stack.append(self._data.clone())
            self._data = self._undo_stack.pop()
            self._current_data = get_page_data(self._data, self._current_page, self.chunk_size)
            self.layoutChanged.emit()

    def redo(self):
        if self._redo_stack:
            self._undo_stack.append(self._data.clone())
            self._data = self._redo_stack.pop()
            self._current_data = get_page_data(self._data, self._current_page, self.chunk_size)
            self.layoutChanged.emit()

    def update_data(self, new_df: pl.DataFrame):
        self.save_state()
        self._data = new_df
        self._max_pages = calculate_max_pages(new_df.height, self.chunk_size)
        self._current_page = 0
        self._current_data = get_page_data(self._data, self._current_page, self.chunk_size)
        self._column_types = get_column_types(self._data)
        self.layoutChanged.emit()