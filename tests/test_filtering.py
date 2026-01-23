import datetime

import polars as pl

from logic.filtering import apply_filter_to_df


def test_filter_contains_and_starts_with():
    df = pl.DataFrame({"s": ["apple", "banana", "apricot", ""]})
    # Use a two-letter substring that matches both 'apple' and 'apricot'
    out = apply_filter_to_df(df, "s", "contains", "ap")
    assert out.height == 2

    out2 = apply_filter_to_df(df, "s", "starts_with", "ap")
    assert out2.height == 2


def test_filter_equals_and_between_numeric():
    df = pl.DataFrame({"n": [1, 2, 3, 4, 5]})
    eq = apply_filter_to_df(df, "n", "==", 3)
    assert eq.height == 1 and eq["n"][0] == 3

    between = apply_filter_to_df(df, "n", "between", (2, 4))
    assert between.height == 3


def test_filter_between_dates():
    dates = [
        datetime.date(2024, 1, 1),
        datetime.date(2024, 2, 1),
        datetime.date(2024, 3, 1),
    ]
    df = pl.DataFrame({"d": dates}).with_columns(pl.col("d").cast(pl.Date))
    out = apply_filter_to_df(
        df, "d", "between", (datetime.date(2024, 1, 15), datetime.date(2024, 3, 1))
    )
    assert out.height == 2
