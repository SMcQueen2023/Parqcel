from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLineEdit, QDialogButtonBox,
    QComboBox, QDateEdit, QStackedWidget, QSpinBox, QDoubleSpinBox, 
    QLabel, QMessageBox
)
from PyQt6.QtCore import QDate
import polars as pl

class AddColumnDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add New Column")

        self.layout = QVBoxLayout(self)
        form_layout = QFormLayout()

        self.name_input = QLineEdit()
        form_layout.addRow("Column Name:", self.name_input)

        self.type_combo = QComboBox()
        self.type_combo.addItems(["String", "Integer", "Float", "Date"])
        form_layout.addRow("Data Type:", self.type_combo)

        self.input_stack = QStackedWidget()

        # Default value widgets
        self.string_input = QLineEdit()
        self.input_stack.addWidget(self.string_input)

        self.int_input = QSpinBox()
        self.input_stack.addWidget(self.int_input)

        self.float_input = QDoubleSpinBox()
        self.float_input.setDecimals(4)
        self.input_stack.addWidget(self.float_input)

        self.date_input = QDateEdit()
        self.date_input.setCalendarPopup(True)
        self.date_input.setDate(QDate.currentDate())
        self.input_stack.addWidget(self.date_input)

        form_layout.addRow("Default Value:", self.input_stack)

        self.type_combo.currentIndexChanged.connect(self.input_stack.setCurrentIndex)

        self.layout.addLayout(form_layout)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self.accept)  # Connect to the new accept() method
        self.buttons.rejected.connect(self.reject)
        self.layout.addWidget(self.buttons)

    def accept(self):
        col_name = self.name_input.text().strip()

        # Validate the column name
        if not col_name:
            QMessageBox.warning(self, "Invalid Column Name", "Please enter a column name (no blanks).")
            return
        
        if any(c in col_name for c in r'<>:"/\|?*'):
            QMessageBox.warning(self, "Invalid Column Name", "The column name contains invalid characters.")
            return

        super().accept()  # Proceed with the parent accept() method if valid

    def get_data(self):
        name = self.name_input.text().strip()
        dtype = self.type_combo.currentText()

        if dtype == "String":
            value = self.string_input.text()
        elif dtype == "Integer":
            value = self.int_input.value()
        elif dtype == "Float":
            value = self.float_input.value()
        elif dtype == "Date":
            qdate = self.date_input.date()
            value = qdate.toString("yyyy-MM-dd")
        else:
            value = None

        return name, dtype, value


def add_column(df: pl.DataFrame, parent=None) -> pl.DataFrame:
    dialog = AddColumnDialog(parent)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return df

    col_name, dtype, default_value = dialog.get_data()

    # If the column name is invalid, return without modifying the DataFrame
    if not col_name or any(c in col_name for c in r'<>:"/\|?*') or col_name.strip() == "":
        QMessageBox.warning(parent, "Invalid Column Name", "Please enter a valid column name.")
        return df  # Reject invalid column names

    try:
        if dtype == "Integer":
            default_value = int(default_value)
        elif dtype == "Float":
            default_value = float(default_value)
        elif dtype == "Date":
            default_value = str(default_value)
        else:
            default_value = str(default_value)
    except ValueError:
        return df

    new_col = pl.Series(name=col_name, values=[default_value] * df.height)
    return df.with_columns([new_col])