from PyQt6.QtWidgets import (
    QMainWindow, QFileDialog, QTableView, QVBoxLayout, QWidget, QMenuBar,
    QPushButton, QHBoxLayout, QLineEdit, QLabel, QMenu, QMessageBox, QInputDialog,
    QDialog, QTextEdit
)
from PyQt6.QtGui import QAction
from PyQt6.QtCore import QAbstractTableModel, Qt, QPoint
import polars as pl
import os
from logic.filters import apply_filter  # Import logic to apply filters to dataframe
from models.polars_table_model import PolarsTableModel  # Import the model class
from app.edit_dialogs import add_column  # Import add_column function
from logic.stats import (
    get_numeric_stats,
    get_string_stats,
    generate_statistics,
    update_statistics,
    get_column_types,
    get_page_data,
    calculate_max_pages,
    get_column_statistics,
    get_column_type_counts_string
)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Parqcel")
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

        # Footer column statistics layout (Row count, Column count, Column type count)
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

        # Edit menu
        edit_menu = menu_bar.addMenu("Edit")

        add_column_action = QAction("Add Column", self)
        add_column_action.triggered.connect(self.handle_add_column)
        edit_menu.addAction(add_column_action)

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
        if not self.is_model_loaded():
            return

        file_name, _ = QFileDialog.getSaveFileName(self, "Save Parquet File", "", "Parquet Files (*.parquet)")
        if file_name:
            try:
                self.model._data.write_parquet(file_name)
            except Exception as e:
                print(f"Error saving file: {e}")
    
    def is_model_loaded(self):
        if not hasattr(self, 'model') or self.model is None:
            QMessageBox.warning(self, "No Data", "Please load a file first.")
            return False
        return True

    def load_next_page(self):
        if not self.is_model_loaded():
            return
        self.model.load_next_page()
        self.update_page_info()

    def load_previous_page(self):
        if not self.is_model_loaded():
            return
        self.model.load_previous_page()
        self.update_page_info()

    def jump_to_page(self):
        if not self.is_model_loaded():
            return
        page_number = self.page_input.text()
        if page_number.isdigit():
            page_number = int(page_number) -1  # Convert to zero-based index
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
        dtype = self.model._data.schema[column_name]

        menu = QMenu(self)

        # Add sorting and drop options
        sort_asc = menu.addAction("Sort Ascending")
        sort_desc = menu.addAction("Sort Descending")
        drop_col = menu.addAction("Drop Column")
        stats_col = menu.addAction("Generate Statistics")

        # Initialize filter menu and actions
        filter_menu = None
        less_than = None
        less_than_equal = None
        equal_to = None
        greater_than = None
        greater_than_equal = None
        contains = None
        starts_with = None
        ends_with = None
        equals = None

        # Add filtering options based on column type
        if dtype in [pl.Int64, pl.Int32, pl.Float64, pl.Float32, pl.Date]:
            filter_menu = QMenu("Filter", self)
            less_than = filter_menu.addAction("Less than")
            less_than_equal = filter_menu.addAction("Less than or equal to")
            equal_to = filter_menu.addAction("Equal to")
            greater_than = filter_menu.addAction("Greater than")
            greater_than_equal = filter_menu.addAction("Greater than or equal to")
        elif dtype in [pl.Utf8, pl.Categorical]:
            filter_menu = QMenu("Filter", self)
            contains = filter_menu.addAction("Contains")
            starts_with = filter_menu.addAction("Starts with")
            ends_with = filter_menu.addAction("Ends with")
            equals = filter_menu.addAction("Equals")

        if filter_menu:
            menu.addMenu(filter_menu)

        # Execute the menu and handle the selected action
        action = menu.exec(self.table_view.mapToGlobal(pos))

        if action == sort_asc:
            self.model.sort_column(column_name, ascending=True)
        elif action == sort_desc:
            self.model.sort_column(column_name, ascending=False)
        elif action == drop_col:
            self.model.drop_column(column_name)
        elif action == stats_col:
            stats = get_column_statistics(self.model._data, column_name)
            QMessageBox.information(self, f"Statistics for {column_name}", stats)
        elif action == less_than:
            self.handle_filter(column_name, "<")
        elif action == less_than_equal:
            self.handle_filter(column_name, "<=")
        elif action == equal_to:
            self.handle_filter(column_name, "==")
        elif action == greater_than:
            self.handle_filter(column_name, ">")
        elif action == greater_than_equal:
            self.handle_filter(column_name, ">=")
        elif action == contains:
            self.handle_filter(column_name, "contains")
        elif action == starts_with:
            self.handle_filter(column_name, "starts_with")
        elif action == ends_with:
            self.handle_filter(column_name, "ends_with")
        elif action == equals:
            self.handle_filter(column_name, "==")

    def handle_filter(self, column_name, filter_type):
        if not self.is_model_loaded():
            return

        apply_filter(self, column_name, filter_type)
        self.update_page_info()

    def generate_statistics(self):
        if not self.is_model_loaded():
            return
        
        # Call the function from stats.py
        stats_text = generate_statistics(self.model)

        if stats_text:
            # Show the statistics in a new window
            self.show_statistics_window(stats_text)

    def show_statistics_window(self, text):
        dialog = QDialog(self)
        dialog.setWindowTitle("Dataset Statistics")
        dialog.setMinimumSize(600, 400)

        layout = QVBoxLayout(dialog)

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setPlainText(text)
        layout.addWidget(text_edit)

        close_button = QPushButton("Close")
        close_button.clicked.connect(dialog.accept)
        layout.addWidget(close_button)

        dialog.exec()

    def update_statistics(self):
        if not self.is_model_loaded():
            return None

        df = self.model._data
        row_count = df.height
        total_columns = df.width
        column_type_counts = get_column_type_counts_string(df)  # Get the string summary of column type counts

        # Update the footer labels
        self.row_count_label.setText(f"Rows: {row_count}")
        self.total_column_count_label.setText(f"Total Columns: {total_columns}")
        self.column_type_count_label.setText(f"Column Type Count: {column_type_counts}")

        return {
            "row_count": row_count,
            "total_columns": total_columns,
            "column_types": column_type_counts
        }

    def handle_add_column(self):
        if not hasattr(self, 'model') or self.model is None:
            QMessageBox.warning(self, "No Data", "No file is loaded.")
            return

        try:
            df = self.model._data
            updated_df = add_column(df, self)  # `self` is passed in case the logic needs UI interaction
            self.model.update_data(updated_df)
            self.update_statistics()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to add column: {e}")


