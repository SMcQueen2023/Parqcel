import polars as pl
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QFileDialog, QTableView, QMessageBox
)
from PyQt5.QtCore import Qt, QAbstractTableModel, QModelIndex


class PolarsTableModel(QAbstractTableModel):
    def __init__(self, df: pl.DataFrame):
        super().__init__()
        self._df = df

    def rowCount(self, parent=QModelIndex()):
        return self._df.height

    def columnCount(self, parent=QModelIndex()):
        return self._df.width

    def data(self, index, role=Qt.DisplayRole):
        if role == Qt.DisplayRole:
            return str(self._df[index.row(), index.column()])
        elif role == Qt.EditRole:
            return str(self._df[index.row(), index.column()])
        return None

    def setData(self, index, value, role=Qt.EditRole):
        if role == Qt.EditRole:
            col_name = self._df.columns[index.column()]
            try:
                # Cast value to original type
                dtype = self._df.schema[col_name]
                cast_value = pl.Series("", [value]).cast(dtype)[0]
                self._df = self._df.with_columns(
                    self._df[col_name].set_at_idx(index.row(), cast_value).alias(col_name)
                )
                self.dataChanged.emit(index, index, [Qt.DisplayRole])
                return True
            except Exception as e:
                print(f"Failed to update value: {e}")
        return False

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole:
            if orientation == Qt.Horizontal:
                return self._df.columns[section]
            else:
                return str(section)
        return None

    def flags(self, index):
        return Qt.ItemIsSelectable | Qt.ItemIsEnabled | Qt.ItemIsEditable


class ParquetViewer(QWidget):
    def __init__(self):
        super().__init__()
        self.df = None
        self.model = None
        self.current_file = None

        self.setWindowTitle("Parqcel - Polars Edition")
        self.resize(800, 600)

        self.layout = QVBoxLayout()
        self.setLayout(self.layout)

        self.table_view = QTableView()
        self.layout.addWidget(self.table_view)

        self.load_button = QPushButton("Load Parquet")
        self.load_button.clicked.connect(self.load_parquet)
        self.layout.addWidget(self.load_button)

        self.save_button = QPushButton("Save")
        self.save_button.clicked.connect(self.save_parquet)
        self.layout.addWidget(self.save_button)

    def load_parquet(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open Parquet File", "", "Parquet Files (*.parquet);;All Files (*)"
        )
        if file_path:
            try:
                self.df = pl.read_parquet(file_path)
                self.current_file = file_path
                self.model = PolarsTableModel(self.df)
                self.table_view.setModel(self.model)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to load file:\n{e}")

    def save_parquet(self):
        if self.df is not None and self.current_file:
            try:
                self.df.write_parquet(self.current_file)
                QMessageBox.information(self, "Saved", "File saved successfully.")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save file:\n{e}")
