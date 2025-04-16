from app.viewer import ParquetViewer
from PyQt5.QtWidgets import QApplication
import sys
import os

# Ensure the parent directory of 'app' is in the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    app = QApplication(sys.argv)
    viewer = ParquetViewer()
    viewer.show()
    sys.exit(app.exec_())