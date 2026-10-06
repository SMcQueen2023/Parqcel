from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import QTimer
from app.main_window import MainWindow
from app.theme import setup_theme
from logging_config import configure_logging
import importlib.resources as resources
import logging
import sys


def main():
    configure_logging()
    logger = logging.getLogger("parqcel")
    logger.info("Starting Parqcel application")

    app = QApplication([])
    app.setApplicationName("Parqcel")
    app.setOrganizationName("Parqcel")
    setup_theme(app)

    # Create and show the main window
    window = MainWindow()

    # Set application icon from packaged assets, if available
    try:
        icon_res = resources.files("parqcel.assets").joinpath("parqcel_icon.svg")
        from importlib.resources import as_file

        with as_file(icon_res) as icon_path:
            window.setWindowIcon(QIcon(str(icon_path)))
    except Exception:
        logger.exception("Failed to set application icon")

    window.show()

    if "--smoke-test" in sys.argv:
        import polars as pl
        from models.polars_table_model import PolarsTableModel

        window.set_model(PolarsTableModel(pl.DataFrame({"value": [1, 2]})))
        window.model.sort_column("value", ascending=False)
        window.model.undo()
        if window.model.get_dataframe()["value"].to_list() != [1, 2]:
            raise RuntimeError("Desktop smoke test failed")
        QTimer.singleShot(0, window.close)

    # Start the Qt event loop
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
