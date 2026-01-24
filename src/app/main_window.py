from PyQt6.QtWidgets import (
    QMainWindow,
    QFileDialog,
    QTableView,
    QVBoxLayout,
    QWidget,
    QPushButton,
    QHBoxLayout,
    QLineEdit,
    QLabel,
    QMenu,
    QMessageBox,
    QInputDialog,
    QDialog,
    QTextEdit,
    QSizePolicy,
)
from PyQt6.QtGui import QAction, QFont
from PyQt6.QtCore import Qt, QPoint
import polars as pl
import os
import time
from logic.filters import apply_filter  # Import logic to apply filters to dataframe
from logic.parsers import convert_series_to_datetime
from models.polars_table_model import PolarsTableModel  # Import the model class
from app.widgets.edit_menu_gui import AddColumnDialog, MultiSortDialog
from app.edit_menu_controller import add_column
from logic.stats import (
    generate_statistics,
    get_column_statistics,
    get_column_type_counts_string,
)
import logging

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Parqcel")
        self.setMinimumSize(800, 600)

        self._createMenuBar()

        self.table_view = QTableView()
        self.table_view.horizontalHeader().setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.table_view.horizontalHeader().customContextMenuRequested.connect(
            self.show_context_menu
        )

        layout = QVBoxLayout()

        # Button Layout for pagination and actions
        self.pagination_layout = QHBoxLayout()
        self.first_button = QPushButton("⏮")
        self.prev_button = QPushButton("⏪")
        self.next_button = QPushButton("⏩")
        self.last_button = QPushButton("⏭")
        self.page_input = QLineEdit()
        self.page_input.setPlaceholderText("Jump to page")
        self.page_input.setFixedWidth(100)
        self.jump_button = QPushButton("Jump")
        self.page_info_label = QLabel()
        self.undo_button = QPushButton("Undo")
        self.redo_button = QPushButton("Redo")

        self.first_button.setToolTip("First Page")
        self.prev_button.setToolTip("Previous Page")
        self.next_button.setToolTip("Next Page")
        self.last_button.setToolTip("Last Page")

        # Footer column statistics layout (Row count, Column count, Column type count)
        self.stats_layout = QVBoxLayout()
        self.row_count_label = QLabel("Total Rows: 0")
        self.total_column_count_label = QLabel("Total Columns: 0")
        self.column_type_count_label = QLabel("Column Type Count: {}")
        self.stats_layout.addWidget(self.row_count_label)
        self.stats_layout.addWidget(self.total_column_count_label)
        self.stats_layout.addWidget(self.column_type_count_label)

        # Improve pagination button appearance
        pagination_font = QFont()
        pagination_font.setPointSize(14)
        pagination_font.setBold(True)
        pagination_buttons = [
            self.first_button,
            self.prev_button,
            self.next_button,
            self.last_button,
        ]
        for button in pagination_buttons:
            button.setFont(pagination_font)
            button.setFixedSize(36, 32)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            # Modern plain white icon on transparent background
            button.setStyleSheet(
                "QPushButton {"
                "  color: #FFFFFF;"
                "  background-color: transparent;"
                "  border: none;"
                "  border-radius: 6px;"
                "  padding: 2px;"
                "}"
                "QPushButton:hover {"
                "  background-color: rgba(255,255,255,0.03);"
                "}"
                "QPushButton:pressed {"
                "  background-color: rgba(255,255,255,0.06);"
                "}"
            )

        # Set button styles
        self.pagination_layout.addWidget(self.first_button)
        self.pagination_layout.addWidget(self.prev_button)
        self.pagination_layout.addWidget(self.next_button)
        self.pagination_layout.addWidget(self.last_button)
        self.pagination_layout.addWidget(self.page_input)

        # Cap Jump/Undo/Redo sizes to avoid stretching on large windows
        self.jump_button.setFixedWidth(80)
        self.jump_button.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
        )
        self.undo_button.setFixedWidth(80)
        self.undo_button.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
        )
        self.redo_button.setFixedWidth(80)
        self.redo_button.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
        )

        # Page info label should expand to absorb available space so buttons don't stretch
        self.page_info_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )

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
        self.first_button.clicked.connect(self.load_first_page)
        self.prev_button.clicked.connect(self.load_previous_page)
        self.next_button.clicked.connect(self.load_next_page)
        self.last_button.clicked.connect(self.load_last_page)
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

        # Add column action
        add_column_action = QAction("Add Column", self)
        add_column_action.triggered.connect(self.handle_add_column)
        edit_menu.addAction(add_column_action)

        # Multi-Sort action
        sort_columns_action = QAction("Sort Columns...", self)
        sort_columns_action.triggered.connect(self.handle_multi_sort)
        edit_menu.addAction(sort_columns_action)

    def open_file(self):
        file_dialog = QFileDialog(self)
        file_path, _ = file_dialog.getOpenFileName(
            self, "Open Parquet File", "", "Data Files (*.parquet *.csv *.xlsx)"
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
                    QMessageBox.warning(
                        self, "Unsupported Format", f"Unsupported file extension: {ext}"
                    )
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

        file_name, _ = QFileDialog.getSaveFileName(
            self, "Save Parquet File", "", "Parquet Files (*.parquet)"
        )
        if file_name:
            try:
                self.model._data.write_parquet(file_name)
            except Exception as e:
                QMessageBox.critical(self, "Save Error", f"Error saving file: {e}")

    def is_model_loaded(self):
        if not hasattr(self, "model") or self.model is None:
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

    def load_first_page(self):
        if not self.is_model_loaded():
            return
        self.model.jump_to_page(0)
        self.update_page_info()

    def load_last_page(self):
        if not self.is_model_loaded():
            return
        self.model.jump_to_page(self.model.get_max_pages() - 1)
        self.update_page_info()

    def jump_to_page(self):
        if not self.is_model_loaded():
            return
        page_number = self.page_input.text()
        if page_number.isdigit():
            page_number = int(page_number) - 1  # Convert to zero-based index
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
        convert_type = menu.addAction("Convert Type...")

        # Initialize filter menu and actions
        filter_menu = None
        less_than = None
        less_than_equal = None
        equal_to = None
        greater_than = None
        greater_than_equal = None
        between = None
        contains = None
        starts_with = None
        ends_with = None
        equals = None

        # Add filtering options based on column type
        if dtype in [pl.Int64, pl.Int32, pl.Float64, pl.Float32]:
            filter_menu = QMenu("Filter", self)
            less_than = filter_menu.addAction("Less than")
            less_than_equal = filter_menu.addAction("Less than or equal to")
            equal_to = filter_menu.addAction("Equal to")
            greater_than = filter_menu.addAction("Greater than")
            greater_than_equal = filter_menu.addAction("Greater than or equal to")
        elif dtype in [pl.Date, pl.Datetime]:
            filter_menu = QMenu("Filter", self)
            less_than = filter_menu.addAction("Less than")
            less_than_equal = filter_menu.addAction("Less than or equal to")
            equal_to = filter_menu.addAction("Equal to")
            greater_than = filter_menu.addAction("Greater than")
            greater_than_equal = filter_menu.addAction("Greater than or equal to")
            between = filter_menu.addAction("Between...")
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
        if action is None:
            return
        if action == sort_asc:
            self.model.sort_column(column_name, ascending=True)
        elif action == sort_desc:
            self.model.sort_column(column_name, ascending=False)
        elif action == drop_col:
            self.model.drop_column(column_name)
            self.update_statistics()
        elif action == stats_col:
            stats = get_column_statistics(self.model._data, column_name)
            QMessageBox.information(self, f"Statistics for {column_name}", stats)
        elif action == convert_type:
            self.handle_convert_type(column_name)
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
        elif action == between:
            self.handle_filter(column_name, "between")
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

    def handle_convert_type(self, column_name):
        if not self.is_model_loaded():
            return

        type_options = ["String", "Integer", "Float", "Boolean", "Date", "Datetime"]
        new_type, ok = QInputDialog.getItem(
            self,
            "Convert Column Type",
            f"Convert '{column_name}' to:",
            type_options,
            0,
            False,
        )
        if not ok:
            return

        type_map = {
            "String": pl.Utf8,
            "Integer": pl.Int64,
            "Float": pl.Float64,
            "Boolean": pl.Boolean,
            "Date": pl.Date,
            "Datetime": pl.Datetime,
        }

        try:
            target_type = type_map[new_type]
            column_expr = pl.col(column_name)
            # If converting from string to date/datetime, use robust helper
            if (
                new_type in ["Date", "Datetime"]
                and self.model._data.schema[column_name] == pl.Utf8
            ):
                start = time.perf_counter()
                # This column was generated by the app and should parse cleanly;
                # prefer the fast vectorized path and disable Python fallback.
                converted_series = convert_series_to_datetime(
                    self.model._data[column_name], allow_fallback=False
                )
                # If user selected Date, cast down to Date
                if new_type == "Date":
                    try:
                        converted_series = converted_series.cast(pl.Date)
                    except Exception:
                        # best-effort: leave as-is
                        pass
                converted_df = self.model._data.with_columns(converted_series.alias(column_name))
                elapsed = time.perf_counter() - start
                logger.info(
                    "Conversion of column '%s' to %s took %.2fs",
                    column_name,
                    new_type,
                    elapsed,
                )
            else:
                converted_df = self.model._data.with_columns(
                    column_expr.cast(target_type).alias(column_name)
                )
            self.model.update_data(converted_df)
            # Re-assign the model and refresh the view to re-read header data and types
            try:
                self.table_view.setModel(self.model)
                # Force view refresh in case headers or displayed values are cached
                self.table_view.reset()
                header = self.table_view.horizontalHeader()
                if header is not None:
                    viewport = header.viewport()
                    if viewport is not None:
                        viewport.update()
                table_viewport = self.table_view.viewport()
                if table_viewport is not None:
                    table_viewport.update()
                # Adjust column sizes to reflect potential value width changes
                self.table_view.resizeColumnsToContents()
            except Exception:
                logger.exception(
                    "Failed to refresh table view after converting column '%s' to %s",
                    column_name,
                    new_type,
                )
            self.update_statistics()
        except Exception as e:
            QMessageBox.warning(
                self,
                "Conversion Error",
                f"Could not convert '{column_name}' to {new_type}: {e}",
            )

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
        column_type_counts = get_column_type_counts_string(
            df
        )  # Get the string summary of column type counts

        # Update the footer labels
        self.row_count_label.setText(f"Total Rows: {row_count}")
        self.total_column_count_label.setText(f"Total Columns: {total_columns}")
        self.column_type_count_label.setText(f"Column Type Count: {column_type_counts}")

        return {
            "row_count": row_count,
            "total_columns": total_columns,
            "column_types": column_type_counts,
        }

    def handle_add_column(self):
        if not self.is_model_loaded():
            return

        dialog = AddColumnDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            column_name, dtype, default_value = dialog.get_data()
            try:
                if not column_name:
                    QMessageBox.warning(
                        self, "Invalid Column Name", "Column name cannot be empty."
                    )
                    return
                if column_name in self.model._data.columns:
                    QMessageBox.warning(
                        self,
                        "Duplicate Column",
                        f"A column named '{column_name}' already exists.",
                    )
                    return
                new_df = add_column(
                    self.model._data, column_name, dtype, default_value
                )  # Pass DataFrame
                self.model.update_data(
                    new_df
                )  # Update the model with the new DataFrame
                self.update_statistics()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to add column: {e}")

    def handle_multi_sort(self):
        if not self.is_model_loaded():
            print("Model is not loaded, cannot sort.")
            return

        dialog = MultiSortDialog(self.model.get_column_names(), parent=self)
        result = dialog.exec()
        print("MultiSortDialog exec result:", result)

        if result == QDialog.DialogCode.Accepted:
            logger.debug("MultiSortDialog accepted")
            criteria = (
                dialog.get_sorting_criteria()
            )  # List of (column_name, ascending_bool) tuples
            logger.debug("Sorting criteria received: %s", criteria)

            if criteria:
                columns, directions = zip(*criteria)  # unzip into two lists
                logger.info(
                    "Sorting columns: %s with directions: %s", columns, directions
                )
                self.model.sort_multiple_columns(list(columns), list(directions))
            else:
                logger.debug("No sort criteria provided.")
        else:
            logger.debug("MultiSortDialog canceled or closed")
