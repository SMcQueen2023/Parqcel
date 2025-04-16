import pandas as pd
from PyQt5.QtWidgets import QMainWindow, QPushButton, QFileDialog, QVBoxLayout, QWidget, QTableWidget, QTableWidgetItem, QMessageBox
from PyQt5.QtCore import Qt

class ParquetViewer(QMainWindow):
    def __init__(self):
        super().__init__()

        # Initialize main window
        self.df = None
        self.parquet_file_path = None

        # Create buttons
        self.load_button = QPushButton("Load Parquet File")
        self.load_button.clicked.connect(self.load_parquet)

        self.save_button = QPushButton("Save Changes")
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self.save_over_parquet)

        # Create a QTableWidget to display the DataFrame
        self.table_widget = QTableWidget()
        
        # Layout to hold buttons and the table
        layout = QVBoxLayout()
        layout.addWidget(self.load_button)
        layout.addWidget(self.save_button)
        layout.addWidget(self.table_widget)

        # Create a QWidget to hold the layout
        widget = QWidget()
        widget.setLayout(layout)

        self.setCentralWidget(widget)

    def load_parquet(self):
        """Load a Parquet file and display its content in the table."""
        file_path, _ = QFileDialog.getOpenFileName(self, "Open Parquet File", "", "Parquet Files (*.parquet)")
        if file_path:
            self.parquet_file_path = file_path
            self.df = pd.read_parquet(self.parquet_file_path)

            # Display the DataFrame in the QTableWidget
            self.display_data_in_table()

            # Enable save button
            self.save_button.setEnabled(True)

    def display_data_in_table(self):
        """Populate the QTableWidget with the loaded DataFrame."""
        if self.df is not None:
            # Set the row count and column count
            self.table_widget.setRowCount(len(self.df))
            self.table_widget.setColumnCount(len(self.df.columns))

            # Set the headers for the columns
            self.table_widget.setHorizontalHeaderLabels(self.df.columns)

            # Populate the table with the data
            for row in range(len(self.df)):
                for col in range(len(self.df.columns)):
                    self.table_widget.setItem(row, col, QTableWidgetItem(str(self.df.iloc[row, col])))

    def save_over_parquet(self):
        """Save the changes to the original Parquet file."""
        if self.df is not None and self.parquet_file_path:
            # Update the DataFrame with changes made in the table
            self.update_dataframe_from_table()

            # Save over the original Parquet file
            self.df.to_parquet(self.parquet_file_path)

            # Show a success message
            QMessageBox.information(self, "Success", f"Parquet file saved and overwritten at: {self.parquet_file_path}")
        else:
            QMessageBox.warning(self, "Error", "No Parquet file loaded.")

    def update_dataframe_from_table(self):
        """Update the DataFrame with the data from the table."""
        for row in range(self.df.shape[0]):
            for col in range(self.df.shape[1]):
                item = self.table_widget.item(row, col)
                if item:
                    # Get the text from the table cell
                    new_value = item.text()

                    # Try to cast the value to the appropriate dtype of the DataFrame column
                    try:
                        column_dtype = self.df.dtypes[col]

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

    def reset_table(self):
        """Reset the table after saving to ensure it is up to date."""
        self.display_data_in_table()