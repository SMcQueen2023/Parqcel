from dataclasses import FrozenInstanceError
from decimal import Decimal
import os
from threading import Event
from types import SimpleNamespace
import weakref

import polars as pl
import pytest

from parqcel.core import io


def _rich_frame():
    return pl.DataFrame(
        {
            "unsigned": pl.Series([2**64 - 1, None, 0], dtype=pl.UInt64),
            "floats": [float("nan"), float("inf"), -0.0],
            "ns": pl.Series([1700000000000000001, None, -1]).cast(pl.Datetime("ns")),
            "zoned": pl.Series([1700000000000000001, None, -1]).cast(
                pl.Datetime("ns", "America/Chicago")
            ),
            "duration": pl.Series([1, None, -1]).cast(pl.Duration("ns")),
            "decimal": pl.Series(
                [Decimal("123456.7891"), None, Decimal("-0.0001")],
                dtype=pl.Decimal(15, 4),
            ),
            "list": pl.Series([[1, None], None, []], dtype=pl.List(pl.Int64)),
            "array": pl.Series([[1, 2], None, [3, 4]], dtype=pl.Array(pl.Int32, 2)),
            "struct": pl.Series(
                [{"s": "a", "f": float("nan")}, None, {"s": None, "f": 1.0}],
                dtype=pl.Struct({"s": pl.String, "f": pl.Float64}),
            ),
            "binary": [b"\x00\xff", None, b""],
            "null": pl.Series([None] * 3, dtype=pl.Null),
            "category": pl.Series(["z", None, "a"], dtype=pl.Categorical),
            "enum": pl.Series(["a", None, "b"], dtype=pl.Enum(["a", "b", "unused"])),
        }
    )


@pytest.mark.parametrize("empty", [False, True])
@pytest.mark.parametrize("batch_rows", [1, 2, 65536])
def test_verified_export_preserves_full_schema_values_and_column_order(
    tmp_path, empty, batch_rows
):
    frame = _rich_frame()
    if empty:
        frame = frame.head(0)
    path = tmp_path / "data[verified].parquet"
    size = io.write_parquet_verified_atomic(
        frame, path, max_temporary_bytes=1024**2, verification_batch_rows=batch_rows
    )
    restored = pl.read_parquet(path, glob=False)
    assert restored.columns == frame.columns
    assert restored.schema == frame.schema
    assert restored.shape == frame.shape
    if not empty:
        assert restored.equals(frame)
    assert size == path.stat().st_size
    assert io.verify_parquet(frame, path) == size
    assert list(tmp_path.iterdir()) == [path]


def test_options_are_immutable_and_native_writer_settings_are_explicit():
    options = io.ParquetWriteOptions()
    assert options.as_kwargs() == {
        "compression": "zstd",
        "compression_level": 3,
        "statistics": True,
        "row_group_size": 131072,
        "data_page_size": 1048576,
        "use_pyarrow": False,
    }
    with pytest.raises(FrozenInstanceError):
        options.compression = "snappy"


def test_verified_writer_matches_candidate_measurement_bytes(tmp_path):
    frame = _rich_frame()
    measured = tmp_path / "measured.parquet"
    exported = tmp_path / "exported.parquet"
    frame.write_parquet(measured, **io.DEFAULT_PARQUET_OPTIONS.as_kwargs())
    io.write_parquet_verified_atomic(frame, exported)
    assert exported.read_bytes() == measured.read_bytes()


def test_bounded_candidate_writer_matches_native_output_without_overwriting(tmp_path):
    frame = _rich_frame()
    direct = tmp_path / "direct.parquet"
    measured = tmp_path / "measured.parquet"
    frame.write_parquet(direct, **io.DEFAULT_PARQUET_OPTIONS.as_kwargs())
    size = io.write_parquet_bounded(frame, measured, max_temporary_bytes=1024**2)
    assert size == measured.stat().st_size
    assert measured.read_bytes() == direct.read_bytes()
    with pytest.raises(FileExistsError):
        io.write_parquet_bounded(pl.DataFrame({"changed": [1]}), measured)
    assert measured.read_bytes() == direct.read_bytes()


