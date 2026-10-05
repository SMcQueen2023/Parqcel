import polars as pl
import pytest
from polars.testing import assert_frame_equal

from parqcel.core.io import read_dataset, write_dataset_atomic
from parqcel.core.operations import convert_column


def test_parquet_atomic_roundtrip_preserves_schema(tmp_path):
    df = pl.DataFrame(
        {"flag": [True, None], "id": [2**63 + 1, None]},
        schema={"flag": pl.Boolean, "id": pl.UInt64},
    )
    path = tmp_path / "data.PARQUET"
    write_dataset_atomic(df, path)
    assert_frame_equal(read_dataset(path), df)
    assert list(tmp_path.iterdir()) == [path]


def test_failed_save_keeps_destination_and_cleans_temporary(tmp_path, monkeypatch):
    path = tmp_path / "data.parquet"
    original = pl.DataFrame({"id": [1]})
    write_dataset_atomic(original, path)

    def fail(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(pl.DataFrame, "write_parquet", fail)
    with pytest.raises(OSError, match="disk full"):
        write_dataset_atomic(pl.DataFrame({"id": [2]}), path)
    assert_frame_equal(read_dataset(path), original)
    assert list(tmp_path.iterdir()) == [path]


def test_csv_typing_is_explicit(tmp_path):
    path = tmp_path / "data.csv"
    path.write_text("id\n001\n002\n", encoding="utf-8")
    assert read_dataset(path)["id"].to_list() == ["001", "002"]
    assert read_dataset(path, csv_types="infer")["id"].to_list() == [1, 2]


def test_convert_nullable_dates_preserves_nulls():
    result = convert_column(
        pl.DataFrame({"date": ["2024-01-02", None]}), "date", "Date"
    )
    assert result.schema["date"] == pl.Date
    assert result["date"].null_count() == 1


def test_invalid_date_conversion_is_not_silently_applied():
    with pytest.raises((ValueError, pl.exceptions.PolarsError)):
        convert_column(pl.DataFrame({"date": ["not a date"]}), "date", "Datetime")


def test_boolean_conversion_rejects_unknown_strings():
    result = convert_column(
        pl.DataFrame({"flag": ["true", "0", None]}), "flag", "Boolean"
    )
    assert result["flag"].to_list() == [True, False, None]
    with pytest.raises(pl.exceptions.PolarsError):
        convert_column(pl.DataFrame({"flag": ["unknown"]}), "flag", "Boolean")
