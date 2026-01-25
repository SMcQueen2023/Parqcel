from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon
from app.main_window import MainWindow
from logging_config import configure_logging
import importlib.resources as resources
from importlib.resources import as_file
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
        icon_res = resources.files("parqcel.assets").joinpath("parqcel_icon.svg")
        with as_file(icon_res) as icon_path:
            window.setWindowIcon(QIcon(str(icon_path)))
    except Exception:
        logger.exception("Failed to set application icon")

    window.show()

    # Start the Qt event loop
    app.exec()


if __name__ == "__main__":
    main()
