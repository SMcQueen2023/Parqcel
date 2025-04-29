import sys
import os
from PyQt6.QtWidgets import QApplication, QMainWindow
from ui.main_window import MainWindow  # Import MainWindow from main_window.py
from licensing.license_validator import validate_license_key
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton, QMessageBox

# Ensure the compiled .pyd file is in sys.path (add the directory containing the .pyd file)
sys.path.append(os.path.join(os.path.dirname(__file__), 'cython'))

# Import MainWindow from the compiled .pyd file
from main import MainWindow

LICENSE_FILE = "license_key.txt"  # Path to store the license key

class LicenseDialog(QDialog):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Parcel DataSuite License Key Entry")
        self.setFixedSize(400, 200)

        layout = QVBoxLayout()

        self.label = QLabel("Please enter your license key to proceed:")
        layout.addWidget(self.label)

        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Enter your license key here")
        layout.addWidget(self.input_field)

        self.submit_button = QPushButton("Submit")
        self.submit_button.clicked.connect(self.submit_license)
        layout.addWidget(self.submit_button)

        self.setLayout(layout)

    def submit_license(self):
        input_key = self.input_field.text()
        if validate_license_key(input_key):
            self.accept()  # Close the dialog and return True
            with open(LICENSE_FILE, 'w') as f:
                f.write(input_key)
        else:
            QMessageBox.critical(self, "License Error", "Invalid License Key. Access Denied.")

def check_existing_license():
    if os.path.exists(LICENSE_FILE):
        with open(LICENSE_FILE, 'r') as f:
            stored_key = f.read().strip()
            if validate_license_key(stored_key):
                return True
            else:
                print("Stored license key is invalid.")
    return False

def main():
    app = QApplication(sys.argv)

    # Check for a valid license first
    if not check_existing_license():
        dialog = LicenseDialog()
        if dialog.exec() != QDialog.DialogCode.Accepted:
            sys.exit(1)  # Exit if the user cancels or the license is invalid

    # Create and show the main window
    window = MainWindow()
    window.show()

    # Start the Qt event loop
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
