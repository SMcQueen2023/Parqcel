from datetime import date, datetime, time, timezone

import polars as pl
import pytest

from parqcel.core.values import is_editable_dtype, parse_cell_value


@pytest.mark.parametrize(
    "dtype",
    [
        pl.Int8,
        pl.Int16,
        pl.Int32,
        pl.Int64,
        pl.Int128,
        pl.UInt8,
        pl.UInt16,
        pl.UInt32,
        pl.UInt64,
    ],
)
def test_integer_types_and_rejected_decimal(dtype):
    assert parse_cell_value("12", dtype) == 12
    with pytest.raises(ValueError):
        parse_cell_value("12.5", dtype)


@pytest.mark.parametrize(
    "dtype,value", [(pl.Int8, "128"), (pl.UInt8, "-1"), (pl.UInt64, str(2**64))]
)
def test_integer_overflow_is_rejected(dtype, value):
    with pytest.raises(ValueError):
        parse_cell_value(value, dtype)


@pytest.mark.parametrize(
    "dtype,value,expected",
    [
        (pl.UInt64, str(2**63 + 1), 2**63 + 1),
        (pl.Float32, "1.25", 1.25),
        (pl.Float64, "-1.25", -1.25),
        (pl.Boolean, "false", False),
        (pl.Boolean, "TRUE", True),
        (pl.Date, "2024-01-31", date(2024, 1, 31)),
        (pl.Datetime("us"), "2024-01-31T12:01:02", datetime(2024, 1, 31, 12, 1, 2)),
        (pl.Time, "12:01:02.123456", time(12, 1, 2, 123456)),
        (pl.String, "  text  ", "  text  "),
        (pl.String, "", ""),
        (pl.Int64, "", None),
        (pl.Null, "", None),
        (pl.String, None, None),
    ],
)
def test_supported_values(dtype, value, expected):
    assert parse_cell_value(value, dtype) == expected


@pytest.mark.parametrize(
    "dtype,value",
    [
        (pl.Boolean, "truthy"),
        (pl.Date, "2024-02-30"),
        (pl.Datetime("ns"), "2024-01-01T00:00:00.123456789"),
        (pl.Datetime("us", "UTC"), "2024-01-01T00:00:00"),
        (pl.Datetime("us"), "2024-01-01T00:00:00+00:00"),
        (pl.Datetime("ms"), "2024-01-01T00:00:00.123456"),
        (pl.Time, "12:00:00+02:00"),
        (pl.Float32, "1e100"),
        (pl.Null, "a"),
        (pl.List(pl.Int64), "[1]"),
    ],
)
def test_invalid_values_do_not_coerce(dtype, value):
    with pytest.raises(ValueError):
        parse_cell_value(value, dtype)


def test_timezone_value_preserves_instant_and_column_zone():
    parsed = parse_cell_value("2024-01-01T01:00:00+01:00", pl.Datetime("us", "UTC"))
    assert parsed.astimezone(timezone.utc).hour == 0
    series = pl.Series([parsed], dtype=pl.Datetime("us", "UTC"))
    assert series.cast(pl.Int64)[0] == 1704067200000000
    assert not is_editable_dtype(pl.List(pl.Int64))
