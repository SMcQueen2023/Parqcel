import polars as pl
import datetime

from logic.stats import (
    get_numeric_stats,
    get_string_stats,
    get_boolean_stats,
    get_date_stats,
    get_datetime_stats,
    generate_statistics,
    get_page_data,
    calculate_max_pages,
    get_column_statistics,
    get_column_type_counts_string,
)


def test_calculate_max_pages():
    assert calculate_max_pages(0, 10) == 0
    assert calculate_max_pages(1, 10) == 1
    assert calculate_max_pages(10, 10) == 1
    assert calculate_max_pages(11, 10) == 2


def test_get_page_data():
    df = pl.DataFrame({"a": list(range(25))})
    page = get_page_data(df, 1, 10)
    assert page.height == 10
    assert page["a"].to_list()[0] == 10


def test_numeric_stats():
    series = pl.Series([1, 2, 3, 4, 5])
    stats = get_numeric_stats(series)
    assert any(line.startswith("Mean:") for line in stats)
    assert any(line.startswith("Std Dev:") for line in stats)


def test_string_stats():
    series = pl.Series(["a", "bb", "", None])
    stats = get_string_stats(series)
    assert any(line.startswith("Unique:") for line in stats)
    assert "Top Values:" in stats


def test_boolean_stats():
    series = pl.Series([True, False, True, None])
    stats = get_boolean_stats(series)
    assert any(line.startswith("True:") for line in stats)
    assert any(line.startswith("False:") for line in stats)


def test_date_stats():
    series = pl.Series([datetime.date(2024, 1, 1), datetime.date(2024, 2, 1)])
    series = series.cast(pl.Date)
    stats = get_date_stats(series)
    assert any(line.startswith("Earliest:") for line in stats)
    assert any(line.startswith("Latest:") for line in stats)


def test_datetime_stats():
    series = pl.Series(
        [
            datetime.datetime(2024, 1, 1, 10, 0, 0),
            datetime.datetime(2024, 1, 2, 10, 0, 0),
        ]
    ).cast(pl.Datetime)
    stats = get_datetime_stats(series)
    assert any(line.startswith("Min:") for line in stats)
    assert any(line.startswith("Max:") for line in stats)


def test_generate_statistics_and_column_helpers():
    df = pl.DataFrame(
        {
            "num": [1, 2, 3],
            "txt": ["a", "b", "b"],
            "flag": [True, False, True],
        }
    )

    class DummyModel:
        def __init__(self, data):
            self._data = data

    output = generate_statistics(DummyModel(df))
    assert "Column: num" in output
    assert "Column: txt" in output
    assert "Column: flag" in output

    stats = get_column_statistics(df, "num")
    assert "Non-Nulls" in stats

    type_counts = get_column_type_counts_string(df)
    assert "Int64" in type_counts
    assert "String" in type_counts