@pytest.mark.parametrize("cancelled", [False, True])
def test_bounded_candidate_writer_cleans_failed_output(tmp_path, cancelled):
    path = tmp_path / "candidate.parquet"
    cancel = Event()
    if cancelled:
        cancel.set()
    with pytest.raises((ValueError, io.ParquetOperationCancelled)):
        io.write_parquet_bounded(
            pl.DataFrame({"a": [1, 2]}), path, max_temporary_bytes=8, cancel=cancel
        )
    assert not path.exists()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"compression": "unknown"},
        {"compression_level": True},
        {"compression_level": 23},
        {"compression": "snappy"},
        {"statistics": "full"},
        {"row_group_size": 0},
        {"data_page_size": -1},
    ],
)
def test_invalid_writer_options_are_rejected(kwargs):
    with pytest.raises(ValueError):
        io.ParquetWriteOptions(**kwargs)


@pytest.mark.parametrize("codec", ["snappy", "lz4", "uncompressed", "gzip", "brotli"])
def test_supported_alternative_codecs_roundtrip(tmp_path, codec):
    io.write_parquet_verified_atomic(
        pl.DataFrame({"a": [1, 2]}),
        tmp_path / "result.parquet",
        options=io.ParquetWriteOptions(compression=codec, compression_level=None),
    )


@pytest.mark.parametrize(
    "change", ["order", "columns", "dtype", "float", "nested", "category", "row_count"]
)
def test_verification_rejects_changed_data_and_preserves_destination(
    tmp_path, monkeypatch, change
):
    frame = _rich_frame()
    path = tmp_path / "existing.parquet"
    path.write_bytes(b"existing file")
    changed = {
        "order": frame.reverse(),
        "columns": frame.select(list(reversed(frame.columns))),
        "dtype": frame.with_columns(pl.col("unsigned").cast(pl.Float64)),
        "float": frame.with_columns(
            pl.Series("floats", [float("nan"), float("inf"), 1e-14])
        ),
        "nested": frame.with_columns(
            pl.Series("list", [[2, None], None, []], dtype=pl.List(pl.Int64))
        ),
        "category": frame.with_columns(pl.col("category").cast(pl.String)),
        "row_count": frame.head(2),
    }[change]
    original_write = pl.DataFrame.write_parquet

    def write_changed(self, *args, **kwargs):
        return original_write(changed, *args, **kwargs)

    monkeypatch.setattr(pl.DataFrame, "write_parquet", write_changed)
    with pytest.raises(io.ParquetVerificationError):
        io.write_parquet_verified_atomic(frame, path)
    assert path.read_bytes() == b"existing file"
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize(
    "stage", ["before", "during_write", "after_write", "after_read", "before_publish"]
)
def test_cancellation_at_each_export_phase_preserves_destination_and_cleans_temp(
    tmp_path, monkeypatch, stage
):
    frame = pl.DataFrame({"a": [1, 2]})
    path = tmp_path / "existing.parquet"
    path.write_bytes(b"existing file")
    cancel = Event()
    if stage == "before":
        cancel.set()
    elif stage in {"during_write", "after_write"}:
        original_write = pl.DataFrame.write_parquet

        def write(self, *args, **kwargs):
            if stage == "during_write":
                cancel.set()
            original_write(self, *args, **kwargs)
            cancel.set()

        monkeypatch.setattr(pl.DataFrame, "write_parquet", write)
    elif stage == "after_read":
        original_collect = pl.LazyFrame.collect

        def collect(self, *args, **kwargs):
            result = original_collect(self, *args, **kwargs)
            if result.columns == frame.columns:
                cancel.set()
            return result

        monkeypatch.setattr(pl.LazyFrame, "collect", collect)
    else:
        original_check = io._check_destination
        checks = 0

        def check(*args, **kwargs):
            nonlocal checks
            original_check(*args, **kwargs)
            checks += 1
            if checks == 2:
                cancel.set()

        monkeypatch.setattr(io, "_check_destination", check)
    with pytest.raises(io.ParquetOperationCancelled):
        io.write_parquet_verified_atomic(frame, path, cancel=cancel)
    assert path.read_bytes() == b"existing file"
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize(
    "failure", ["write", "replace", "size", "disk_preflight", "disk_write"]
)
def test_resource_or_io_failure_leaves_original_and_no_temporary_files(
    tmp_path, monkeypatch, failure
):
    path = tmp_path / "existing.parquet"
    path.write_bytes(b"original")
    frame = pl.DataFrame({"a": [1, 2]})
    kwargs = {}
    if failure == "write":

        def fail(self, file, **kwargs):
            file.write(b"partial")
            raise OSError("simulated write failure")

        monkeypatch.setattr(pl.DataFrame, "write_parquet", fail)
    elif failure == "replace":

        def fail(*args):
            raise OSError("simulated replace failure")

        monkeypatch.setattr(io.os, "replace", fail)
    elif failure == "size":
        kwargs["max_temporary_bytes"] = 8
    else:
        free_values = iter([0] if failure == "disk_preflight" else [1024**3, 0])
        monkeypatch.setattr(
            io.shutil, "disk_usage", lambda _: SimpleNamespace(free=next(free_values))
        )
    with pytest.raises((OSError, ValueError)):
        io.write_parquet_verified_atomic(frame, path, **kwargs)
    assert path.read_bytes() == b"original"
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize("hardlink", [False, True])
def test_active_source_and_alias_cannot_be_overwritten(tmp_path, hardlink):
    source = tmp_path / "source.parquet"
    source.write_bytes(b"source")
    destination = source
    if hardlink:
        destination = tmp_path / "alias.parquet"
        os.link(source, destination)
    with pytest.raises(ValueError, match="active source"):
        io.write_parquet_verified_atomic(
            pl.DataFrame({"a": [1]}), destination, protected_paths=[source]
        )
    assert source.read_bytes() == destination.read_bytes() == b"source"
    assert len(list(tmp_path.iterdir())) == (2 if hardlink else 1)


