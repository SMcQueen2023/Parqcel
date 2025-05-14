from PyQt6.QtWidgets import (
    QInputDialog, QMessageBox, QDialog, QVBoxLayout,
    QPushButton, QDateEdit, QDateTimeEdit
)
from PyQt6.QtCore import QDate, QDateTime
import datetime
import polars as pl
from logic.stats import get_page_data

def apply_filter(self, column_name, filter_type):
    # Determine column data type first
    try:
        column_dtype = self.model._data.schema[column_name]
    except KeyError:
        QMessageBox.warning(self, "Column Error", f"Column '{column_name}' not found.")
        return

    # Customize the filter prompt based on type and operator
    if filter_type == "==":
        if column_dtype in [pl.Utf8, pl.Categorical]:
            prompt_text = "String value equals:"
        elif column_dtype == pl.Boolean:
            prompt_text = "Boolean value equals (true/false):"
        elif column_dtype in [pl.Date, pl.Datetime, pl.Time]:
            prompt_text = "Date/Time value equals (e.g. 2024-01-01):"
        else:
            prompt_text = "Numeric value equals:"
    elif filter_type == "contains":
        prompt_text = "String contains:"
    elif filter_type == "starts_with":
        prompt_text = "String starts with:"
    elif filter_type == "ends_with":
        prompt_text = "String ends with:"
    else:
        prompt_text = f"Filter {column_name} with {filter_type}:"

    # Ask the user for a filter value
    if column_dtype == pl.Date:
        dialog = QDialog(self)
        dialog.setWindowTitle("Select Date")
        layout = QVBoxLayout(dialog)
        date_edit = QDateEdit()
        date_edit.setCalendarPopup(True)
        date_edit.setDate(QDate.currentDate())
        layout.addWidget(date_edit)
        ok_button = QPushButton("OK")
        ok_button.clicked.connect(dialog.accept)
        layout.addWidget(ok_button)
        if dialog.exec():
            selected_date = date_edit.date()
            filter_value = datetime.date(
                selected_date.year(), selected_date.month(), selected_date.day()
            )
        else:
            return

    elif column_dtype == pl.Datetime:
        dialog = QDialog(self)
        dialog.setWindowTitle("Select Date and Time")
        layout = QVBoxLayout(dialog)
        datetime_edit = QDateTimeEdit()
        datetime_edit.setCalendarPopup(True)
        datetime_edit.setDateTime(QDateTime.currentDateTime())
        layout.addWidget(datetime_edit)
        ok_button = QPushButton("OK")
        ok_button.clicked.connect(dialog.accept)
        layout.addWidget(ok_button)
        if dialog.exec():
            dt = datetime_edit.dateTime().toPyDateTime()
            filter_value = dt
        else:
            return

    else:
        # Fallback for other types
        filter_value, ok = QInputDialog.getText(self, "Enter Filter Value", prompt_text)
        if not ok or not filter_value:
            return

    self.model.save_state()  # Save current state for undo

    # Parse filter_value based on column dtype
    try:
        if column_dtype in [pl.Float32, pl.Float64,
                            pl.Int8, pl.Int16, pl.Int32, pl.Int64,
                            pl.UInt8, pl.UInt16, pl.UInt32, pl.UInt64]:
            if filter_type in ["<", "<=", "==", ">", ">="]:
                filter_value = float(filter_value)
        elif column_dtype == pl.Boolean:
            filter_value = filter_value.strip().lower()
            if filter_value in ["true", "1", "yes"]:
                filter_value = True
            elif filter_value in ["false", "0", "no"]:
                filter_value = False
            else:
                raise ValueError("Boolean value must be true or false")
        elif column_dtype in [pl.Date, pl.Datetime]:
            if not isinstance(filter_value, (datetime.date, datetime.datetime)):
                raise ValueError("Filter value must be a valid date/datetime.")
        elif column_dtype in [pl.Utf8, pl.Categorical]:
            pass  # keep as string
        else:
            raise TypeError(f"Filtering not supported for type: {column_dtype}")
    except (ValueError, TypeError) as e:
        QMessageBox.warning(self, "Invalid Input", str(e))
        return

    # Apply the actual filter
    try:
        col = pl.col(column_name)
        if filter_type == "contains":
            self.model._data = self.model._data.filter(col.str.contains(filter_value))
        elif filter_type == "starts_with":
            self.model._data = self.model._data.filter(col.str.starts_with(filter_value))
        elif filter_type == "ends_with":
            self.model._data = self.model._data.filter(col.str.ends_with(filter_value))
        elif filter_type == "==":
            self.model._data = self.model._data.filter(col == filter_value)
        elif filter_type == "<":
            self.model._data = self.model._data.filter(col < filter_value)
        elif filter_type == "<=":
            self.model._data = self.model._data.filter(col <= filter_value)
        elif filter_type == ">":
            self.model._data = self.model._data.filter(col > filter_value)
        elif filter_type == ">=":
            self.model._data = self.model._data.filter(col >= filter_value)
    except Exception as e:
        QMessageBox.warning(self, "Filter Error", f"Error applying filter: {str(e)}")
        return

    # Refresh table view
    self.model._current_data = get_page_data(
        self.model._data,
        self.model.get_current_page(),
        self.model.chunk_size
    )
    self.model.layoutChanged.emit()
    self.update_page_info()
