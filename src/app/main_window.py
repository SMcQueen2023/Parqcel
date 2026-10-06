from PyQt6.QtWidgets import (
    QMainWindow,
    QFileDialog,
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
    QProgressBar,
    QStackedWidget,
    QListWidget,
    QToolBar,
    QApplication,
)
from PyQt6.QtGui import QAction, QActionGroup, QKeySequence, QIntValidator
from PyQt6.QtCore import Qt, QPoint, QTimer
import importlib.util
import polars as pl
import os
import json
from pathlib import Path
from app.icons import line_icon
from app.preferences import settings
from app.theme import apply_theme, theme_mode
from app.widgets.data_grid import DataGrid
from parqcel import __version__
from app.widgets.filter_dialog import apply_filter
from models.polars_table_model import PolarsTableModel  # Import the model class
from app.widgets.edit_menu_gui import AddColumnDialog, MultiSortDialog
from app.edit_menu_controller import add_column
from parqcel.core.statistics import (
    generate_statistics,
    get_column_statistics,
    get_column_type_counts_string,
)
import webbrowser
from parqcel.core.io import read_dataset, write_dataset_atomic
from parqcel.core.operations import convert_column, featurize_dataset
from parqcel.core.transformations import execute_transformation
from app.background_tasks import run_in_background, has_active_tasks, cancel_tasks
from app.temp_files import TempFileManager
import logging

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Parqcel")
        self.setMinimumSize(800, 600)
        self.resize(1180, 760)
        self.setAcceptDrops(True)
        self.model = None
        self._closing = False
        self._close_ready = False
        self._load_generation = 0
        self._task_generation = 0
        self._statistics_cache = {}
        self._save_task = None
        self._export_task = None
        self.temp_files = TempFileManager()
        self.grid = DataGrid(self)
        self.table_view = self.grid.table_view
        self.table_view.horizontalHeader().setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.table_view.horizontalHeader().customContextMenuRequested.connect(
            self.show_context_menu
        )
        self._createMenuBar()
        self._create_toolbar()

        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(16, 12, 16, 8)
        layout.setSpacing(8)
        heading = QHBoxLayout()
        self.dataset_title = QLabel("Parqcel")
        self.dataset_title.setTextFormat(Qt.TextFormat.PlainText)
        self.dataset_title.setObjectName("workspaceTitle")
        self.dataset_subtitle = QLabel("Explore your Parquet data")
        self.dataset_subtitle.setObjectName("workspaceSubtitle")
        titles = QVBoxLayout()
        titles.setSpacing(2)
        titles.addWidget(self.dataset_title)
        titles.addWidget(self.dataset_subtitle)
        heading.addLayout(titles, 1)
        self.mode_badge = QLabel("Ready")
        self.mode_badge.setObjectName("modeBadge")
        heading.addWidget(self.mode_badge)
        layout.addLayout(heading)
        self.workspace_stack = QStackedWidget()
        self.empty_state = self._create_empty_state()
        self.workspace_stack.addWidget(self.empty_state)
        self.workspace_stack.addWidget(self.grid)
        layout.addWidget(self.workspace_stack, 1)

        self.pagination_layout = QHBoxLayout()
        self.first_button = self._page_button(
            "First page",
            "first",
            self.load_first_page,
        )
        self.prev_button = self._page_button(
            "Previous page", "previous", self.load_previous_page
        )
        self.next_button = self._page_button("Next page", "next", self.load_next_page)
        self.last_button = self._page_button("Last page", "last", self.load_last_page)
        self.page_info_label = QLabel("No dataset open")
        self.page_info_label.setObjectName("secondaryText")
        self.page_input = QLineEdit()
        self.page_input.setPlaceholderText("Page")
        self.page_input.setAccessibleName("Page number")
        self.page_input.setMaximumWidth(85)
        self.page_input.setValidator(QIntValidator(1, 2147483647, self))
        self.page_input.returnPressed.connect(self.jump_to_page)
        self.jump_button = QPushButton("Go")
        self.jump_button.clicked.connect(self.jump_to_page)
        self.row_count_label = QLabel("Total Rows: 0")
        self.total_column_count_label = QLabel("Total Columns: 0")
        self.column_type_count_label = QLabel("Column Type Count: {}", self)
        self.column_type_count_label.hide()
        self.pagination_layout.addWidget(self.row_count_label)
        self.pagination_layout.addWidget(self.total_column_count_label)
        self.pagination_layout.addStretch(1)
        for widget in (
            self.first_button,
            self.prev_button,
            self.page_info_label,
            self.next_button,
            self.last_button,
            self.page_input,
            self.jump_button,
        ):
            self.pagination_layout.addWidget(widget)
        layout.addLayout(self.pagination_layout)
        self.setCentralWidget(container)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setMaximumWidth(140)
        self.progress.hide()
        self.cancel_button = QPushButton("Cancel work")
        self.cancel_button.clicked.connect(self.cancel_work)
        self.cancel_button.hide()
        self.statusBar().addPermanentWidget(self.progress)
        self.statusBar().addPermanentWidget(self.cancel_button)
        self._close_timer = QTimer(self)
        self._close_timer.setInterval(50)
        self._close_timer.timeout.connect(self._finish_close)
        self._refresh_recent_files()
        self.update_page_info()
        self._update_file_actions()

    def _page_button(self, label, icon, callback):
        button = QPushButton(line_icon(icon), "")
        button.setToolTip(label)
        button.setAccessibleName(label)
        button.setFixedWidth(32)
        button.clicked.connect(callback)
        return button

    def _create_toolbar(self):
        self.toolbar = QToolBar("Dataset", self)
        self.toolbar.setMovable(False)
        self.toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.addToolBar(self.toolbar)
        icons = {
            self.open_action: "open",
            self.preview_action: "preview",
            self.save_action: "save",
            self.undo_action: "undo",
            self.redo_action: "redo",
            self.grid.copy_action: "copy",
            self.grid.find_action: "find",
            self.grid.columns_action: "columns",
            self.grid.inspector_action: "inspector",
        }
        for action, icon in icons.items():
            action.setIcon(line_icon(icon))
        for action in (self.preview_action, self.open_action, self.save_action):
            self.toolbar.addAction(action)
        self.toolbar.addSeparator()
        for action in (self.undo_action, self.redo_action):
            self.toolbar.addAction(action)
        self.undo_button = self.toolbar.widgetForAction(self.undo_action)
        self.redo_button = self.toolbar.widgetForAction(self.redo_action)
        self.toolbar.addSeparator()
        for action in (
            self.grid.copy_action,
            self.grid.find_action,
            self.grid.columns_action,
            self.grid.inspector_action,
        ):
            self.toolbar.addAction(action)

    def _create_empty_state(self):
        panel = QWidget()
        panel.setObjectName("emptyState")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(60, 35, 60, 35)
        layout.addStretch(1)
        title = QLabel("A clearer view of your data")
        title.setObjectName("workspaceTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        hint = QLabel(
            "Drop a Parquet file to preview it, or open a dataset for editing."
        )
        hint.setWordWrap(True)
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setObjectName("workspaceSubtitle")
        layout.addWidget(hint)
        actions = QHBoxLayout()
        actions.addStretch(1)
        preview = QPushButton("Preview Parquet...")
        preview.setObjectName("primaryButton")
        preview.clicked.connect(self.preview_parquet)
        actions.addWidget(preview)
        open_button = QPushButton("Open for editing...")
        open_button.clicked.connect(self.open_file)
        actions.addWidget(open_button)
        actions.addStretch(1)
        layout.addLayout(actions)
        layout.addSpacing(20)
        recent_label = QLabel("Recent files")
        recent_label.setObjectName("sectionTitle")
        layout.addWidget(recent_label)
        self.recent_list = QListWidget()
        self.recent_list.setMaximumHeight(180)
        self.recent_list.itemActivated.connect(
            lambda item: self._open_recent(item.data(Qt.ItemDataRole.UserRole))
        )
        layout.addWidget(self.recent_list)
        layout.addStretch(1)
        return panel

    def _recent_files(self):
        try:
            records = json.loads(str(settings().value("files/recent", "[]")))
            return [
                r
                for r in records
                if isinstance(r, dict)
                and isinstance(r.get("path"), str)
                and r.get("mode") in ("preview", "editor")
            ][:10]
        except (ValueError, TypeError):
            return []

    def _remember_file(self, path, mode="editor"):
        path = str(Path(path).absolute())
        records = [
            r
            for r in self._recent_files()
            if os.path.normcase(r["path"]) != os.path.normcase(path)
        ]
        records.insert(0, {"path": path, "mode": mode})
        settings().setValue("files/recent", json.dumps(records[:10]))
        self._refresh_recent_files()

    def _refresh_recent_files(self):
        from PyQt6.QtWidgets import QListWidgetItem

        self.recent_menu.clear()
        self.recent_list.clear()
        for record in self._recent_files():
            label = f"{Path(record['path']).name}  ?  {record['mode'].title()}"
            action = self.recent_menu.addAction(label)
            action.setToolTip(record["path"])
            action.triggered.connect(
                lambda checked=False, r=record: self._open_recent(r)
            )
            item = QListWidgetItem(label)
            item.setToolTip(record["path"])
            item.setData(Qt.ItemDataRole.UserRole, record)
            self.recent_list.addItem(item)
        self.recent_menu.setEnabled(bool(self.recent_list.count()))
        if not self.recent_list.count():
            item = QListWidgetItem("Opened files will appear here")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.recent_list.addItem(item)

    def _open_recent(self, record):
        if not record or self._closing:
            return
        if record["mode"] == "preview":
            self._show_preview(record["path"])
        else:
            self._open_path(record["path"])

    def dragEnterEvent(self, event):
        urls = event.mimeData().urls()
        if (
            len(urls) == 1
            and urls[0].isLocalFile()
            and Path(urls[0].toLocalFile()).suffix.lower() in (".parquet", ".csv")
        ):
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if len(urls) != 1 or not urls[0].isLocalFile() or self._closing:
            return
        path = urls[0].toLocalFile()
        suffix = Path(path).suffix.lower()
        if suffix == ".parquet":
            self._show_preview(path)
        elif suffix == ".csv":
            self._open_path(path)
        else:
            return
        event.acceptProposedAction()

    def _update_file_actions(self):
        loaded = self.model is not None and not self._closing
        busy = self._save_task is not None and self._save_task.is_running
        self.save_action.setEnabled(loaded and not busy)
        self.save_as_action.setEnabled(loaded and not busy)
        self.export_action.setEnabled(
            loaded
            and not busy
            and not (self._export_task and self._export_task.is_running)
        )

    def _optional_modules_available(self, *module_names):
        return all(
            importlib.util.find_spec(module_name) is not None
            for module_name in module_names
        )

    def _set_action_state(self, action, enabled, message=None):
        action.setEnabled(enabled)
        tooltip = (
            "" if enabled else (message or "Optional dependency is not installed.")
        )
        action.setToolTip(tooltip)
        action.setStatusTip(tooltip)

    def _configure_optional_actions(self):
        ml_message = "Install the '[ml]' extras to enable this feature."
        ml_available = self._optional_modules_available("numpy", "sklearn")
        self._set_action_state(self.featurize_action, ml_available, ml_message)
        self._set_action_state(self.dim_action, ml_available, ml_message)

    def _createMenuBar(self):
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("File")

        # Open action
        open_action = self.open_action = QAction("Open for editing...", self)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.triggered.connect(self.open_file)
        file_menu.addAction(open_action)
        preview_action = self.preview_action = QAction("Preview Parquet...", self)
        preview_action.triggered.connect(self.preview_parquet)
        file_menu.addAction(preview_action)
        self.recent_menu = file_menu.addMenu("Recent files")
        file_menu.addSeparator()

        # Save As action
        save_action = self.save_action = QAction("Save", self)
        save_action.setShortcut(QKeySequence.StandardKey.Save)
        save_action.triggered.connect(self.save_current)
        file_menu.addAction(save_action)
        self.save_as_action = QAction("Save As...", self)
        self.save_as_action.setShortcut(QKeySequence.StandardKey.SaveAs)
        self.save_as_action.triggered.connect(self.save_parquet)
        file_menu.addAction(self.save_as_action)
        self.export_action = QAction("Export CSV...", self)
        self.export_action.triggered.connect(self.export_csv)
        file_menu.addAction(self.export_action)

        # Generate statistics action
        stats_action = QAction("Generate Statistics", self)
        stats_action.triggered.connect(self.generate_statistics)

        # Edit menu
        edit_menu = menu_bar.addMenu("Edit")
        self.undo_action = QAction("Undo", self)
        self.undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        self.undo_action.triggered.connect(self.undo)
        self.undo_action.setEnabled(False)
        edit_menu.addAction(self.undo_action)
        self.redo_action = QAction("Redo", self)
        self.redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        self.redo_action.triggered.connect(self.redo)
        self.redo_action.setEnabled(False)
        edit_menu.addAction(self.redo_action)
        edit_menu.addSeparator()
        for action in (
            self.grid.copy_action,
            self.grid.copy_headers_action,
            self.grid.find_action,
            self.grid.go_to_action,
            self.grid.rename_action,
        ):
            edit_menu.addAction(action)

        # Add column action
        add_column_action = QAction("Add Column", self)
        add_column_action.triggered.connect(self.handle_add_column)
        edit_menu.addAction(add_column_action)

        # Multi-Sort action
        sort_columns_action = QAction("Sort Columns...", self)
        sort_columns_action.triggered.connect(self.handle_multi_sort)
        edit_menu.addAction(sort_columns_action)

        view_menu = menu_bar.addMenu("View")
        for action in (
            self.grid.columns_action,
            self.grid.format_action,
            self.grid.inspector_action,
        ):
            view_menu.addAction(action)
        theme_menu = view_menu.addMenu("Appearance")
        theme_group = QActionGroup(self)
        theme_group.setExclusive(True)
        for mode, label in (
            ("system", "Follow system"),
            ("light", "Light"),
            ("dark", "Dark"),
        ):
            action = QAction(label, self, checkable=True)
            action.setChecked(theme_mode() == mode)
            action.triggered.connect(
                lambda checked=False, m=mode: apply_theme(QApplication.instance(), m)
            )
            theme_group.addAction(action)
            theme_menu.addAction(action)

        # Analysis menu
        analysis_menu = menu_bar.addMenu("Analysis")
        analysis_menu.addAction(stats_action)
        self.featurize_action = QAction("Featurize Columns...", self)
        self.featurize_action.triggered.connect(self.handle_featurize)
        analysis_menu.addAction(self.featurize_action)
        self.dim_action = QAction("Dimensionality Reduction...", self)
        self.dim_action.triggered.connect(self.handle_dimensionality)
        analysis_menu.addAction(self.dim_action)
        self.ai_action = QAction("AI Assistant...", self)
        self.ai_action.triggered.connect(self.handle_ai_assistant)
        analysis_menu.addAction(self.ai_action)

        # Settings menu
        settings_menu = menu_bar.addMenu("Settings")
        self.ai_settings_action = QAction("AI Settings...", self)
        self.ai_settings_action.triggered.connect(self.handle_ai_settings)
        settings_menu.addAction(self.ai_settings_action)

        self._configure_optional_actions()
        help_menu = menu_bar.addMenu("Help")
        about = help_menu.addAction("About Parqcel")
        about.triggered.connect(
            lambda: QMessageBox.about(
                self,
                "About Parqcel",
                f"Parqcel {__version__}\n\nParquet viewing, editing and analysis.",
            )
        )

    def preview_parquet(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Preview Parquet", "", "Parquet Files (*.parquet)"
        )
        if path and not self._closing:
            self._show_preview(path)

    def _show_preview(self, path):
        from app.preview_window import PreviewWindow

        if self._closing:
            return
        preview = PreviewWindow(path, parent=self)
        preview.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        preview.show()
        if Path(path).is_file():
            self._remember_file(path, "preview")

    def open_file(self):
        if self._closing:
            return
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open Dataset", "", "Data Files (*.parquet *.csv *.xlsx)"
        )
        if not file_path:
            return
        self._open_path(file_path)

    def _open_path(self, file_path):
        if self._closing:
            return
        csv_types = "strings"
        if file_path.lower().endswith(".csv"):
            choice, accepted = QInputDialog.getItem(
                self,
                "CSV Column Types",
                "Import columns as:",
                ["Strings (preserve text)", "Infer numbers and other types"],
                0,
                False,
            )
            if not accepted:
                return
            csv_types = "infer" if choice.startswith("Infer") else "strings"
        self._confirm_discard(lambda: self.load_file(file_path, csv_types=csv_types))

    def load_file(self, file_path, *, csv_types="strings"):
        """Load a selected file; an intervening edit invalidates the result."""
        self._load_generation += 1
        generation = self._load_generation
        previous = self.model
        revision = previous.session.revision if previous else None

        def loaded(df):
            if generation != self._load_generation:
                return
            if self.model is not previous or (
                previous and previous.session.revision != revision
            ):
                self.statusBar().showMessage(
                    "File load discarded because the dataset changed.", 5000
                )
                return
            self.set_model(PolarsTableModel(df, source_path=file_path))
            self._remember_file(file_path)

        return self._run_task(
            "Opening dataset...",
            lambda: read_dataset(file_path, csv_types=csv_types),
            loaded,
        )

    def set_model(self, model):
        if self.model is not None:
            try:
                self.model.dataset_changed.disconnect(self._dataset_changed)
                self.model.pagination_changed.disconnect(self.update_page_info)
            except TypeError:
                pass
        self.model = model
        self.grid.set_model(
            model, identity=model.session.source_path or "", scope_label="Dataset"
        )
        self.workspace_stack.setCurrentWidget(self.grid)
        model.dataset_changed.connect(self._dataset_changed)
        model.pagination_changed.connect(self.update_page_info)
        # Avoid scanning every visible cell to resize rows on a large dataset.
        self._dataset_changed()

    def _dataset_changed(self):
        if self.model is None:
            return
        self._statistics_cache.clear()
        self.update_page_info()
        self.update_statistics()
        session = self.model.session
        self.undo_button.setEnabled(session.can_undo)
        self.redo_button.setEnabled(session.can_redo)
        self.undo_action.setEnabled(session.can_undo)
        self.redo_action.setEnabled(session.can_redo)
        name = (
            os.path.basename(session.source_path) if session.source_path else "Untitled"
        )
        self.setWindowTitle(f"{name}{' *' if session.dirty else ''} — Parqcel")
        self.dataset_title.setText(name)
        self.dataset_title.setToolTip(session.source_path or "Untitled dataset")
        self.dataset_subtitle.setText(
            "Changes not saved" if session.dirty else "Ready to explore and edit"
        )
        self.mode_badge.setText(
            "Editor · unsaved changes" if session.dirty else "Editor"
        )
        self._update_file_actions()

    def undo(self):
        if self.model is not None:
            self.model.undo()

    def redo(self):
        if self.model is not None:
            self.model.redo()

    def _run_task(self, label, func, on_success):
        if self._closing:
            return None
        self._task_generation += 1
        generation = self._task_generation
        self.statusBar().showMessage(label)
        self.progress.show()
        self.cancel_button.show()

        def error(exc):
            logger.error(
                "%s %s", label, exc, exc_info=(type(exc), exc, exc.__traceback__)
            )
            QMessageBox.critical(self, "Operation Failed", str(exc))

        def finished():
            if not has_active_tasks(self):
                self.progress.hide()
                self.cancel_button.hide()
            if generation == self._task_generation:
                if self.statusBar().currentMessage() == label:
                    self.statusBar().clearMessage()
            self._update_file_actions()

        return run_in_background(self, func, on_success, error, finished)

    def run_dataset_task(self, label, operation, *, on_result=None):
        if not self.is_model_loaded():
            return None
        model = self.model
        revision = model.session.revision
        snapshot = model.get_dataframe()

        def apply(result):
            if self.model is not model or model.session.revision != revision:
                self.statusBar().showMessage(
                    "Result discarded because the dataset changed.", 5000
                )
                return
            if on_result is None:
                model.update_data(result)
            else:
                on_result(result)

        return self._run_task(label, lambda: operation(snapshot), apply)

    def cancel_work(self):
        for grid in self.findChildren(DataGrid):
            grid.cancel_pending_work()
        cancel_tasks(self)
        self._load_generation += 1
        self._task_generation += 1
        self.progress.hide()
        self.cancel_button.hide()
        self.statusBar().showMessage(
            "Results cancelled; active calculations are finishing.", 5000
        )

    def _confirm_discard(self, proceed):
        if self.model is None or not self.model.session.dirty:
            proceed()
            return
        choice = QMessageBox.question(
            self,
            "Unsaved Changes",
            "Save your changes before continuing?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if choice == QMessageBox.StandardButton.Save:
            self.save_current(on_saved=proceed)
        elif choice == QMessageBox.StandardButton.Discard:
            proceed()

    def save_parquet(self, checked=False, *, on_saved=None):
        """Save As, retaining the public entry point used by older integrations."""
        if self._saving_busy() or not self.is_model_loaded():
            return
        file_name, _ = QFileDialog.getSaveFileName(
            self,
            "Save Parquet As",
            self.model.session.source_path or "",
            "Parquet Files (*.parquet)",
        )
        if not file_name:
            return
        if not file_name.lower().endswith(".parquet"):
            file_name += ".parquet"
        return self._save_to(file_name, on_saved=on_saved)

    def save_current(self, checked=False, *, on_saved=None):
        if self._saving_busy() or not self.is_model_loaded():
            return
        path = self.model.session.source_path
        if path and Path(path).suffix.lower() == ".parquet" and Path(path).is_file():
            return self._save_to(path, on_saved=on_saved)
        return self.save_parquet(on_saved=on_saved)

    def _saving_busy(self):
        if self._save_task is not None and self._save_task.is_running:
            self.statusBar().showMessage(
                "A save is already running. Wait for it to finish before saving again.",
                5000,
            )
            return True
        return False

    def _save_to(self, file_name, *, on_saved=None):
        model = self.model
        revision = model.session.revision
        snapshot = model.get_dataframe()

        def saved(_):
            if self.model is not model:
                return
            if model.session.mark_saved(revision, file_name):
                self._dataset_changed()
                self.grid.set_identity(str(file_name))
                self._remember_file(file_name)
                if on_saved is not None:
                    on_saved()
            else:
                self.statusBar().showMessage(
                    "Snapshot saved; newer edits still need saving.", 5000
                )

        self._save_task = self._run_task(
            "Saving Parquet...",
            lambda: write_dataset_atomic(snapshot, file_name),
            saved,
        )
        self._update_file_actions()
        return self._save_task

    def export_csv(self, checked=False):
        if self._closing or not self.is_model_loaded():
            return
        if self._export_task is not None and self._export_task.is_running:
            self.statusBar().showMessage("A CSV export is already running.", 5000)
            return
        source = self.model.session.source_path
        suggestion = str(Path(source).with_suffix(".csv")) if source else "dataset.csv"
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Dataset as CSV", suggestion, "CSV Files (*.csv)"
        )
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"
        snapshot = self.model.get_dataframe()
        self._export_task = self._run_task(
            "Exporting CSV...",
            lambda: write_dataset_atomic(snapshot, path, format="csv"),
            lambda _: self.statusBar().showMessage(f"CSV exported: {path}", 5000),
        )
        self._update_file_actions()
        return self._export_task

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
        if self.model is None:
            for control in (
                self.first_button,
                self.prev_button,
                self.next_button,
                self.last_button,
                self.page_input,
                self.jump_button,
            ):
                control.setEnabled(False)
            return
        max_pages = self.model.get_max_pages()
        current_page = self.model.get_current_page() + 1 if max_pages else 0
        self.page_info_label.setText(f"Page {current_page} of {max_pages}")
        self.first_button.setEnabled(current_page > 1)
        self.prev_button.setEnabled(current_page > 1)
        self.next_button.setEnabled(current_page < max_pages)
        self.last_button.setEnabled(current_page < max_pages)
        self.page_input.setEnabled(max_pages > 0)
        self.jump_button.setEnabled(max_pages > 0)
        self.page_input.clear()

    def show_context_menu(self, pos: QPoint):
        if self.model is None:
            return
        column = self.table_view.horizontalHeader().logicalIndexAt(pos)
        if column < 0:
            return
        column_name = self.model._data.columns[column]
        dtype = self.model._data.schema[column_name]
        self.grid.set_current_column(column)

        menu = QMenu(self)
        for shared_action in (
            self.grid.rename_action,
            self.grid.format_action,
            self.grid.columns_action,
            self.grid.inspector_action,
        ):
            menu.addAction(shared_action)
        menu.addSeparator()

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
        if dtype.is_numeric():
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
        action = menu.exec(self.table_view.horizontalHeader().mapToGlobal(pos))
        if action is None:
            return
        if action == sort_asc:
            self.run_dataset_task("Sorting rows...", lambda df: df.sort(column_name))
        elif action == sort_desc:
            self.run_dataset_task(
                "Sorting rows...", lambda df: df.sort(column_name, descending=True)
            )
        elif action == drop_col:
            self.model.drop_column(column_name)
            self.update_statistics()
        elif action == stats_col:
            self.run_dataset_task(
                "Computing column statistics...",
                lambda df: get_column_statistics(df, column_name),
                on_result=lambda text: QMessageBox.information(
                    self, f"Statistics for {column_name}", text
                ),
            )
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

        self.run_dataset_task(
            "Converting column...", lambda df: convert_column(df, column_name, new_type)
        )

    def generate_statistics(self):
        if not self.is_model_loaded():
            return
        key = (self.model.session.id, self.model.session.revision)
        if key in self._statistics_cache:
            self.show_statistics_window(self._statistics_cache[key])
            return

        def show(text):
            self._statistics_cache[key] = text
            self.show_statistics_window(text)

        self.run_dataset_task(
            "Computing statistics...", generate_statistics, on_result=show
        )

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
                self.run_dataset_task(
                    "Sorting rows...",
                    lambda df: df.sort(
                        list(columns), descending=[not d for d in directions]
                    ),
                )
            else:
                logger.debug("No sort criteria provided.")
        else:
            logger.debug("MultiSortDialog canceled or closed")

    def handle_featurize(self):
        try:
            from app.widgets.featurize_gui import FeaturizeDialog
            from ds.featurize import detect_columns
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Missing dependency",
                "Featurization requires the '[ml]' extras. Install them to use this feature.",
            )
            logger.debug("Featurize dependencies unavailable", exc_info=exc)
            return

        if not self.is_model_loaded():
            return

        df = self.model.get_dataframe()
        numeric, categorical, text = detect_columns(df)

        dialog = FeaturizeDialog(
            self.model.get_column_names(), numeric, categorical, text, parent=self
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            selected = dialog.get_selected_columns()
            # Split selected columns by detected type
            sel_numeric = [c for c in selected if c in numeric]
            sel_categorical = [c for c in selected if c in categorical]
            sel_text = [c for c in selected if c in text]
            opts = dialog.get_options()

            def _task(df):
                return featurize_dataset(
                    df,
                    numeric_cols=sel_numeric,
                    categorical_cols=sel_categorical,
                    text_cols=sel_text,
                    scale_numeric=opts.get("scale_numeric"),
                    one_hot=opts.get("one_hot", True),
                    tfidf_max_features=opts.get("tfidf_max_features", 200),
                )

            self.run_dataset_task("Generating features...", _task)

    def handle_dimensionality(self):
        try:
            from app.widgets.pca_gui import PCADialog
            from parqcel.core.projection import build_projection
        except Exception:
            QMessageBox.critical(
                self,
                "Missing dependency",
                "NumPy is required for dimensionality reduction. Install the '[ml]' extras or numpy in your environment.",
            )
            return
        if not self.is_model_loaded():
            return

        col_names = self.model.get_column_names()

        dialog = PCADialog(col_names, parent=self)
        # allow coloring by any column
        dialog.set_color_choices(col_names)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        selected = dialog.get_selected_columns()
        if not selected:
            QMessageBox.warning(
                self, "No features", "Please select at least one feature column."
            )
            return

        opts = dialog.get_options()

        self.statusBar().showMessage("Computing dimensionality reduction...")

        def _success(result):
            if result.get("html_path"):
                webbrowser.open(result["html_path"])
            if result.get("plot_error"):
                QMessageBox.information(
                    self,
                    "Dimensionality Result",
                    f"Embedding computed (shape {result['emb_shape']}). Could not render interactive plot: {result['plot_error']}",
                )

        self.run_dataset_task(
            "Computing dimensionality reduction...",
            lambda df: build_projection(df, selected, opts, self.temp_files),
            on_result=_success,
        )

    def _safe_execute_transformation(self, code: str):
        """Execute a validated operation plan without evaluating Python."""
        if not self.is_model_loaded():
            raise ValueError("Open a dataset first.")
        return execute_transformation(self.model.get_dataframe(), code)

    def handle_ai_assistant(self):
        # Create or show an AI assistant dock widget
        try:
            if hasattr(self, "ai_dock") and self.ai_dock is not None:
                self.ai_dock.show()
                return

            # import factory lazily to avoid heavy ML/backends imports during module import
            from app.widgets.ai_assistant import AIAssistantWidget
            from ai.assistant import assistant_from_config

            assistant = assistant_from_config()
            widget = AIAssistantWidget(assistant=assistant, parent=self)
            dock = QDockWidget("AI Assistant", self)
            dock.setWidget(widget)
            dock.setAllowedAreas(
                Qt.DockWidgetArea.RightDockWidgetArea
                | Qt.DockWidgetArea.LeftDockWidgetArea
            )
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
                    self.run_dataset_task(
                        "Applying transformation...",
                        lambda df: execute_transformation(df, code),
                    )
                    dlg.accept()

                close_btn.clicked.connect(dlg.accept)
                exec_btn.clicked.connect(_on_exec)
                dlg.exec()

            widget.apply_code.connect(_confirm_and_show)
        except Exception as e:
            QMessageBox.critical(
                self, "AI Assistant Error", f"Could not create assistant: {e}"
            )

    def handle_ai_settings(self):
        from app.widgets.ai_assistant import AIAssistantWidget
        from app.widgets.ai_settings import AISettingsDialog

        dlg = AISettingsDialog(self)
        # show dialog modally; after it closes, reload assistant config
        dlg.exec()

        try:
            from ai.assistant import assistant_from_config

            new_assistant = assistant_from_config()
            # if assistant dock exists, update the widget
            if hasattr(self, "ai_dock") and self.ai_dock is not None:
                w = self.ai_dock.widget()
                if isinstance(w, AIAssistantWidget):
                    w.assistant = new_assistant
                    try:
                        w._append_chat("System", "Assistant configuration reloaded.")
                    except Exception:
                        # Non-critical: failure to append a system message should not block settings update
                        logger.exception(
                            "Failed to append system message after reloading AI assistant settings."
                        )
        except Exception as e:
            QMessageBox.warning(
                self,
                "AI Settings",
                f"Saved settings but failed to create assistant: {e}",
            )

    def _begin_close(self):
        for grid in self.findChildren(DataGrid):
            grid.prepare_close()
        self._closing = True
        cancel_tasks(self)
        self.setEnabled(False)
        self.statusBar().showMessage("Waiting for active work to finish...")
        self._close_timer.start()

    def _finish_close(self):
        if has_active_tasks(self):
            return
        self._close_timer.stop()
        self.temp_files.cleanup()
        self._close_ready = True
        self.close()

    def closeEvent(self, event):
        if self._close_ready:
            event.accept()
            return
        event.ignore()
        if not self._closing:
            self._confirm_discard(self._begin_close)
