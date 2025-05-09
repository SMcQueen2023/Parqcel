from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox,
    QStackedWidget, QSpinBox, QDoubleSpinBox, QDateEdit, QDateTimeEdit,
    QPushButton, QMessageBox
)
from PyQt6.QtCore import QDate, QDateTime
import polars as pl


class AddColumnDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Add Column")
        self.layout = QVBoxLayout()

        # Column name input
        name_layout = QHBoxLayout()
        name_label = QLabel("Column Name:")
        self.name_input = QLineEdit()
        name_layout.addWidget(name_label)
        name_layout.addWidget(self.name_input)
        self.layout.addLayout(name_layout)

        # Data type selector
        type_layout = QHBoxLayout()
        type_label = QLabel("Data Type:")
        self.type_combo = QComboBox()
        self.type_combo.addItems(["String", "Integer", "Float", "Date", "Datetime"])
        self.type_combo.currentIndexChanged.connect(self.update_input_widget)
        type_layout.addWidget(type_label)
        type_layout.addWidget(self.type_combo)
        self.layout.addLayout(type_layout)

        # Stacked widget to show appropriate default value input
        self.input_stack = QStackedWidget()

        self.string_input = QLineEdit()
        self.input_stack.addWidget(self.string_input)

        self.int_input = QSpinBox()
        self.input_stack.addWidget(self.int_input)

        self.float_input = QDoubleSpinBox()
        self.input_stack.addWidget(self.float_input)

        self.date_input = QDateEdit()
        self.date_input.setCalendarPopup(True)
        self.date_input.setDate(QDate.currentDate())
        self.input_stack.addWidget(self.date_input)

        self.datetime_input = QDateTimeEdit()
        self.datetime_input.setCalendarPopup(True)
        self.datetime_input.setDateTime(QDateTime.currentDateTime())
        self.input_stack.addWidget(self.datetime_input)

        self.layout.addWidget(self.input_stack)

        # OK and Cancel buttons
        button_layout = QHBoxLayout()
        ok_button = QPushButton("OK")
        ok_button.clicked.connect(self.accept)
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(ok_button)
        button_layout.addWidget(cancel_button)
        self.layout.addLayout(button_layout)

        self.setLayout(self.layout)

    def update_input_widget(self, index):
        self.input_stack.setCurrentIndex(index)

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
            value = self.date_input.date().toString("yyyy-MM-dd")
        elif dtype == "Datetime":
            value = self.datetime_input.dateTime().toString("yyyy-MM-ddTHH:mm:ss")
        else:
            value = None

        return name, dtype, value


def add_column(df: pl.DataFrame, parent=None):
    dialog = AddColumnDialog()
    if dialog.exec():
        col_name, dtype, default_value = dialog.get_data()

        if col_name in df.columns:
            QMessageBox.warning(parent, "Error", f"Column '{col_name}' already exists.")
            return df

        try:
            if dtype == "Integer":
                default_value = int(default_value)
                new_col = pl.Series(name=col_name, values=[default_value] * df.height, dtype=pl.Int64)
            elif dtype == "Float":
                default_value = float(default_value)
                new_col = pl.Series(name=col_name, values=[default_value] * df.height, dtype=pl.Float64)
            elif dtype == "Date":
                new_col = pl.Series(name=col_name, values=[default_value] * df.height).cast(pl.Date)
            elif dtype == "Datetime":
                new_col = pl.Series(name=col_name, values=[default_value] * df.height).cast(pl.Datetime)
            else:  # String
                new_col = pl.Series(name=col_name, values=[default_value] * df.height, dtype=pl.Utf8)

            df = df.with_columns(new_col)

        except Exception as e:
            QMessageBox.warning(parent, "Error", f"Could not add column: {str(e)}")

    return df