def test_unsupported_object_dtype_fails_without_replacing_original(tmp_path):
    path = tmp_path / "existing.parquet"
    path.write_bytes(b"original")
    frame = pl.DataFrame({"object": pl.Series([object()], dtype=pl.Object)})
    with pytest.raises(pl.exceptions.PolarsError):
        io.write_parquet_verified_atomic(frame, path)
    assert path.read_bytes() == b"original"
    assert list(tmp_path.iterdir()) == [path]


def test_source_alias_created_during_export_is_rechecked_before_publish(
    tmp_path, monkeypatch
):
    source = tmp_path / "source.parquet"
    source.write_bytes(b"source")
    destination = tmp_path / "export.parquet"
    real_verify = io.verify_parquet

    def verify(*args, **kwargs):
        size = real_verify(*args, **kwargs)
        os.link(source, destination)
        return size

    monkeypatch.setattr(io, "verify_parquet", verify)
    with pytest.raises(ValueError, match="active source"):
        io.write_parquet_verified_atomic(
            pl.DataFrame({"a": [1]}), destination, protected_paths=[source]
        )
    assert source.read_bytes() == destination.read_bytes() == b"source"
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "export.parquet",
        "source.parquet",
    ]


def test_verification_reads_bounded_batches_without_retaining_previous_or_eager_read(
    tmp_path, monkeypatch
):
    batch_rows = io.DEFAULT_VERIFICATION_BATCH_ROWS
    frame = pl.DataFrame({"id": range(2 * batch_rows + 17), "value": 1.25})
    path = tmp_path / "wide[batch].parquet"
    frame.write_parquet(path, row_group_size=batch_rows)
    original_collect = pl.LazyFrame.collect
    previous = None
    batch_sizes = []

    def collect(self, *args, **kwargs):
        nonlocal previous
        assert previous is None or previous() is None, "Prior batch still retained"
        result = original_collect(self, *args, **kwargs)
        if result.columns == frame.columns:
            batch_sizes.append(result.height)
            previous = weakref.ref(result)
        return result

    def forbidden(*args, **kwargs):
        raise AssertionError("Verification must not use the eager full-file reader")

    monkeypatch.setattr(pl, "read_parquet", forbidden)
    monkeypatch.setattr(pl.LazyFrame, "collect", collect)
    assert io.verify_parquet(frame, path) == path.stat().st_size
    assert batch_sizes == [batch_rows, batch_rows, 17]
    assert previous() is None


