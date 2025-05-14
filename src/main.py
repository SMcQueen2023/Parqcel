from PyQt6.QtWidgets import QApplication
from app.main_window import MainWindow
from models.polars_table_model import PolarsTableModel

def main():
    app = QApplication([])

    # Create and show the main window
    window = MainWindow()
    window.show()

    # Start the Qt event loop
    app.exec()

if __name__ == "__main__":
    main()
