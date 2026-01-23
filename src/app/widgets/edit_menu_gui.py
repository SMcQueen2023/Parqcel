from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QComboBox,
    QStackedWidget,
    QSpinBox,
    QDoubleSpinBox,
    QDateEdit,
    QDateTimeEdit,
    QPushButton,
    QWidget,
    QListWidgetItem,
    QListWidget,
    QMessageBox,
)
from PyQt6.QtCore import QDate, QDateTime


class AddColumnDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Column")

        # Main layout
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
            value = self.date_input.date().toPyDate()
        elif dtype == "Datetime":
            value = self.datetime_input.dateTime().toPyDateTime()
        else:
            value = None
        return name, dtype, value


class MultiSortDialog(QDialog):
    def __init__(self, column_names, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Multi-Sort")

        self.column_names = column_names  # List of available columns

        self.layout = QVBoxLayout(self)

        # Instruction label
        instruction_label = QLabel("Select columns to sort by (in order):")
        self.layout.addWidget(instruction_label)

        # Sort list (with column name and ASC/DESC for each)
        self.sort_list_widget = QListWidget()
        self.layout.addWidget(self.sort_list_widget)

        # Add column sort rule
        add_layout = QHBoxLayout()
        self.column_selector = QComboBox()
        self.column_selector.addItems(self.column_names)

        self.order_selector = QComboBox()
        self.order_selector.addItems(["Ascending", "Descending"])

        add_button = QPushButton("Add Sort Rule")
        add_button.clicked.connect(self.add_sort_rule)

        add_layout.addWidget(QLabel("Column:"))
        add_layout.addWidget(self.column_selector)
        add_layout.addWidget(QLabel("Order:"))
        add_layout.addWidget(self.order_selector)
        add_layout.addWidget(add_button)

        self.layout.addLayout(add_layout)

        # OK/Cancel buttons
        button_layout = QHBoxLayout()
        ok_button = QPushButton("OK")
        ok_button.clicked.connect(self.accept)
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)

        button_layout.addWidget(ok_button)
        button_layout.addWidget(cancel_button)
        self.layout.addLayout(button_layout)

    def add_sort_rule(self):
        column = self.column_selector.currentText()

        # Prevent duplicates
        for i in range(self.sort_list_widget.count()):
            item = self.sort_list_widget.item(i)
            widget = self.sort_list_widget.itemWidget(item)
            if widget and widget.column_label.text() == column:
                return  # Already added

        order = self.order_selector.currentText()

        item = QListWidgetItem()
        widget = SortRuleWidget(column, order)  # Make sure SortRuleWidget is imported
        self.sort_list_widget.addItem(item)
        self.sort_list_widget.setItemWidget(item, widget)
        item.setSizeHint(widget.sizeHint())

    def get_sorting_criteria(self):
        criteria = []
        for i in range(self.sort_list_widget.count()):
            item = self.sort_list_widget.item(i)
            widget = self.sort_list_widget.itemWidget(item)
            if widget:
                column = widget.column_label.text()
                ascending = widget.order_combo.currentText() == "Ascending"
                criteria.append((column, ascending))
        return criteria

    def accept(self):
        criteria = self.get_sorting_criteria()
        if not criteria:
            QMessageBox.warning(
                self, "No Sort Criteria", "Please add at least one sort rule."
            )
            return
        super().accept()


class SortRuleWidget(QWidget):
    def __init__(self, column_name, order="Ascending", parent=None):
        super().__init__(parent)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.column_label = QLabel(column_name)
        self.order_combo = QComboBox()
        self.order_combo.addItems(["Ascending", "Descending"])
        self.order_combo.setCurrentText(order)

        self.remove_button = QPushButton("X")
        self.remove_button.setFixedSize(20, 20)
        self.remove_button.clicked.connect(self._on_remove_clicked)

        layout.addWidget(self.column_label)
        layout.addWidget(self.order_combo)
        layout.addWidget(self.remove_button)

    def _on_remove_clicked(self):
        # Remove this widget's QListWidgetItem from the list
        list_widget = self.parent()
        if isinstance(list_widget, QListWidget):
            for i in range(list_widget.count()):
                if list_widget.itemWidget(list_widget.item(i)) is self:
                    list_widget.takeItem(i)
                    break
