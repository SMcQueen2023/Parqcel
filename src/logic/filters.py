import polars as pl
from PyQt6.QtWidgets import (
    QInputDialog, QMessageBox
)
from logic.stats import get_page_data

def apply_filter(self, column_name, filter_type):
    # Ask for the filter value
    filter_value, ok = QInputDialog.getText(self, "Enter Filter Value", f"Filter {column_name} with {filter_type}:")
    
    if ok and filter_value:
        self.model.save_state()  # Save current state before applying filter (for undo functionality)

        # Convert the filter_value to float if it is a numeric filter
        try:
            if filter_type in ["<", "<=", "==", ">", ">="]:
                filter_value = float(filter_value)  # For numeric columns
        except ValueError:
            # Handle invalid numeric input
            if filter_type in ["<", "<=", "==", ">", ">="]:
                QMessageBox.warning(self, "Invalid Value", "Please enter a valid number.")
                return

        # Apply the filter based on the selected filter type
        try:
            if filter_type == "contains":
                self.model._data = self.model._data.filter(pl.col(column_name).str.contains(filter_value))
            elif filter_type == "starts_with":
                self.model._data = self.model._data.filter(pl.col(column_name).str.starts_with(filter_value))
            elif filter_type == "ends_with":
                self.model._data = self.model._data.filter(pl.col(column_name).str.ends_with(filter_value))
            elif filter_type == "==":
                self.model._data = self.model._data.filter(pl.col(column_name) == filter_value)
            elif filter_type == "<":
                self.model._data = self.model._data.filter(pl.col(column_name) < filter_value)
            elif filter_type == "<=":
                self.model._data = self.model._data.filter(pl.col(column_name) <= filter_value)
            elif filter_type == ">":
                self.model._data = self.model._data.filter(pl.col(column_name) > filter_value)
            elif filter_type == ">=":
                self.model._data = self.model._data.filter(pl.col(column_name) >= filter_value)
        except Exception as e:
            QMessageBox.warning(self, "Filter Error", f"Error applying filter: {str(e)}")
            return

        # Refresh current data
        self.model._current_data = get_page_data(self.model._data, self.model.get_current_page(), self.model.chunk_size)
        self.model.layoutChanged.emit()
        
        self.update_page_info()  # Refresh UI to reflect new data
