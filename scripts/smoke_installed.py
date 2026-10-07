"""Run with isolated Python after installing the wheel, outside the checkout."""

import importlib.resources
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication  # noqa: E402
import polars as pl  # noqa: E402
from app.main_window import MainWindow  # noqa: E402
from app.theme import apply_theme  # noqa: E402
from app.background_tasks import has_active_tasks  # noqa: E402
from models.polars_table_model import PolarsTableModel  # noqa: E402
from parqcel.core.io import read_dataset, write_dataset_atomic  # noqa: E402


def _wait_for(app, predicate, *, timeout=10):
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() >= deadline:
            raise RuntimeError("Desktop smoke operation timed out")
        app.processEvents()
        time.sleep(0.005)


def _run_smoke():
    app = QApplication([])
    apply_theme(app, "dark")
    window = MainWindow()
    window.set_model(PolarsTableModel(pl.DataFrame({"a": [2, 1]})))
    window.model.sort_column("a")
    window.model.undo()
    assert window.model.get_dataframe()["a"].to_list() == [2, 1]
    window.grid.set_column_format("a", mode="number", precision=2)
    window.table_view.setCurrentIndex(window.model.index(0, 0))
    assert window.grid.copy_selection()
    assert app.clipboard().text() == "2\n"
    window.model.insert_pasted_rows(1, "3\n4\n", ["a"])
    assert window.model.get_dataframe()["a"].to_list() == [2, 3, 4, 1]
    window.undo()
    assert window.model.get_dataframe()["a"].to_list() == [2, 1]
    assert not window.model.session.dirty
    apply_theme(app, "light")
    assert (
        importlib.resources.files("parqcel.assets")
        .joinpath("parqcel_icon.svg")
        .is_file()
    )
    assert importlib.resources.files("ai").joinpath("prompts.json").is_file()
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "roundtrip.parquet"
        write_dataset_atomic(window.model.get_dataframe(), path)
        assert read_dataset(path).height == 2
        optimizer = window.open_parquet_optimizer()
        assert optimizer.analyze()
        _wait_for(app, lambda: not has_active_tasks(window))
        assert optimizer.export_button.isEnabled()
        output = Path(directory) / "optimized.parquet"
        assert optimizer.export_selected(output)
        _wait_for(app, lambda: not has_active_tasks(window))
        assert sorted(read_dataset(output)["a"].to_list()) == [1, 2]
        assert window.model.get_dataframe()["a"].to_list() == [2, 1]
        assert not window.model.session.dirty
        optimizer.close()
        subprocess.run(
            [sys.executable, "-I", "-m", "parqcel.cli", "--help"],
            cwd=directory,
            check=True,
        )
    window.close()
    _wait_for(app, lambda: window._close_ready, timeout=5)
    print("Installed wheel desktop, optimizer, CLI, resources and Parquet I/O passed.")


def main():
    with tempfile.TemporaryDirectory(prefix="parqcel-smoke-settings-") as directory:
        os.environ["PARQCEL_SETTINGS_FILE"] = str(Path(directory) / "preferences.ini")
        _run_smoke()


if __name__ == "__main__":
    main()
