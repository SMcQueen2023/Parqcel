from PyQt6.QtWidgets import (
    QMainWindow, QFileDialog, QTableView, QVBoxLayout, QWidget, QMenuBar,
    QPushButton, QHBoxLayout, QLineEdit, QLabel, QMenu, QMessageBox
)
from PyQt6.QtGui import QAction
from PyQt6.QtCore import QAbstractTableModel, Qt, QPoint
import polars as pl
import os

# This is a PyQt6 application that uses Polars for data manipulation and display.
# It provides a table view for displaying data, with pagination and editing capabilities.
class PolarsTableModel(QAbstractTableModel):
    def __init__(self, data: pl.DataFrame, chunk_size=500):
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
    # This method is called when the user edits a cell in the table view
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


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Parcel")
        self.setMinimumSize(800, 600)

        self._createMenuBar()

        self.table_view = QTableView()
        self.table_view.horizontalHeader().setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table_view.horizontalHeader().customContextMenuRequested.connect(self.show_context_menu)

        layout = QVBoxLayout()

        # Button Layout for pagination and actions
        self.pagination_layout = QHBoxLayout()
        self.prev_button = QPushButton("Previous Page")
        self.next_button = QPushButton("Next Page")
        self.page_input = QLineEdit()
        self.page_input.setPlaceholderText("Jump to page")
        self.page_input.setFixedWidth(100)
        self.jump_button = QPushButton("Jump")
        self.page_info_label = QLabel()
        self.undo_button = QPushButton("Undo")
        self.redo_button = QPushButton("Redo")

        # Statistics Layout (Row count, Column count, Column type count)
        self.stats_layout = QVBoxLayout()
        self.row_count_label = QLabel("Rows: 0")
        self.total_column_count_label = QLabel("Total Columns: 0")
        self.column_type_count_label = QLabel("Column Type Count: {}")
        self.stats_layout.addWidget(self.row_count_label)
        self.stats_layout.addWidget(self.total_column_count_label)
        self.stats_layout.addWidget(self.column_type_count_label)

        # Set button styles
        self.pagination_layout.addWidget(self.prev_button)
        self.pagination_layout.addWidget(self.next_button)
        self.pagination_layout.addWidget(self.page_input)
        self.pagination_layout.addWidget(self.jump_button)
        self.pagination_layout.addWidget(self.page_info_label)
        self.pagination_layout.addWidget(self.undo_button)
        self.pagination_layout.addWidget(self.redo_button)

        # Add buttons to the layout
        layout.addLayout(self.pagination_layout)
        layout.addWidget(self.table_view)
        layout.addLayout(self.stats_layout)

        # Set the main layout
        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        # Connect Click events to methods
        self.prev_button.clicked.connect(self.load_previous_page)
        self.next_button.clicked.connect(self.load_next_page)
        self.jump_button.clicked.connect(self.jump_to_page)

    def _createMenuBar(self):
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("File")

        # Open action
        open_action = QAction("Open File", self)
        open_action.triggered.connect(self.open_file)
        file_menu.addAction(open_action)

        # Save As action
        save_action = QAction("Save As...", self)
        save_action.triggered.connect(self.save_parquet)
        file_menu.addAction(save_action)

        # Generate statistics action
        stats_action = QAction("Generate Statistics", self)
        stats_action.triggered.connect(self.generate_statistics)
        file_menu.addAction(stats_action)

    def open_file(self):
        file_dialog = QFileDialog(self)
        file_path, _ = file_dialog.getOpenFileName(
            self,
            "Open Parquet File",
            "",
            "Data Files (*.parquet *.csv *.xlsx)"
        )

        if file_path:
            ext = os.path.splitext(file_path)[1].lower()
            try:
                if ext == ".parquet":
                    df = pl.read_parquet(file_path)
                elif ext == ".csv":
                    df = pl.read_csv(file_path, infer_schema_length=0)
                    df = df.cast(pl.Utf8)  # Ensure all columns are treated as strings
                elif ext == ".xlsx":
                    df = pl.read_excel(file_path)
                else:
                    QMessageBox.warning(self, "Unsupported Format", f"Unsupported file extension: {ext}")
                    return

                self.model = PolarsTableModel(df)
                self.table_view.setModel(self.model)
                self.table_view.resizeColumnsToContents()
                self.table_view.resizeRowsToContents()
                self.update_page_info()
                self.update_statistics()

                # Connect undo/redo buttons after model is set
                self.undo_button.clicked.connect(self.model.undo)
                self.redo_button.clicked.connect(self.model.redo)

            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to load file: {e}")

    def save_parquet(self):
        if not hasattr(self, 'model') or self.model is None:
            return

        file_name, _ = QFileDialog.getSaveFileName(self, "Save Parquet File", "", "Parquet Files (*.parquet)")
        if file_name:
            try:
                self.model._data.write_parquet(file_name)
            except Exception as e:
                print(f"Error saving file: {e}")

    def load_next_page(self):
        self.model.load_next_page()
        self.update_page_info()

    def load_previous_page(self):
        self.model.load_previous_page()
        self.update_page_info()

    def jump_to_page(self):
        page_number = self.page_input.text()
        if page_number.isdigit():
            page_number = int(page_number)
            self.model.jump_to_page(page_number)
            self.update_page_info()

    def update_page_info(self):
        current_page = self.model.get_current_page() + 1
        max_pages = self.model.get_max_pages()
        self.page_info_label.setText(f"Page {current_page} of {max_pages}")
        self.page_input.clear()

    def show_context_menu(self, pos: QPoint):
        index = self.table_view.indexAt(pos)
        if not index.isValid():
            return

        column = index.column()
        column_name = self.model._data.columns[column]

        menu = QMenu(self)

        sort_asc = menu.addAction("Sort Ascending")
        sort_desc = menu.addAction("Sort Descending")
        drop_col = menu.addAction("Drop Column")
        stats_col = menu.addAction("Generate Statistics")

        action = menu.exec(self.table_view.mapToGlobal(pos))

        if action == sort_asc:
            self.model.sort_column(column_name, ascending=True)
        elif action == sort_desc:
            self.model.sort_column(column_name, ascending=False)
        elif action == drop_col:
            self.model.drop_column(column_name)
        elif action == stats_col:
            stats = self.model.get_column_statistics(column_name)
            QMessageBox.information(self, f"Statistics for {column_name}", stats)

    def generate_statistics(self):
        if not hasattr(self, 'model') or self.model is None:
            QMessageBox.warning(self, "No Data", "No file is loaded.")
            return
        
        df = self.model._data

        stats = []

        for col in df.columns:
            col_stats = [f"Column: {col} ({df.schema[col]})"]
            dtype = df.schema[col]

            series = df[col]

            if dtype in [pl.Int64, pl.Int32, pl.Float64, pl.Float32]:
                col_stats.append(f"Min: {series.min()}")
                col_stats.append(f"Max: {series.max()}")
                col_stats.append(f"Mean: {series.mean():.2f}")
                col_stats.append(f"Median: {series.median()}")
                col_stats.append(f"Std Dev: {series.std():.2f}")
                col_stats.append(f"Variance: {series.var():.2f}")
            elif dtype in [pl.Utf8, pl.Categorical]:
                col_stats.append(f"Unique Values: {series.n_unique()}")
                blanks = (series == "").sum()
                col_stats.append(f"Blanks: {blanks}")
                nulls = series.is_null().sum()
                col_stats.append(f"Nulls: {nulls}")
            else:
                col_stats.append("Statistics not supported for this type.")

            stats.append("\n".join(col_stats))
        
        full_text = "\n\n".join(stats)

        # Show in a pop-up window with easy copy option
        self.show_statistics_window(full_text)

    def show_statistics_window(self, text):
        stats_window = QMessageBox(self)
        stats_window.setWindowTitle("Dataset Statistics")
        stats_window.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        stats_window.setMinimumSize(600, 400)
        stats_window.setText(text)
        stats_window.exec()

    def update_statistics(self):
        if hasattr(self, 'model') and self.model is not None:
            df = self.model._data
            row_count = df.height
            total_columns = df.width
            column_types = self.model._get_column_types()

            self.row_count_label.setText(f"Rows: {row_count}")
            self.total_column_count_label.setText(f"Total Columns: {total_columns}")

            # Count columns by type
            type_count = {}
            for col_name, col_type in column_types.items():
                if col_type not in type_count:
                    type_count[col_type] = 0
                type_count[col_type] += 1

            type_count_text = "\n".join([f"{t}: {count}" for t, count in type_count.items()])
            self.column_type_count_label.setText(f"Column Type Count:\n{type_count_text}")