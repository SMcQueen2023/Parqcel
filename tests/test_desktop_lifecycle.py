import threading

import polars as pl
from PyQt6.QtWidgets import QMessageBox

from app.background_tasks import has_active_tasks
from app.main_window import MainWindow
from models.polars_table_model import PolarsTableModel


def window(qtbot):
    widget = MainWindow()
    qtbot.addWidget(widget)
    widget.set_model(PolarsTableModel(pl.DataFrame({"a": [1, 2]})))
    return widget


def test_old_result_cannot_overwrite_new_file(qtbot):
    widget = window(qtbot)
    entered, release = threading.Event(), threading.Event()

    def operation(df):
        entered.set()
        assert release.wait(5)
        return df.with_columns(pl.lit(9).alias("a"))

    task = widget.run_dataset_task("Test", operation)
    qtbot.waitUntil(entered.is_set)
    replacement = PolarsTableModel(pl.DataFrame({"b": [42]}))
    widget.set_model(replacement)
    release.set()
    qtbot.waitUntil(lambda: not task.is_running)
    assert widget.model is replacement
    assert widget.model.get_dataframe().to_dict(as_series=False) == {"b": [42]}


def test_old_result_cannot_overwrite_edit(qtbot):
    widget = window(qtbot)
    entered, release = threading.Event(), threading.Event()

    def operation(df):
        entered.set()
        assert release.wait(5)
        return df.head(1)

    task = widget.run_dataset_task("Test", operation)
    qtbot.waitUntil(entered.is_set)
    assert widget.model.setData(widget.model.index(0, 0), "7")
    release.set()
    qtbot.waitUntil(lambda: not task.is_running)
    assert widget.model.get_dataframe()["a"].to_list() == [7, 2]


def test_close_defers_until_work_finishes(qtbot):
    widget = window(qtbot)
    widget.show()
    entered, release = threading.Event(), threading.Event()

    def operation(df):
        entered.set()
        assert release.wait(5)
        return df.head(1)

    widget.run_dataset_task("Test", operation)
    qtbot.waitUntil(entered.is_set)
    widget.close()
    assert widget._closing and not widget._close_ready
    assert has_active_tasks(widget)
    release.set()
    qtbot.waitUntil(lambda: widget._close_ready)
    assert not widget.isVisible()
    assert widget.model.get_dataframe().height == 2


def test_cancel_unsaved_close_keeps_window(qtbot, monkeypatch):
    widget = window(qtbot)
    widget.show()
    widget.model.drop_column("a")
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Cancel,
    )
    widget.close()
    assert widget.isVisible()
    assert not widget._closing
    widget.model.undo()


def test_undo_updates_footer_and_buttons(qtbot):
    widget = window(qtbot)
    widget.model.update_data(widget.model.get_dataframe().head(1))
    assert widget.row_count_label.text() == "Total Rows: 1"
    widget.undo()
    assert widget.row_count_label.text() == "Total Rows: 2"
    assert widget.redo_button.isEnabled()


def test_opening_twice_does_not_connect_old_undo(qtbot):
    widget = window(qtbot)
    old = widget.model
    old.add_column("b", 0)
    widget.set_model(PolarsTableModel(pl.DataFrame({"c": [1]})))
    widget.model.add_column("d", 0)
    widget.undo_button.click()
    assert old.get_column_names() == ["a", "b"]
    assert widget.model.get_column_names() == ["c"]
