from PyQt5.QtWidgets import QTableWidget, QTableWidgetItem, QVBoxLayout, QPushButton, QWidget
import pandas as pd
import os

class ParquetViewer(QWidget):
    def __init__(self, parent=None):
        super(ParquetViewer, self).__init__(parent)
        
        # Initialize the UI components
        self.df = pd.DataFrame()  # Empty DataFrame for demonstration
        self.init_ui()
    
    def init_ui(self):
        """Set up the UI elements like table, buttons, etc."""
        self.table_widget = QTableWidget(self)
        self.table_widget.setRowCount(5)  # Example row count
        self.table_widget.setColumnCount(3)  # Example column count
        self.load_button = QPushButton("Load Parquet", self)
        self.save_button = QPushButton("Save Changes", self)
        
        layout = QVBoxLayout(self)
        layout.addWidget(self.table_widget)
        layout.addWidget(self.load_button)
        layout.addWidget(self.save_button)
        
        # Connect buttons to respective functions
        self.load_button.clicked.connect(self.load_parquet_file)
        self.save_button.clicked.connect(self.save_parquet_file)
    
    def load_parquet_file(self):
        """Load a Parquet file into the table and DataFrame."""
        file_path = "path_to_your_parquet_file.parquet"  # Set your file path
        if os.path.exists(file_path):
            self.df = pd.read_parquet(file_path)
            self.update_table_from_dataframe()
    
    def update_table_from_dataframe(self):
        """Update the table widget with data from the DataFrame."""
        self.table_widget.setRowCount(self.df.shape[0])
        self.table_widget.setColumnCount(self.df.shape[1])

        for row in range(self.df.shape[0]):
            for col in range(self.df.shape[1]):
                item = QTableWidgetItem(str(self.df.iloc[row, col]))
                self.table_widget.setItem(row, col, item)

    def update_dataframe_from_table(self):
        """Update the DataFrame with the data from the table."""
        for row in range(self.df.shape[0]):
            for col in range(self.df.shape[1]):
                item = self.table_widget.item(row, col)
                if item:
                    # Get the text from the table cell
                    new_value = item.text()

                    # Get the column data type using .iloc
                    column_dtype = self.df.dtypes.iloc[col]

                    # Try to cast the value to the appropriate dtype of the DataFrame column
                    try:
                        # If it's a numeric column, try to convert to float or int
                        if pd.api.types.is_numeric_dtype(column_dtype):
                            if "." in new_value:
                                new_value = float(new_value)  # Convert to float if it has a decimal point
                            else:
                                new_value = int(new_value)  # Convert to int if it's an integer
                        # If the column is of a string type, no conversion is needed
                        elif pd.api.types.is_string_dtype(column_dtype):
                            new_value = str(new_value)
                        # Set the updated value back to the DataFrame
                        self.df.iloc[row, col] = new_value
                    except ValueError as e:
                        print(f"Value conversion failed for {new_value} in row {row}, column {col}: {e}")
                        pass  # Skip any conversion errors
    
    def save_parquet_file(self):
        """Save the modified DataFrame back to a Parquet file."""
        self.update_dataframe_from_table()  # Ensure the table data is reflected in the DataFrame
        self.df.to_parquet("path_to_save_file.parquet", engine="pyarrow")  # Save Parquet
        print("File saved successfully!")