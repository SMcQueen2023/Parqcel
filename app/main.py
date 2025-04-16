from app.viewer import ParquetViewer
from PyQt5.QtWidgets import QApplication
import sys

if __name__ == "__main__":
    app = QApplication(sys.argv)
    viewer = ParquetViewer()
    viewer.show()
    sys.exit(app.exec_())