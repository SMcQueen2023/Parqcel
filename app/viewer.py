# app/viewer.py
import sys
import pandas as pd
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QPushButton, QFileDialog, QLabel, QTableWidget, QTableWidgetItem
import pyarrow.parquet as pq
import tkinter as tk
from tkinter import filedialog, messagebox

class ParquetViewer(QWidget):
    def __init__(self):
        super().__init__()
        
        # Set up window
        self.setWindowTitle("Parqcel - Parquet File Viewer")
        self.setGeometry(100, 100, 800, 600)
        
        # Layout
        layout = QVBoxLayout()

        # Button to open a Parquet file
        self.open_button = QPushButton("Open Parquet File")
        self.open_button.clicked.connect(self.load_parquet)
        layout.addWidget(self.open_button)
        
        # Label to show file path
        self.label = QLabel("No file loaded.")
        layout.addWidget(self.label)
        
        # Table to display the Parquet file data
        self.table = QTableWidget()
        layout.addWidget(self.table)
        
        self.setLayout(layout)

    def load_parquet(self):
        """Method to load Parquet file."""
        # Open file dialog to select Parquet file
        file_name, _ = QFileDialog.getOpenFileName(self, "Open Parquet File", "", "Parquet Files (*.parquet);;All Files (*)")
        
        if file_name:
            self.label.setText(f"Loaded: {file_name}")
            # Read Parquet file into DataFrame
            df = pd.read_parquet(file_name)
            self.display_data(df)

    def display_data(self, df):
        """Display DataFrame data in the table."""
        self.table.setRowCount(df.shape[0])
        self.table.setColumnCount(df.shape[1])
        self.table.setHorizontalHeaderLabels(df.columns)
        
        # Populate table with data from DataFrame
        for row in range(df.shape[0]):
            for col in range(df.shape[1]):
                self.table.setItem(row, col, QTableWidgetItem(str(df.iat[row, col])))

    def save_over_parquet(self):
        """Save the changes to the original Parquet file."""
        if self.df is not None and self.parquet_file_path:
            # You can modify the DataFrame here if needed
            # For example, let's say you want to add 1 to the "age" column
            self.df['age'] = self.df['age'] + 1  # Example modification
            
            # Save over the original Parquet file
            self.df.to_parquet(self.parquet_file_path)
            
            messagebox.showinfo("Success", f"Parquet file saved and overwritten at: {self.parquet_file_path}")
        else:
            messagebox.showerror("Error", "No Parquet file loaded.")