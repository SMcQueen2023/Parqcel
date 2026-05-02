import polars as pl
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFileDialog

from app.main_window import MainWindow


def test_main_window_open_edit_drop_undo_save_smoke(qtbot, monkeypatch, tmp_path):
    input_path = tmp_path / "input.csv"
    output_path = tmp_path / "output.parquet"
    input_path.write_text("a,b\n1,foo\n2,bar\n", encoding="utf-8")

    mw = MainWindow()
    qtbot.addWidget(mw)

    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileName",
        lambda *args, **kwargs: (str(input_path), "Data Files (*.parquet *.csv *.xlsx)"),
    )
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        lambda *args, **kwargs: (str(output_path), "Parquet Files (*.parquet)"),
    )

    mw.open_file()
    assert mw.model is not None
    assert mw.model.columnCount() == 2

    index = mw.model.index(0, 0)
    assert mw.model.setData(index, "10", role=Qt.ItemDataRole.EditRole) is True
    assert mw.model._data["a"][0] == "10"

    mw.model.drop_column("b")
    assert mw.model._data.columns == ["a"]

    qtbot.mouseClick(mw.undo_button, Qt.MouseButton.LeftButton)
    assert mw.model._data.columns == ["a", "b"]

    mw.save_parquet()
    saved = pl.read_parquet(output_path)
    assert saved.columns == ["a", "b"]
    assert saved["a"][0] == "10"