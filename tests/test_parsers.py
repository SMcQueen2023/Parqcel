import datetime
import polars as pl
import pytest

from logic.parsers import (
    detect_format_for_samples,
    parse_single_date,
    parse_single_datetime,
    convert_series_to_datetime,
)


def test_detect_format_for_samples():
    values = ["2024-01-31", "2025-12-01", "2023-06-15"]
    fmt = detect_format_for_samples(values, ["%Y-%m-%d", "%m/%d/%Y"])
    assert fmt == "%Y-%m-%d"


def test_parse_single_date_and_datetime():
    d = parse_single_date("01/31/2024")
    assert isinstance(d, datetime.date)
    assert d == datetime.date(2024, 1, 31)

    dt = parse_single_datetime("2024-01-31T13:45:00")
    assert isinstance(dt, datetime.datetime)
    assert dt.year == 2024 and dt.hour == 13


def test_nullable_date_fast_path():
    result = convert_series_to_datetime(
        pl.Series("d", ["2024-01-02", None]), allow_fallback=False
    )
    assert result.dtype == pl.Datetime
    assert result.null_count() == 1


def test_disabled_fallback_reports_conversion_failure():
    with pytest.raises(ValueError, match="Could not fully parse"):
        convert_series_to_datetime(pl.Series("d", ["invalid"]), allow_fallback=False)
