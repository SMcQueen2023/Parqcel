import polars as pl
from PyQt6.QtCore import Qt

from app.main_window import MainWindow
from models.polars_table_model import PolarsTableModel


def test_undo_redo_buttons_restore_dropped_column(qtbot):
    mw = MainWindow()
    qtbot.addWidget(mw)

    df = pl.DataFrame({"a": [1, 2], "b": [3, 4], "c": [5, 6]})
    mw.model = PolarsTableModel(df, chunk_size=10)
    mw.table_view.setModel(mw.model)
    mw.undo_button.clicked.connect(mw.model.undo)
    mw.redo_button.clicked.connect(mw.model.redo)

    mw.model.drop_column("b")
    assert mw.model._data.columns == ["a", "c"]

    qtbot.mouseClick(mw.undo_button, Qt.MouseButton.LeftButton)
    assert mw.model._data.columns == ["a", "b", "c"]

    qtbot.mouseClick(mw.redo_button, Qt.MouseButton.LeftButton)
    assert mw.model._data.columns == ["a", "c"]