@pytest.mark.parametrize("changed_row", [0, 3, 4, 7, 8, 10])
def test_verification_detects_exact_changes_at_and_around_batch_boundaries(
    tmp_path, changed_row
):
    frame = pl.DataFrame(
        {
            "id": range(11),
            "time": pl.Series(range(11), dtype=pl.Datetime("ns")),
            "value": [1.0] * 11,
        }
    )
    # An alteration well below approximate floating-point comparison tolerances
    # must still be rejected, including the final partial batch.
    altered = frame.with_columns(
        pl.when(pl.col("id") == changed_row)
        .then(1.0 + 1e-14)
        .otherwise(pl.col("value"))
        .alias("value")
    )
    path = tmp_path / "altered.parquet"
    altered.write_parquet(path, row_group_size=3)
    with pytest.raises(io.ParquetVerificationError, match="ordered values"):
        io.verify_parquet(frame, path, verification_batch_rows=4)


def test_verification_rejects_row_reordering_across_batch_boundary(tmp_path):
    frame = pl.DataFrame({"id": range(9), "nested": [[i, None] for i in range(9)]})
    path = tmp_path / "swapped.parquet"
    frame[[0, 1, 2, 4, 3, 5, 6, 7, 8]].write_parquet(path, row_group_size=3)
    with pytest.raises(io.ParquetVerificationError, match="ordered values"):
        io.verify_parquet(frame, path, verification_batch_rows=4)


def test_batch_cancellation_preserves_existing_destination_and_stops_later_reads(
    tmp_path, monkeypatch
):
    frame = pl.DataFrame({"id": range(11)})
    path = tmp_path / "existing.parquet"
    path.write_bytes(b"original")
    cancel = Event()
    original_collect = pl.LazyFrame.collect
    read_batches = []

    def collect(self, *args, **kwargs):
        result = original_collect(self, *args, **kwargs)
        if result.columns == frame.columns:
            read_batches.append(result["id"].to_list())
            if len(read_batches) == 2:
                cancel.set()
        return result

    monkeypatch.setattr(pl.LazyFrame, "collect", collect)
    with pytest.raises(io.ParquetOperationCancelled):
        io.write_parquet_verified_atomic(
            frame, path, cancel=cancel, verification_batch_rows=4
        )
    assert read_batches == [[0, 1, 2, 3], [4, 5, 6, 7]]
    assert path.read_bytes() == b"original"
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize("batch_rows", [0, -1, True, 1.5, "4"])
def test_invalid_verification_batch_size_fails_before_scan_or_write(
    tmp_path, monkeypatch, batch_rows
):
    frame = pl.DataFrame({"id": [1]})
    path = tmp_path / "existing.parquet"
    path.write_bytes(b"original")

    def forbidden(*args, **kwargs):
        raise AssertionError("Invalid verification settings must fail before I/O")

    monkeypatch.setattr(pl.DataFrame, "write_parquet", forbidden)
    monkeypatch.setattr(pl, "scan_parquet", forbidden)
    with pytest.raises(ValueError, match="Verification batch rows"):
        io.verify_parquet(frame, path, verification_batch_rows=batch_rows)
    with pytest.raises(ValueError, match="Verification batch rows"):
        io.write_parquet_verified_atomic(
            frame, path, verification_batch_rows=batch_rows
        )
    assert path.read_bytes() == b"original"
    assert list(tmp_path.iterdir()) == [path]
