import sys
import os
from PyQt6.QtWidgets import QApplication, QMainWindow
from ui.main_window import MainWindow  # Import MainWindow from main_window.py
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton, QMessageBox
from main import MainWindow

def main():
    app = QApplication(sys.argv)

    # Create and show the main window
    window = MainWindow()
    window.show()

    # Start the Qt event loop
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
