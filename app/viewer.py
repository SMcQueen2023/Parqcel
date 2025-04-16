import polars as pl
from PyQt5.QtWidgets import QTableView, QVBoxLayout, QWidget, QPushButton, QFileDialog, QMessageBox
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QStandardItemModel, QStandardItem

class ParquetViewer(QWidget):
    def __init__(self):
        super().__init__()
        self.df = None  # Initialize an empty DataFrame
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("Parquet Viewer")
        self.setGeometry(100, 100, 800, 600)

        layout = QVBoxLayout()

        # TableView
        self.table_view = QTableView(self)
        layout.addWidget(self.table_view)

        # Load Button
        load_button = QPushButton("Load Parquet File", self)
        load_button.clicked.connect(self.load_file)
        layout.addWidget(load_button)

        # Save Button
        save_button = QPushButton("Save Parquet File", self)
        save_button.clicked.connect(self.save_over)
        layout.addWidget(save_button)

        self.setLayout(layout)

    def load_file(self):
        # Open file dialog to load a parquet file
        file_path, _ = QFileDialog.getOpenFileName(self, "Open Parquet File", "", "Parquet Files (*.parquet)")

        if file_path:
            try:
                # Read the parquet file into a Polars DataFrame
                self.df = pl.read_parquet(file_path)

                # Debug: Show DataFrame content in the console
                print("Loaded DataFrame:")
                print(self.df)

                # Set up the model for QTableView
                self.model = QStandardItemModel()
                self.model.setHorizontalHeaderLabels(self.df.columns)
                self.table_view.setModel(self.model)

                # Populate the table view with data from the DataFrame
                for row in self.df.iter_rows():
                    row_items = [QStandardItem(str(val)) for val in row]
                    self.model.appendRow(row_items)

                print(f"Data successfully loaded from: {file_path}")

            except Exception as e:
                print(f"Failed to load parquet file: {e}")

    def save_over(self):
        if self.df is None:
            print("No data to save!")
            return

        # Debug: Confirm the DataFrame is not empty and has updated data
        print("DataFrame to save:")
        print(self.df)

        # Open file dialog to save the updated file
        file_path, _ = QFileDialog.getSaveFileName(self, "Save Parquet File", "", "Parquet Files (*.parquet)")

        if not file_path:
            print("No file path provided!")
            return

        # Debug: Show the file path to ensure we're saving to the right place
        print(f"Saving over: {file_path}")

        try:
            # Save the updated DataFrame to the same Parquet file
            self.df.write_parquet(file_path, compression='snappy')

            # Confirm save with a message box
            QMessageBox.information(self, "File Saved", f"File has been saved over: {file_path}")
            print(f"File saved over: {file_path}")

        except Exception as e:
            print(f"Failed to save the file: {e}")
            QMessageBox.critical(self, "Save Error", f"Failed to save the file: {e}")

    def update_cell(self, row, col, value):
        """ Update the cell in the dataframe """
        if self.df is not None:
            # Update the Polars DataFrame
            self.df[row, col] = value

            # Debug: Show updated value
            print(f"Updated cell at ({row}, {col}) to {value}")
            
            self.update_table_view()

    def update_table_view(self):
        """ Update the QTableView to reflect changes """
        for row in range(self.df.height):
            for col in range(self.df.width):
                index = self.model.index(row, col)
                self.model.setData(index, str(self.df[row, col]))
