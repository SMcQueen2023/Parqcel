import pandas as pd
from PyQt5.QtWidgets import QMainWindow, QPushButton, QFileDialog, QVBoxLayout, QWidget, QMessageBox
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

        # Layout to hold buttons
        layout = QVBoxLayout()
        layout.addWidget(self.load_button)
        layout.addWidget(self.save_button)

        # Create a QWidget to hold the layout
        widget = QWidget()
        widget.setLayout(layout)

        self.setCentralWidget(widget)

    def load_parquet(self):
        """Load a Parquet file and display its content."""
        file_path, _ = QFileDialog.getOpenFileName(self, "Open Parquet File", "", "Parquet Files (*.parquet)")
        if file_path:
            self.parquet_file_path = file_path
            self.df = pd.read_parquet(self.parquet_file_path)
            print(self.df)  # Debugging: Print the DataFrame
            self.save_button.setEnabled(True)  # Enable save button

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
