import numpy as np
import polars as pl

from models.polars_table_model import PolarsTableModel
from app.main_window import MainWindow


def _run_sync(owner, func, on_success, on_error, on_finished=None):
    try:
        on_success(func())
    except Exception as exc:
        on_error(exc)
    finally:
        if on_finished is not None:
            on_finished()


def test_handle_featurize_uses_background_runner(monkeypatch, qapp):
    import app.main_window as main_window_module
    import app.widgets.featurize_gui as featurize_gui_module
    import ds.featurize as featurize_module

    called = {"background": False}

    def run_sync(owner, func, on_success, on_error, on_finished=None):
        called["background"] = True
        return _run_sync(owner, func, on_success, on_error, on_finished)

    class FakeDialog:
        def __init__(self, *args, **kwargs):
            pass

        def exec(self):
            from PyQt6.QtWidgets import QDialog

            return QDialog.DialogCode.Accepted

        def get_selected_columns(self):
            return ["a"]

        def get_options(self):
            return {"one_hot": True, "tfidf_max_features": 5, "scale_numeric": "standard"}

    monkeypatch.setattr(main_window_module, "run_in_background", run_sync)
    monkeypatch.setattr(featurize_gui_module, "FeaturizeDialog", FakeDialog)
    monkeypatch.setattr(featurize_module, "detect_columns", lambda df: (["a"], [], []))
    monkeypatch.setattr(
        featurize_module,
        "generate_feature_matrix",
        lambda *args, **kwargs: (np.array([[10], [20]]), ["feat_a"]),
    )
    monkeypatch.setattr(
        featurize_module,
        "add_features_to_df",
        lambda df, X, feature_names: df.with_columns(
            pl.Series(feature_names[0], X[:, 0].tolist())
        ),
    )

    mw = MainWindow()
    mw.model = PolarsTableModel(pl.DataFrame({"a": [1, 2]}), chunk_size=10)
    mw.table_view.setModel(mw.model)

    mw.handle_featurize()

    assert called["background"] is True
    assert "feat_a" in mw.model._data.columns