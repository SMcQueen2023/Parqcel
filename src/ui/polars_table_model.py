from PyQt6.QtCore import QAbstractTableModel, Qt
import polars as pl

class PolarsTableModel(QAbstractTableModel):
    def __init__(self, data: pl.DataFrame, chunk_size=10000):
        super().__init__()
        self._data = data
        self.chunk_size = chunk_size
        self._current_page = 0
        self._max_pages = (data.height + chunk_size - 1) // chunk_size
        self._current_data = self._get_page_data(self._current_page)
        self._column_types = self._get_column_types()
        self._undo_stack = []
        self._redo_stack = []

    def save_state(self):
        self._undo_stack.append(self._data.clone())  # Save state before any changes
        self._redo_stack.clear()  # Clear redo stack when a new change happens

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

    # Define the flags for the items in the model
    # This allows for editing, selection, and enabling of items in the table view
    def flags(self, index):
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEditable

    # Define the setData method to handle editing of the table view
    def setData(self, index, value, role):
        if role == Qt.ItemDataRole.EditRole:
            self.save_state()  # Save the current state before making changes
            
            row = index.row() + self._current_page * self.chunk_size
            col = index.column()
            col_name = self._data.columns[col]

            dtype = self._data.schema[col_name]

            # Safely cast value to original dtype
            try:
                if dtype in [pl.Int64, pl.Int32]:
                    value = int(value)
                elif dtype in [pl.Float64, pl.Float32]:
                    value = float(value)
                else:
                    value = str(value)
            except ValueError:
                return False  # Invalid value entered, ignore change

            # Modify the specific value
            col_values = self._data[col_name].to_list()
            col_values[row] = value

            # Rebuild the column
            new_col = pl.Series(name=col_name, values=col_values)

            # Replace the column in the DataFrame
            self._data = self._data.with_columns(new_col)

            # Update the visible chunk
            self._current_data = self._get_page_data(self._current_page)

            # Refresh the view
            self.dataChanged.emit(index, index, [Qt.ItemDataRole.DisplayRole])
            self.layoutChanged.emit()

            return True
        return False

    def _get_page_data(self, page_number):
        start_row = page_number * self.chunk_size
        return self._data.slice(start_row, self.chunk_size)

    def load_next_page(self):
        if self._current_page < self._max_pages - 1:
            self._current_page += 1
            self._current_data = self._get_page_data(self._current_page)
            self.layoutChanged.emit()

    def load_previous_page(self):
        if self._current_page > 0:
            self._current_page -= 1
            self._current_data = self._get_page_data(self._current_page)
            self.layoutChanged.emit()

    def jump_to_page(self, page_number):
        if 0 <= page_number < self._max_pages:
            self._current_page = page_number
            self._current_data = self._get_page_data(self._current_page)
            self.layoutChanged.emit()

    def get_current_page(self):
        return self._current_page

    def get_max_pages(self):
        return self._max_pages

    def _get_column_types(self):
        column_types = {}
        for col in self._data.columns:
            dtype = self._data.schema[col]
            column_types[col] = str(dtype)
        return column_types

    def sort_column(self, column_name, ascending=True):
        self._data = self._data.sort(column_name, descending=not ascending)
        self._current_data = self._get_page_data(self._current_page)
        self.layoutChanged.emit()

    def drop_column(self, column_name):
        self._data = self._data.drop(column_name)
        self._current_data = self._get_page_data(self._current_page)
        self.layoutChanged.emit()

    def add_column(self, column_name: str, default_value=None):
        if column_name in self._data.columns:
            return  # Avoid duplicates

        self.save_state()  # Support undo

        # Create new column with default_value repeated for each row
        new_series = pl.Series(name=column_name, values=[default_value] * self._data.height)
        self._data = self._data.with_columns(new_series)

        # Update cached info
        self._current_data = self._get_page_data(self._current_page)
        self._column_types[column_name] = str(new_series.dtype)

        self.layoutChanged.emit()

    def get_column_statistics(self, column_name):
        dtype = self._data.schema[column_name]
        col = self._data[column_name]

        stats = ""
        if dtype in [pl.Utf8, pl.Categorical]:
            stats += f"Unique Values: {col.n_unique()}\n"
            stats += f"Blanks: {(col == '').sum()}\n"
            stats += f"Nulls: {col.is_null().sum()}\n"
            value_counts = col.value_counts()
            for row in value_counts.iter_rows():
                value, count = row
                percentage = (count / self._data.height) * 100
                stats += f"'{value}': {percentage:.2f}%\n"
        elif dtype in [pl.Int64, pl.Int32, pl.Float64, pl.Float32]:
            stats += f"Min: {col.min()}\n"
            stats += f"Max: {col.max()}\n"
            stats += f"Mean: {col.mean():.2f}\n"
            stats += f"Median: {col.median()}\n"
            stats += f"Std Dev: {col.std():.2f}\n"
            stats += f"Variance: {col.var():.2f}\n"
        else:
            stats += "Statistics not supported for this column type."
        return stats

    def undo(self):
        if self._undo_stack:
            self._redo_stack.append(self._data.clone())  # Save current state for redo
            self._data = self._undo_stack.pop()  # Revert to previous state
            self._current_data = self._get_page_data(self._current_page)
            self.layoutChanged.emit()

    def redo(self):
        if self._redo_stack:
            self._undo_stack.append(self._data.clone())  # Save current state for undo
            self._data = self._redo_stack.pop()  # Restore next state
            self._current_data = self._get_page_data(self._current_page)
            self.layoutChanged.emit()

    def update_data(self, new_df: pl.DataFrame):
        self.save_state()
        self._data = new_df
        self._max_pages = (new_df.height + self.chunk_size - 1) // self.chunk_size
        self._current_page = 0
        self._current_data = self._get_page_data(self._current_page)
        self._column_types = self._get_column_types()
        self.layoutChanged.emit()