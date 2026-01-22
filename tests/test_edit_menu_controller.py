import datetime

import polars as pl
import pytest

from app.edit_menu_controller import add_column


def test_add_column_string_and_numeric():
    df = pl.DataFrame({"a": [1, 2, 3]})
    df2 = add_column(df, "new_s", "String", "x")
    assert "new_s" in df2.columns
    assert df2["new_s"][0] == "x"

    df3 = add_column(df2, "new_i", "Integer", 5)
    assert df3["new_i"][0] == 5


def test_add_column_date_and_datetime():
    df = pl.DataFrame({"a": [1, 2]})
    d = datetime.date(2024, 1, 1)
    df2 = add_column(df, "dt", "Date", d)
    assert df2["dt"][0] == d

    dt = datetime.datetime(2024, 1, 1, 12, 0)
    df3 = add_column(df2, "ts", "Datetime", dt)
    assert df3["ts"][0] == dt


def test_add_column_errors():
    df = pl.DataFrame({"a": [1]})
    with pytest.raises(ValueError):
        add_column(df, "", "String", None)

    df2 = add_column(df, "x", "String", "v")
    with pytest.raises(ValueError):
        add_column(df2, "x", "String", "v2")
