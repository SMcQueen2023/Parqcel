import polars as pl
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QTableView, QPushButton, QFileDialog,
    QMessageBox, QAbstractItemView
)
from PyQt5.QtGui import QStandardItemModel, QStandardItem
from PyQt5.QtCore import Qt


class ParquetViewer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.df = None  # Polars DataFrame
        self.file_path = None

        self.model = QStandardItemModel(self)
        self.model.itemChanged.connect(self.on_cell_changed)

        self.table_view = QTableView(self)
        self.table_view.setModel(self.model)
        self.table_view.setEditTriggers(QAbstractItemView.DoubleClicked)

        self.load_button = QPushButton("Load File", self)
        self.load_button.clicked.connect(self.load_file)

        self.save_button = QPushButton("Save", self)
        self.save_button.clicked.connect(self.save_data)

        layout = QVBoxLayout(self)
        layout.addWidget(self.load_button)
        layout.addWidget(self.table_view)
        layout.addWidget(self.save_button)

    def load_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open Parquet File", "", "Parquet Files (*.parquet)")
        if path:
            self.file_path = path
            try:
                self.df = pl.read_parquet(path)
                self.update_table_view()
                print(f"Loaded: {path}")
            except Exception as e:
                QMessageBox.critical(self, "Load Error", f"Error: {e}")

    def update_table_view(self):
        self.model.clear()
        if self.df is not None:
            self.model.setHorizontalHeaderLabels(self.df.columns)
            for row_idx in range(self.df.height):
                for col_idx, col_name in enumerate(self.df.columns):
                    val = str(self.df[row_idx, col_name])
                    item = QStandardItem(val)
                    item.setEditable(True)
                    self.model.setItem(row_idx, col_idx, item)
            self.table_view.resizeColumnsToContents()

    def on_cell_changed(self, item):
        row, col = item.row(), item.column()
        new_value = item.text()
        col_name = self.df.columns[col]

        try:
            current_dtype = self.df.dtypes[col]
            if current_dtype == pl.Int64:
                new_value = int(new_value)
            elif current_dtype == pl.Float64:
                new_value = float(new_value)
            else:
                new_value = str(new_value)

            # Convert to Pandas, update, and convert back to Polars
            df_pd = self.df.to_pandas()
            df_pd.iloc[row, col] = new_value
            self.df = pl.DataFrame(df_pd)

            print(f"Updated cell ({row}, {col}) to {new_value}")
        except Exception as e:
            QMessageBox.critical(self, "Edit Error", f"Could not update cell: {e}")

    def save_data(self):
        if self.df is None:
            QMessageBox.warning(self, "Save Error", "No data to save.")
            return

        path, _ = QFileDialog.getSaveFileName(self, "Save Parquet File", "", "Parquet Files (*.parquet)")
        if path:
            try:
                self.df.write_parquet(path)
                print(f"Saved to: {path}")
            except Exception as e:
                QMessageBox.critical(self, "Save Error", f"Failed to save: {e}")
