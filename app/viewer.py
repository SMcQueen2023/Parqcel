from PyQt5.QtWidgets import QTableWidget, QTableWidgetItem, QVBoxLayout, QPushButton, QWidget, QFileDialog
import pandas as pd
import os

class ParquetViewer(QWidget):
    def __init__(self, parent=None):
        super(ParquetViewer, self).__init__(parent)

        # Initialize the UI components
        self.df = pd.DataFrame()  # Empty DataFrame to start
        self.init_ui()

    def init_ui(self):
        """Set up the UI elements like table, buttons, etc."""
        self.table_widget = QTableWidget(self)
        self.load_button = QPushButton("Load Parquet", self)
        self.save_button = QPushButton("Save Changes", self)

        layout = QVBoxLayout(self)
        layout.addWidget(self.table_widget)
        layout.addWidget(self.load_button)
        layout.addWidget(self.save_button)

        # Connect buttons to respective functions
        self.load_button.clicked.connect(self.load_parquet_file)
        self.save_button.clicked.connect(self.save_parquet_file)

        self.setWindowTitle('Parqcel - Parquet File Viewer')

    def load_parquet_file(self):
        """Load a Parquet file into the table and DataFrame."""
        # Open file dialog to select Parquet file
        file_path, _ = QFileDialog.getOpenFileName(self, 'Open Parquet File', '', 'Parquet Files (*.parquet)')
        if file_path:
            self.df = pd.read_parquet(file_path)
            self.update_table_from_dataframe(file_path)

    def update_table_from_dataframe(self, file_path=None):
        """Update the table widget with data from the DataFrame."""
        if self.df.empty:
            print("No data to load.")
            return

        # Set row and column count based on DataFrame shape
        self.table_widget.setRowCount(self.df.shape[0])
        self.table_widget.setColumnCount(self.df.shape[1])

        # Set table headers to DataFrame column names
        self.table_widget.setHorizontalHeaderLabels(self.df.columns.tolist())

        # Populate the table with DataFrame data
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
                    new_value = item.text()
                    column_dtype = self.df.dtypes.iloc[col]

                    # Try to cast the value to the appropriate dtype of the DataFrame column
                    try:
                        if pd.api.types.is_numeric_dtype(column_dtype):
                            if "." in new_value:
                                new_value = float(new_value)
                            else:
                                new_value = int(new_value)
                        elif pd.api.types.is_string_dtype(column_dtype):
                            new_value = str(new_value)
                        self.df.iloc[row, col] = new_value
                    except ValueError as e:
                        print(f"Value conversion failed for {new_value} in row {row}, column {col}: {e}")
                        pass

    def save_parquet_file(self):
        """Save the modified DataFrame back to a Parquet file."""
        if self.df.empty:
            print("No data to save.")
            return

        self.update_dataframe_from_table()  # Ensure the table data is reflected in the DataFrame

        # Open file dialog to select the location to save the file
        save_path, _ = QFileDialog.getSaveFileName(self, 'Save Parquet File', '', 'Parquet Files (*.parquet)')
        if save_path:
            self.df.to_parquet(save_path, engine='pyarrow')
            print(f"File saved successfully to {save_path}")