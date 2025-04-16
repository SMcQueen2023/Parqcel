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
            # Example modification: Adding 1 to the "age" column
            if 'age' in self.df.columns:
                self.df['age'] = self.df['age'] + 1  # Modify the DataFrame as needed
            
            # Save over the original Parquet file
            self.df.to_parquet(self.parquet_file_path)

            # Show a success message
            QMessageBox.information(self, "Success", f"Parquet file saved and overwritten at: {self.parquet_file_path}")
        else:
            QMessageBox.warning(self, "Error", "No Parquet file loaded.")