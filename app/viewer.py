import polars as pl
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QFileDialog, QMessageBox, QLineEdit, QLabel, QTableView, QHeaderView, QComboBox
)
from PyQt5.QtCore import Qt, QAbstractTableModel, QVariant
import sys


class PolarsTableModel(QAbstractTableModel):
    def __init__(self, df, parent=None):
        super().__init__(parent)
        self.original_df = df
        self.filtered_df = df
        self.columns = df.columns

    def rowCount(self, parent=None):
        return self.filtered_df.height

    def columnCount(self, parent=None):
        return len(self.columns)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return QVariant()
        if role in (Qt.DisplayRole, Qt.EditRole):
            return str(self.filtered_df[index.row, index.column])
        return QVariant()

    def setData(self, index, value, role=Qt.EditRole):
        if index.isValid() and role == Qt.EditRole:
            try:
                col_name = self.columns[index.column()]
                dtype = self.original_df.schema[col_name]
                if dtype == pl.Int64:
                    value = int(value)
                elif dtype == pl.Float64:
                    value = float(value)
                else:
                    value = str(value)

                self.original_df = self.original_df.with_columns(
                    self.original_df[col_name].set_at_idx(index.row(), value)
                )
                self.filtered_df = self.original_df
                self.dataChanged.emit(index, index)
                return True
            except Exception as e:
                print(f"Error updating cell: {e}")
        return False

    def flags(self, index):
        return Qt.ItemIsSelectable | Qt.ItemIsEnabled | Qt.ItemIsEditable

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole:
            if orientation == Qt.Horizontal:
                return self.columns[section]
            else:
                return section + 1
        return QVariant()

    def apply_filter(self, text):
        if text:
            try:
                self.filtered_df = self.original_df.filter(pl.any_horizontal(self.original_df.select(pl.col("*").cast(str)).str.contains(text)))
            except Exception as e:
                print(f"Filter error: {e}")
                self.filtered_df = self.original_df
        else:
            self.filtered_df = self.original_df
        self.layoutChanged.emit()

    def apply_sort(self, column, order):
        try:
            reverse = (order == Qt.DescendingOrder)
            self.filtered_df = self.filtered_df.sort(self.columns[column], descending=reverse)
            self.layoutChanged.emit()
        except Exception as e:
            print(f"Sort error: {e}")


class ParquetViewer(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Parqcel Viewer")
        self.df = None
        self.model = None

        self.table_view = QTableView()
        self.table_view.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        self.load_button = QPushButton("Load")
        self.load_button.setStyleSheet("padding: 6px 12px; border-radius: 10px; background-color: #0078D4; color: white;")
        self.load_button.clicked.connect(self.load_file)

        self.save_button = QPushButton("Save")
        self.save_button.setStyleSheet("padding: 6px 12px; border-radius: 10px; background-color: #28A745; color: white;")
        self.save_button.clicked.connect(self.save_file)

        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("Filter...")
        self.filter_input.textChanged.connect(self.apply_filter)

        self.sort_column = QComboBox()
        self.sort_column.currentIndexChanged.connect(self.apply_sort)
        self.sort_order = QComboBox()
        self.sort_order.addItems(["Ascending", "Descending"])
        self.sort_order.currentIndexChanged.connect(self.apply_sort)

        # Layouts
        button_layout = QHBoxLayout()
        button_layout.addWidget(self.load_button)
        button_layout.addWidget(self.save_button)
        button_layout.setSpacing(10)

        sort_layout = QHBoxLayout()
        sort_layout.addWidget(QLabel("Sort by:"))
        sort_layout.addWidget(self.sort_column)
        sort_layout.addWidget(self.sort_order)

        control_layout = QHBoxLayout()
        control_layout.addLayout(button_layout)
        control_layout.addStretch()
        control_layout.addWidget(self.filter_input)

        main_layout = QVBoxLayout()
        main_layout.addLayout(control_layout)
        main_layout.addLayout(sort_layout)
        main_layout.addWidget(self.table_view)
        self.setLayout(main_layout)

    def load_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Open Parquet File", "", "Parquet Files (*.parquet)")
        if file_path:
            try:
                self.df = pl.read_parquet(file_path)
                self.model = PolarsTableModel(self.df)
                self.table_view.setModel(self.model)
                self.sort_column.clear()
                self.sort_column.addItems(self.df.columns)
                print(f"Data successfully loaded from: {file_path}")
            except Exception as e:
                QMessageBox.critical(self, "Load Error", f"Failed to load file: {e}")

    def save_file(self):
        if self.df is None:
            return
        file_path, _ = QFileDialog.getSaveFileName(self, "Save File", "", "Parquet Files (*.parquet)")
        if file_path:
            try:
                self.model.original_df.write_parquet(file_path)
                print(f"Data successfully saved to: {file_path}")
            except Exception as e:
                QMessageBox.critical(self, "Save Error", f"Failed to save file: {e}")

    def apply_filter(self):
        if self.model:
            self.model.apply_filter(self.filter_input.text())

    def apply_sort(self):
        if self.model:
            column = self.sort_column.currentIndex()
            order = Qt.AscendingOrder if self.sort_order.currentIndex() == 0 else Qt.DescendingOrder
            self.model.apply_sort(column, order)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    viewer = ParquetViewer()
    viewer.resize(800, 600)
    viewer.show()
    sys.exit(app.exec_())