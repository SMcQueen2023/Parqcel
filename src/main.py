from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon
from app.main_window import MainWindow
from logging_config import configure_logging
import importlib.resources as resources
import logging


def main():
    configure_logging()
    logger = logging.getLogger("parqcel")
    logger.info("Starting Parqcel application")

    app = QApplication([])

    # Create and show the main window
    window = MainWindow()

    # Set application icon from packaged assets, if available
    try:
        icon_path = resources.files("parqcel.assets").joinpath("parqcel_icon.svg")
        if icon_path.is_file():
            window.setWindowIcon(QIcon(str(icon_path)))
    except Exception:
        logger.exception("Failed to set application icon")

    window.show()

    # Start the Qt event loop
    app.exec()


if __name__ == "__main__":
    main()
