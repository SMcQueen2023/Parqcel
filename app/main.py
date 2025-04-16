from app.viewer import ParquetViewer
from PyQt5.QtWidgets import QApplication, QMainWindow
import sys
import os

# Ensure the parent directory of 'app' is in the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    app = QApplication(sys.argv)

    # Initialize the ParquetViewer and set it up as a main window
    viewer = ParquetViewer()
    viewer.setWindowTitle("Parquet File Viewer")
    viewer.resize(600, 400)
    viewer.show()

    sys.exit(app.exec_())
