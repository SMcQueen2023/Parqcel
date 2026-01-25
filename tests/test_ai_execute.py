import polars as pl
from app.main_window import MainWindow


def test_safe_execute_allowed():
    # create a dummy MainWindow and small dataframe
    mw = MainWindow()
    df = pl.DataFrame({"a": [1, 2, 3], "b": [10, 20, 30]})
    mw.model = type("M", (), {})()  # lightweight model stub
    mw.model.get_dataframe = lambda: df
    code = "df.filter(pl.col('a') > 1).select(['a','b'])"
    res = mw._safe_execute_transformation(code)
    assert isinstance(res, pl.DataFrame)
    assert res.height == 2


def test_safe_execute_disallowed_import():
    mw = MainWindow()
    df = pl.DataFrame({"a": [1]})
    mw.model = type("M", (), {})()
    mw.model.get_dataframe = lambda: df
    bad_code = "import os\nos.system('echo hi')"
    try:
        mw._safe_execute_transformation(bad_code)
        assert False, "Import should be rejected"
    except ValueError:
        pass
