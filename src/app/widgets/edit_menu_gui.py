from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox,
    QStackedWidget, QSpinBox, QDoubleSpinBox, QDateEdit, QDateTimeEdit,
    QPushButton
)
from PyQt6.QtCore import QDate, QDateTime


class AddColumnDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Column")

        # Use a less generic variable name to avoid conflicts
        self.main_layout = QVBoxLayout()

        # Column name input
        name_layout = QHBoxLayout()
        name_label = QLabel("Column Name:")
        self.name_input = QLineEdit()
        name_layout.addWidget(name_label)
        name_layout.addWidget(self.name_input)
        self.main_layout.addLayout(name_layout)

        # Data type selector
        type_layout = QHBoxLayout()
        type_label = QLabel("Data Type:")
        self.type_combo = QComboBox()
        self.type_combo.addItems(["String", "Integer", "Float", "Date", "Datetime"])
        self.type_combo.currentIndexChanged.connect(self.update_input_widget)
        type_layout.addWidget(type_label)
        type_layout.addWidget(self.type_combo)
        self.main_layout.addLayout(type_layout)

        # Stacked widget for default values
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

        self.main_layout.addWidget(self.input_stack)

        # Buttons
        button_layout = QHBoxLayout()
        ok_button = QPushButton("OK")
        ok_button.clicked.connect(self.accept)
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(ok_button)
        button_layout.addWidget(cancel_button)
        self.main_layout.addLayout(button_layout)

        self.setLayout(self.main_layout)

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
            value = self.date_input.date().toPyDate()  # Fix here
        elif dtype == "Datetime":
            value = self.datetime_input.dateTime().toPyDateTime()  # Fix here
        else:
            value = None

        return name, dtype, value