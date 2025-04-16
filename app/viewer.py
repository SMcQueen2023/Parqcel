import polars as pl
from PyQt5.QtWidgets import QTableView, QAbstractItemView, QVBoxLayout, QPushButton, QFileDialog, QMessageBox, QWidget, QHBoxLayout
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QStandardItemModel, QStandardItem

class ParquetViewer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.df = None  # This will hold the Polars DataFrame
        self.model = QStandardItemModel(self)
        self.model.itemChanged.connect(self.on_cell_changed)
        self.table_view = QTableView(self)
        self.table_view.setModel(self.model)
        self.table_view.setEditTriggers(QAbstractItemView.DoubleClicked)

        # Load File Button
        self.load_button = QPushButton('Load File', self)
        self.load_button.clicked.connect(self.load_file)
        self.load_button.setStyleSheet("QPushButton { background-color: #4CAF50; color: white; font-weight: bold; border-radius: 5px; padding: 8px 16px; }")
        
        # Save Button
        self.save_button = QPushButton('Save', self)
        self.save_button.clicked.connect(self.save_data)
        self.save_button.setStyleSheet("QPushButton { background-color: #008CBA; color: white; font-weight: bold; border-radius: 5px; padding: 8px 16px; }")

        # Layout
        button_layout = QHBoxLayout()  # Horizontal layout for buttons
        button_layout.addWidget(self.load_button)
        button_layout.addWidget(self.save_button)

        layout = QVBoxLayout(self)
        layout.addLayout(button_layout)  # Add buttons to the layout
        layout.addWidget(self.table_view)

    def load_file(self):
        """Open a file dialog to load a Parquet file."""
        file_path, _ = QFileDialog.getOpenFileName(self, "Open Parquet File", "", "Parquet Files (*.parquet)")
        if file_path:
            self.load_data(file_path)

    def load_data(self, file_path):
        """Loads a Parquet file into the DataFrame and updates the table view."""
        try:
            # Load the Parquet file into a Polars DataFrame
            self.df = pl.read_parquet(file_path)

            # Update the QTableView
            self.update_table_view()
            print(f"Data successfully loaded from: {file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Load Error", f"Error loading the file: {e}")

    def update_table_view(self):
        """Updates the QTableView with the latest data."""
        if self.df is not None:
            # Clear the model
            self.model.clear()

            # Set headers based on the column names in the DataFrame
            self.model.setHorizontalHeaderLabels(self.df.columns)

            # Populate the model with data
            for row in range(len(self.df)):
                for col in range(len(self.df.columns)):
                    item = QStandardItem(str(self.df[row, col]))
                    self.model.setItem(row, col, item)

            # Refresh the table view
            self.table_view.resizeColumnsToContents()

    def on_cell_changed(self, item):
        """Handles when a cell is edited."""
        row = item.row()
        col = item.column()

        # Get the new value from the table
        value = item.text()

        try:
            # Ensure proper casting to match column type
            column_dtype = self.df.dtypes[col]
            if column_dtype == pl.Int64:
                value = int(value)
            elif column_dtype == pl.Float64:
                value = float(value)
            else:
                value = str(value)

            # Convert to a Pandas DataFrame for easier editing
            df_pandas = self.df.to_pandas()
            df_pandas.iloc[row, col] = value  # Update cell

            # Convert back to Polars DataFrame
            self.df = pl.DataFrame(df_pandas)

            print(f"Updated cell ({row}, {col}) to {value}")
        except Exception as e:
            print(f"Error updating cell ({row}, {col}): {e}")
            QMessageBox.critical(self, "Update Error", f"Error updating the cell: {e}")

    def save_data(self):
        """Saves the DataFrame back to the same Parquet file."""
        try:
            # Save the updated DataFrame back to the Parquet file
            if self.df is not None:
                file_path, _ = QFileDialog.getSaveFileName(self, "Save File", "", "Parquet Files (*.parquet)")
                if file_path:
                    self.df.write_parquet(file_path)
                    print(f"Data successfully saved to: {file_path}")
        except Exception as e:
            print(f"Error saving data: {e}")
            QMessageBox.critical(self, "Save Error", f"Error saving the file: {e}")