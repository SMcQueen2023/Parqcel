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
    QDockWidget,
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
from app.widgets.featurize_gui import FeaturizeDialog
from ds.featurize import generate_feature_matrix, add_features_to_df, detect_columns
from app.widgets.pca_gui import PCADialog
from ds.dimensionality import compute_pca, compute_umap
import webbrowser
import tempfile
import numpy as np
import ast
from app.widgets.ai_assistant import AIAssistantWidget
from ai.assistant import assistant_from_config
from app.widgets.ai_settings import AISettingsDialog
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

        # Analysis menu
        analysis_menu = menu_bar.addMenu("Analysis")
        featurize_action = QAction("Featurize Columns...", self)
        featurize_action.triggered.connect(self.handle_featurize)
        analysis_menu.addAction(featurize_action)
        dim_action = QAction("Dimensionality Reduction...", self)
        dim_action.triggered.connect(self.handle_dimensionality)
        analysis_menu.addAction(dim_action)
        ai_action = QAction("AI Assistant...", self)
        ai_action.triggered.connect(self.handle_ai_assistant)
        analysis_menu.addAction(ai_action)

        # Settings menu
        settings_menu = menu_bar.addMenu("Settings")
        ai_settings_action = QAction("AI Settings...", self)
        ai_settings_action.triggered.connect(self.handle_ai_settings)
        settings_menu.addAction(ai_settings_action)

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

    def handle_featurize(self):
        if not self.is_model_loaded():
            return

        df = self.model.get_dataframe()
        numeric, categorical, text = detect_columns(df)

        dialog = FeaturizeDialog(self.model.get_column_names(), numeric, categorical, text, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            selected = dialog.get_selected_columns()
            # Split selected columns by detected type
            sel_numeric = [c for c in selected if c in numeric]
            sel_categorical = [c for c in selected if c in categorical]
            sel_text = [c for c in selected if c in text]
            opts = dialog.get_options()

            try:
                X, feature_names = generate_feature_matrix(
                    df,
                    numeric_cols=sel_numeric,
                    categorical_cols=sel_categorical,
                    text_cols=sel_text,
                    scale_numeric=opts.get("scale_numeric"),
                    one_hot=opts.get("one_hot", True),
                    tfidf_max_features=opts.get("tfidf_max_features", 200),
                )
                new_df = add_features_to_df(df, X, feature_names)
                self.model.update_data(new_df)
                self.update_statistics()
            except Exception as e:
                QMessageBox.critical(self, "Featurize Error", f"Failed to featurize: {e}")

    def handle_dimensionality(self):
        if not self.is_model_loaded():
            return

        df = self.model.get_dataframe()
        col_names = self.model.get_column_names()

        dialog = PCADialog(col_names, parent=self)
        # allow coloring by any column
        dialog.set_color_choices(col_names)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        selected = dialog.get_selected_columns()
        if not selected:
            QMessageBox.warning(self, "No features", "Please select at least one feature column.")
            return

        opts = dialog.get_options()
        method = opts.get("method")
        n_components = opts.get("n_components", 2)
        color_by = opts.get("color_by")
        sample = opts.get("sample", 10000)

        try:
            # build feature matrix
            try:
                X = df.select(selected).to_numpy()
            except Exception:
                X = df.select(selected).to_pandas().values

            # downsample for visualization if requested
            if sample and sample > 0 and X.shape[0] > sample:
                rng = np.random.default_rng(0)
                idx = rng.choice(X.shape[0], size=sample, replace=False)
                X_vis = X[idx]
                color_vals = None
                if color_by:
                    try:
                        color_series = df[color_by].to_list()
                        color_vals = [color_series[i] for i in idx]
                    except Exception:
                        color_vals = None
            else:
                X_vis = X
                color_vals = None
                if color_by:
                    try:
                        color_vals = df[color_by].to_list()
                    except Exception:
                        color_vals = None

            # compute embedding
            if method.startswith("PCA"):
                emb, var_ratio = compute_pca(X_vis, n_components=n_components)
            else:
                emb = compute_umap(X_vis, n_components=n_components)
                var_ratio = None

            # plot using plotly if available, fallback to saving CSV
            try:
                import plotly.graph_objects as go

                # Prepare customdata (index, color value, and up to two feature columns)
                custom_cols = [list(range(len(emb)))]  # index
                hover_names = ["index"]
                if color_vals is not None:
                    custom_cols.append(color_vals)
                    hover_names.append("color")

                extra_hover_cols = []
                for c in selected:
                    if len(extra_hover_cols) >= 2:
                        break
                    if c == color_by:
                        continue
                    try:
                        vals = df[c].to_list()
                        custom_cols.append(vals)
                        hover_names.append(c)
                        extra_hover_cols.append(c)
                    except Exception:
                        continue

                try:
                    customdata = np.column_stack([np.array(col) for col in custom_cols])
                except Exception:
                    customdata = None

                if customdata is not None:
                    hover_lines = [f"{name}: %{{customdata[{i}]}}" for i, name in enumerate(hover_names)]
                    hovertemplate = "<br>".join(hover_lines) + "<extra></extra>"
                else:
                    hovertemplate = None

                if n_components == 2:
                    trace = go.Scatter(
                        x=emb[:, 0],
                        y=emb[:, 1],
                        mode="markers",
                        marker=dict(color=color_vals),
                        customdata=customdata,
                        hovertemplate=hovertemplate,
                    )
                else:
                    trace = go.Scatter3d(
                        x=emb[:, 0],
                        y=emb[:, 1],
                        z=emb[:, 2],
                        mode="markers",
                        marker=dict(color=color_vals, size=3),
                        customdata=customdata,
                        hovertemplate=hovertemplate,
                    )

                fig = go.Figure(data=[trace])

                tmp = tempfile.NamedTemporaryFile(suffix=".html", delete=False)
                fig.write_html(tmp.name)
                webbrowser.open(tmp.name)
            except Exception as e:
                QMessageBox.information(
                    self,
                    "Dimensionality Result",
                    f"Embedding computed (shape {emb.shape}). Could not render interactive plot: {e}",
                )

        except Exception as e:
            QMessageBox.critical(self, "Dimensionality Error", f"Failed to compute embedding: {e}")

    def _safe_execute_transformation(self, code: str):
        """Validate and safely execute a transformation code string.

        Rules:
        - Only the names `df` and `pl` are permitted as free names in the code.
        - No import statements are allowed.
        - Attribute access and calls are allowed only when they are on `df` or `pl`.

        The code may be a single expression (preferred) or a small sequence of statements;
        if the last node is an expression it will be captured as the result.

        Returns a Polars DataFrame on success, or raises an exception.
        """
        import polars as pl

        tree = ast.parse(code, mode="exec")

        allowed_names = {"df", "pl", "True", "False", "None"}

        class Validator(ast.NodeVisitor):
            def visit_Import(self, node):
                raise ValueError("Import statements are not allowed in assistant code")

            def visit_ImportFrom(self, node):
                raise ValueError("Import statements are not allowed in assistant code")

            def visit_Name(self, node):
                if node.id not in allowed_names:
                    raise ValueError(f"Use of name '{node.id}' is not permitted")

            def visit_Call(self, node):
                # Ensure that function being called is an attribute access on allowed names
                func = node.func
                if isinstance(func, ast.Attribute):
                    value = func.value
                    if isinstance(value, ast.Name):
                        if value.id not in ("df", "pl"):
                            raise ValueError("Calls are only allowed on 'df' or 'pl' attributes")
                elif isinstance(func, ast.Name):
                    # direct name calls (e.g., f()) are not allowed
                    raise ValueError("Direct function calls are not permitted; call methods on 'df' or 'pl' only")
                self.generic_visit(node)

            def visit_Attribute(self, node):
                # allow attribute chains but ensure base is df or pl
                cur = node
                while isinstance(cur, ast.Attribute):
                    cur = cur.value
                if isinstance(cur, ast.Name):
                    if cur.id not in ("df", "pl"):
                        raise ValueError("Attribute access only permitted on 'df' or 'pl'")
                self.generic_visit(node)

        Validator().visit(tree)

        # If last node is an Expr, replace it with assignment to capture result
        if tree.body and isinstance(tree.body[-1], ast.Expr):
            result_name = "__parqcel_result__"
            expr_node = tree.body[-1]
            assign = ast.Assign(targets=[ast.Name(id=result_name, ctx=ast.Store())], value=expr_node.value)
            tree.body[-1] = assign

        # Fix any missing lineno/col_offset information before compiling
        tree = ast.fix_missing_locations(tree)
        compiled = compile(tree, filename="<assistant>", mode="exec")

        # Execute in restricted environment
        globs = {"pl": pl}
        locs = {"df": self.model.get_dataframe()}
        exec(compiled, globs, locs)

        if "__parqcel_result__" in locs:
            res = locs["__parqcel_result__"]
            if isinstance(res, pl.DataFrame):
                return res
            else:
                raise ValueError("Result is not a Polars DataFrame")

        # If result not provided, disallow applying ambiguous changes
        raise ValueError("No result DataFrame returned by the executed code")

    def handle_ai_assistant(self):
        # Create or show an AI assistant dock widget
        try:
            if hasattr(self, "ai_dock") and self.ai_dock is not None:
                self.ai_dock.show()
                return

            assistant = assistant_from_config()
            widget = AIAssistantWidget(assistant=assistant, parent=self)
            dock = QDockWidget("AI Assistant", self)
            dock.setWidget(widget)
            dock.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea | Qt.DockWidgetArea.LeftDockWidgetArea)
            self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
            self.ai_dock = dock

            # Connect apply_code signal to a safe confirmation flow
            def _confirm_and_show(code: str):
                # Show the code and offer to execute it safely on the current dataset
                dlg = QDialog(self)
                dlg.setWindowTitle("Suggested Code")
                layout = QVBoxLayout(dlg)
                te = QTextEdit()
                te.setPlainText(code)
                te.setReadOnly(True)
                layout.addWidget(te)

                btn_layout = QHBoxLayout()
                close_btn = QPushButton("Close")
                exec_btn = QPushButton("Execute on dataset")
                btn_layout.addWidget(exec_btn)
                btn_layout.addWidget(close_btn)
                layout.addLayout(btn_layout)

                def _on_exec():
                    try:
                        new_df = self._safe_execute_transformation(code)
                        if new_df is None:
                            QMessageBox.warning(self, "Execution", "Code did not produce a DataFrame result.")
                        else:
                            # apply with undo support via model.update_data
                            self.model.update_data(new_df)
                            self.update_statistics()
                            QMessageBox.information(self, "Execution", "Transformation applied successfully.")
                    except Exception as e:
                        QMessageBox.critical(self, "Execution Error", f"Failed to execute transformation: {e}")
                    finally:
                        dlg.accept()

                close_btn.clicked.connect(dlg.accept)
                exec_btn.clicked.connect(_on_exec)
                dlg.exec()

                widget.apply_code.connect(_confirm_and_show)
        except Exception as e:
            QMessageBox.critical(self, "AI Assistant Error", f"Could not create assistant: {e}")

    def handle_ai_settings(self):
        dlg = AISettingsDialog(self)
        # show dialog modally; after it closes, reload assistant config
        dlg.exec()

        try:
            new_assistant = assistant_from_config()
            # if assistant dock exists, update the widget
            if hasattr(self, "ai_dock") and self.ai_dock is not None:
                w = self.ai_dock.widget()
                if isinstance(w, AIAssistantWidget):
                    w.assistant = new_assistant
                    try:
                        w._append_chat("System", "Assistant configuration reloaded.")
                    except Exception:
                        pass
        except Exception as e:
            QMessageBox.warning(self, "AI Settings", f"Saved settings but failed to create assistant: {e}")
