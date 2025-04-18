import sys
import polars as pl
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QPushButton,
    QFileDialog, QMessageBox, QTableView, QHBoxLayout,
    QLabel, QSpinBox
)
from PyQt5.QtCore import QAbstractTableModel, Qt, QModelIndex, QVariant
from PyQt5.QtGui import QPalette, QColor


class PolarsTableModel(QAbstractTableModel):
    def __init__(self, df: pl.DataFrame, page_size=100):
        super().__init__()
        self.original_df = df.clone()
        self.filtered_df = df.clone()
        self.page_size = page_size
        self.current_page = 0

    def rowCount(self, parent=QModelIndex()):
        return min(self.page_size, len(self.filtered_df) - self.current_page * self.page_size)

    def columnCount(self, parent=QModelIndex()):
        return self.filtered_df.width

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None

        row = self.current_page * self.page_size + index.row()
        col = index.column()

        if role == Qt.DisplayRole or role == Qt.EditRole:
            try:
                return str(self.filtered_df[row, col])
            except:
                return ""
        return None

    def setData(self, index, value, role=Qt.EditRole):
        if role == Qt.EditRole:
            row = self.current_page * self.page_size + index.row()
            col = index.column()
            try:
                col_name = self.filtered_df.columns[col]
                dtype = self.filtered_df.schema[col_name]
                parsed_value = self._convert_to_dtype(value, dtype)
                col_series = self.filtered_df[col_name].to_list()
                col_series[row] = parsed_value
                self.filtered_df = self.filtered_df.with_columns(
                    pl.Series(name=col_name, values=col_series)
                )
                self.dataChanged.emit(index, index, [Qt.DisplayRole])
                return True
            except:
                return False
        return False

    def _convert_to_dtype(self, value, dtype):
        try:
            if dtype == pl.Int64 or dtype == pl.Int32:
                return int(value)
            elif dtype == pl.Float64 or dtype == pl.Float32:
                return float(value)
            elif dtype == pl.Boolean:
                return value.lower() in ('true', '1', 'yes')
            elif dtype == pl.Utf8:
                return str(value)
            else:
                return value
        except:
            return value

    def flags(self, index):
        return Qt.ItemIsSelectable | Qt.ItemIsEnabled | Qt.ItemIsEditable

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole:
            if orientation == Qt.Horizontal:
                col_name = self.filtered_df.columns[section]
                col_dtype = str(self.filtered_df.schema[col_name])
                return f"{col_name}\n[{col_dtype}]"
            else:
                return str(self.current_page * self.page_size + section + 1)
        return None

    def set_page(self, page):
        if 0 <= page <= self.page_count() - 1:
            self.beginResetModel()
            self.current_page = page
            self.endResetModel()

    def set_page_size(self, size):
        self.beginResetModel()
        self.page_size = size
        self.current_page = 0
        self.endResetModel()

    def page_count(self):
        return (len(self.filtered_df) + self.page_size - 1) // self.page_size


class ParquetViewer(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Parqcel")
        self.resize(1000, 600)

        self.table_view = QTableView()
        self.table_view.setAlternatingRowColors(True)
        self.table_view.setStyleSheet("QHeaderView::section { background-color: #f0f0f0; border: 1px solid #c0c0c0; }")

        self.model = None

        self.load_button = QPushButton("Load File")
        self.load_button.clicked.connect(self.load_file)

        self.prev_button = QPushButton("Previous Page")
        self.prev_button.clicked.connect(self.prev_page)

        self.next_button = QPushButton("Next Page")
        self.next_button.clicked.connect(self.next_page)

        self.save_button = QPushButton("Save File")
        self.save_button.clicked.connect(self.save_file)

        self.page_label = QLabel("Page 0 of 0")

        self.page_size_spinbox = QSpinBox()
        self.page_size_spinbox.setRange(10, 10000)
        self.page_size_spinbox.setValue(100)
        self.page_size_spinbox.setPrefix("Page Size: ")
        self.page_size_spinbox.valueChanged.connect(self.change_page_size)

        self.jump_spinbox = QSpinBox()
        self.jump_spinbox.setPrefix("Jump to Page: ")
        self.jump_spinbox.setMinimum(1)
        self.jump_spinbox.valueChanged.connect(self.jump_to_page)

        button_layout = QHBoxLayout()
        for widget in [self.load_button, self.save_button, self.prev_button, self.next_button,
                       self.page_size_spinbox, self.jump_spinbox, self.page_label]:
            button_layout.addWidget(widget)

        layout = QVBoxLayout()
        layout.addLayout(button_layout)
        layout.addWidget(self.table_view)

        self.setLayout(layout)

    def update_page_info(self):
        if self.model:
            total_pages = self.model.page_count()
            current_page = self.model.current_page + 1
            self.page_label.setText(f"Page {current_page} of {total_pages}")
            self.jump_spinbox.setMaximum(total_pages)
            self.jump_spinbox.setValue(current_page)

    def load_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Open Parquet File", "", "Parquet Files (*.parquet)")
        if file_path:
            try:
                df = pl.read_parquet(file_path)
                self.model = PolarsTableModel(df, page_size=self.page_size_spinbox.value())
                self.table_view.setModel(self.model)
                self.table_view.resizeColumnsToContents()
                self.file_path = file_path
                self.update_page_info()
            except Exception as e:
                QMessageBox.critical(self, "Load Error", f"Error loading file: {e}")

    def save_file(self):
        if hasattr(self, 'file_path') and self.model:
            try:
                self.model.filtered_df.write_parquet(self.file_path)
                QMessageBox.information(self, "Success", "File saved successfully.")
            except Exception as e:
                QMessageBox.critical(self, "Save Error", f"Error saving file: {e}")

    def next_page(self):
        if self.model:
            current = self.model.current_page
            if current + 1 < self.model.page_count():
                self.model.set_page(current + 1)
                self.update_page_info()

    def prev_page(self):
        if self.model:
            current = self.model.current_page
            if current > 0:
                self.model.set_page(current - 1)
                self.update_page_info()

    def change_page_size(self, value):
        if self.model:
            self.model.set_page_size(value)
            self.update_page_info()

    def jump_to_page(self, page):
        if self.model:
            self.model.set_page(page - 1)
            self.update_page_info()


def main():
    app = QApplication(sys.argv)
    viewer = ParquetViewer()
    viewer.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()