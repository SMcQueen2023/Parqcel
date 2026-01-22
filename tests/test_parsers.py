import datetime

from logic.parsers import (
    detect_format_for_samples,
    parse_single_date,
    parse_single_datetime,
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
