import polars as pl
from PyQt5.QtWidgets import QTableView, QVBoxLayout, QWidget, QPushButton, QAbstractItemView
from PyQt5.QtCore import QAbstractTableModel, Qt
from PyQt5.QtGui import QStandardItem, QStandardItemModel

class ParquetViewer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Parquet File Viewer")

        # Initialize the layout and components
        layout = QVBoxLayout(self)
        
        # QTableView for showing the data
        self.table_view = QTableView(self)
        layout.addWidget(self.table_view)

        # Button to load Parquet file
        self.load_button = QPushButton("Load Parquet", self)
        self.load_button.clicked.connect(self.load_parquet)
        layout.addWidget(self.load_button)

        # Button to save data over the original Parquet file
        self.save_button = QPushButton("Save Over", self)
        self.save_button.clicked.connect(self.save_over)
        layout.addWidget(self.save_button)

        # Initialize the Polars DataFrame variable
        self.df = None
        self.model = None

    def load_parquet(self):
        # Replace this with actual file dialog code, or hardcoded file path
        file_path = "path/to/your/parquet/file.parquet"
        
        try:
            # Load the Parquet file using Polars
            self.df = pl.read_parquet(file_path)

            # Convert Polars DataFrame to a format that QTableView can understand
            self.update_table_view()
        except Exception as e:
            print(f"Failed to load Parquet file: {e}")

    def save_over(self):
        # Check if DataFrame is loaded
        if self.df is None:
            print("No data to save!")
            return

        # Save the Polars DataFrame back to the same Parquet file
        try:
            file_path = "path/to/your/parquet/file.parquet"
            self.df.write_parquet(file_path)
            print(f"File saved over: {file_path}")
        except Exception as e:
            print(f"Failed to save the file: {e}")

    def update_table_view(self):
        # Ensure DataFrame is loaded
        if self.df is None:
            print("No data to display!")
            return

        # Convert the Polars DataFrame to a list of lists for the model
        data = self.df.to_pandas().values.tolist()
        columns = self.df.columns

        # Create a model from the data
        self.model = QStandardItemModel(len(data), len(columns))

        # Set the headers for the columns
        for col_idx, col_name in enumerate(columns):
            self.model.setHorizontalHeaderItem(col_idx, QStandardItem(col_name))

        # Populate the table with data
        for row_idx, row_data in enumerate(data):
            for col_idx, value in enumerate(row_data):
                self.model.setItem(row_idx, col_idx, QStandardItem(str(value)))

        # Set the model to the table view
        self.table_view.setModel(self.model)
        self.table_view.setEditTriggers(QAbstractItemView.DoubleClicked)

    def update_value(self, row, col, value):
        # Update a value in the DataFrame
        if self.df is None:
            print("No data to update!")
            return

        # Update the value in the dataframe (create a new one)
        updated_df = self.df.with_columns(
            pl.col(self.df.columns[col]).set_at_idx(row, value)
        )

        # Reassign to self.df and update the table view
        self.df = updated_df
        self.update_table_view()