from dataclasses import FrozenInstanceError, replace
from pathlib import Path
import random
from threading import Event

import polars as pl
import pytest

from parqcel.core import parquet_optimizer as optimizer
from parqcel.core.io import ParquetOperationCancelled, ParquetWriteOptions
from parqcel.core.parquet_optimizer import (
    OptimizationOptions,
    analyze_parquet,
    check_working_budget,
    sortable_columns,
    sorted_frame,
)


def compressible_frame():
    groups = list(range(40)) * 60
    random.Random(314).shuffle(groups)
    return pl.DataFrame(
        {
            "group": groups,
            "payload": [
                f"repeated payload category {group:03d}" * 4 for group in groups
            ],
            "time": pl.Series(
                [1_000_000_001 + group for group in groups], dtype=pl.Datetime("ns")
            ),
        }
    )


def test_actual_full_encodings_determine_verified_winner_with_identical_options(
    tmp_path, monkeypatch
):
    frame = compressible_frame()
    original = frame.clone()
    options = OptimizationOptions(sample_rows=600, max_candidates=8, finalists=2)
    settings_seen = []
    limits_seen = []
    full_verified = []
    original_write = pl.DataFrame.write_parquet
    original_verify = optimizer.verify_parquet
    original_bounded = optimizer.write_parquet_bounded

    def write(self, file, **kwargs):
        settings_seen.append(kwargs)
        return original_write(self, file, **kwargs)

    def verify(expected, path, **kwargs):
        full_verified.append(expected.clone())
        return original_verify(expected, path, **kwargs)

    def bounded(expected, path, **kwargs):
        assert not list(path.parent.iterdir())
        limits_seen.append(kwargs["max_temporary_bytes"])
        return original_bounded(expected, path, **kwargs)

    monkeypatch.setattr(pl.DataFrame, "write_parquet", write)
    monkeypatch.setattr(optimizer, "verify_parquet", verify)
    monkeypatch.setattr(optimizer, "write_parquet_bounded", bounded)
    messages = []
    report = analyze_parquet(frame, options, progress=messages.append)
    assert frame.equals(original) and frame.schema == original.schema
    assert report.row_count == frame.height and report.sample_rows == 600
    assert len(report.candidates) <= 8
    assert report.baseline is report.candidates[0] and report.baseline.keys == ()
    measured = [
        candidate for candidate in report.candidates if candidate.full_bytes is not None
    ]
    assert len(measured) == len(full_verified) == 3
    assert all(verified.height == frame.height for verified in full_verified)
    assert len(settings_seen) == len(report.candidates) + len(measured)
    assert limits_seen == [options.max_temporary_bytes] * len(settings_seen)
    assert all(
        settings == report.write_options.as_kwargs() for settings in settings_seen
    )
    assert report.best.full_bytes == min(candidate.full_bytes for candidate in measured)
    assert report.best.full_bytes < report.baseline.full_bytes
    for candidate in measured:
        path = tmp_path / "independent.parquet"
        original_write(
            sorted_frame(frame, candidate.keys),
            path,
            **report.write_options.as_kwargs(),
        )
        assert path.stat().st_size == candidate.full_bytes
    assert any("Profiling" in message for message in messages)
    assert "verified full outputs" in messages[-1]
    with pytest.raises(FrozenInstanceError):
        report.best = report.baseline


def test_sample_is_representative_deterministic_and_retains_original_order():
    frame = pl.DataFrame(
        {"row": range(10_000), "group": [n % 7 for n in range(10_000)]}
    )
    options = OptimizationOptions(sample_rows=100, seed=10)
    first = optimizer._sample(frame, options)
    assert first.equals(optimizer._sample(frame, options))
    assert first.height == 100 and first["row"].is_sorted()
    assert first["row"].max() > 9000 and first["row"].min() < 1000
    assert not first.equals(optimizer._sample(frame, replace(options, seed=11)))
    first_report = analyze_parquet(
        frame, replace(options, max_candidates=3, finalists=1)
    )
    second_report = analyze_parquet(
        frame, replace(options, max_candidates=3, finalists=1)
    )
    assert [
        (x.keys, x.sample_bytes, x.full_bytes) for x in first_report.candidates
    ] == [(x.keys, x.sample_bytes, x.full_bytes) for x in second_report.candidates]


def test_candidate_search_keeps_high_cardinality_time_numeric_and_preferred_keys():
    frame = pl.DataFrame(
        {
            **{
                f"low{n}": [(row + n) % (n + 2) for row in range(200)] for n in range(5)
            },
            "time": pl.Series(range(200), dtype=pl.Datetime("ns")),
            "number": list(reversed(range(200))),
            "wide": [str(n % 10) * 200 for n in range(200)],
        }
    )
    options = OptimizationOptions(preferred_column="wide")
    keys = optimizer._candidate_keys(frame, options, None)
    assert len(keys) == 12 and keys[0] == () and keys[1] == ("wide",)
    assert ("time",) in keys and ("number",) in keys
    assert any(len(candidate) == 2 for candidate in keys)
    assert len(set(keys)) == len(keys)
    with pytest.raises(ValueError, match="preferred"):
        analyze_parquet(frame, replace(options, preferred_column="missing"))


def test_sort_is_stable_whole_row_nulls_last_and_keeps_native_precision():
    frame = pl.DataFrame(
        {
            "key": [2, None, 1, 1, 2],
            "id": pl.Series([2**64 - n for n in range(1, 6)], dtype=pl.UInt64),
            "time": pl.Series([1, 2, 3, 4, 5], dtype=pl.Datetime("ns")),
            "nested": [[1], [2], [3], [4], [5]],
        }
    )
    result = sorted_frame(frame, ("key",))
    assert result.schema == frame.schema
    assert result["key"].to_list() == [1, 1, 2, 2, None]
    assert result["time"].cast(pl.Int64).to_list() == [3, 4, 1, 5, 2]
    assert result["nested"].to_list() == [[3], [4], [1], [5], [2]]
    assert result["id"].to_list() == [2**64 - n for n in [3, 4, 1, 5, 2]]
    assert sorted_frame(frame, ()).equals(frame)
    assert "nested" not in sortable_columns(frame)
    for invalid in [("missing",), ("nested",), ("key", "key"), "key"]:
        with pytest.raises(ValueError):
            sorted_frame(frame, invalid)


@pytest.mark.parametrize(
    "frame",
    [
        pl.DataFrame(),
        pl.DataFrame(schema={"id": pl.Int64, "text": pl.String}),
        pl.DataFrame({"id": [7], "text": ["one"]}),
        pl.DataFrame({"nested": [[2], [1]]}),
        pl.DataFrame({"constant": [1, 1, 1]}),
    ],
)
def test_empty_singleton_constant_or_no_sortable_columns_use_baseline_only(frame):
    report = analyze_parquet(frame)
    assert len(report.candidates) == 1
    assert report.best == report.baseline
    assert report.best.full_bytes > 0 and report.best.keys == ()


def test_ties_prefer_original_order_and_unmeasured_candidate_cannot_win(monkeypatch):
    frame = pl.DataFrame({"a": [3, 1, 2], "b": [1, 2, 3]})
    monkeypatch.setattr(optimizer, "_measure", lambda *args, **kwargs: 100)
    report = analyze_parquet(frame, OptimizationOptions(max_candidates=4, finalists=1))
    assert len(report.candidates) == 4
    assert sum(candidate.full_bytes is not None for candidate in report.candidates) == 2
    assert report.best == report.baseline


def test_write_and_verification_failures_propagate_and_clean_temporary_files(
    monkeypatch,
):
    frame = pl.DataFrame({"id": [2, 1]})
    paths = []

    def broken_write(frame, path, **kwargs):
        paths.append(Path(path))
        Path(path).write_bytes(b"partial")
        raise OSError("test disk failure")

    monkeypatch.setattr(optimizer, "write_parquet_bounded", broken_write)
    with pytest.raises(OSError, match="test disk failure"):
        analyze_parquet(frame)
    assert paths and all(
        not path.exists() and not path.parent.exists() for path in paths
    )


def test_verification_failure_is_not_downgraded_to_a_sample_recommendation(monkeypatch):
    paths = []

    def bad_verify(frame, path, **kwargs):
        paths.append(Path(path))
        raise ValueError("test values differ")

    monkeypatch.setattr(optimizer, "verify_parquet", bad_verify)
    with pytest.raises(ValueError, match="test values differ"):
        analyze_parquet(pl.DataFrame({"id": [2, 1]}))
    assert paths and all(
        not path.exists() and not path.parent.exists() for path in paths
    )


@pytest.mark.parametrize(
    "stage",
    [
        "Preparing",
        "Profiling",
        "Measuring sample 2",
        "Measuring and verifying full output 2",
    ],
)
def test_cancellation_is_checked_between_stages_and_cleans_outputs(stage, monkeypatch):
    cancelled = Event()
    paths = []
    original_write = optimizer.write_parquet_bounded

    def write(frame, path, **kwargs):
        paths.append(Path(path))
        return original_write(frame, path, **kwargs)

    monkeypatch.setattr(optimizer, "write_parquet_bounded", write)

    def progress(message):
        if message.startswith(stage):
            cancelled.set()

    with pytest.raises(ParquetOperationCancelled):
        analyze_parquet(
            pl.DataFrame({"id": [2, 1]}), cancel=cancelled, progress=progress
        )
    assert all(not path.exists() and not path.parent.exists() for path in paths)


def test_cancellation_after_native_write_never_verifies_or_reports(monkeypatch):
    cancelled = Event()
    paths = []
    original_write = optimizer.write_parquet_bounded

    def write(frame, path, **kwargs):
        paths.append(Path(path))
        size = original_write(frame, path, **kwargs)
        cancelled.set()
        return size

    monkeypatch.setattr(optimizer, "write_parquet_bounded", write)
    with pytest.raises(ParquetOperationCancelled):
        analyze_parquet(pl.DataFrame({"id": [2, 1]}), cancel=cancelled)
    assert all(not path.exists() and not path.parent.exists() for path in paths)


def test_working_and_temporary_preflights_fail_before_sort_or_write(monkeypatch):
    frame = pl.DataFrame({"id": [2, 1]})
    with pytest.raises(MemoryError, match="working memory"):
        analyze_parquet(frame, OptimizationOptions(max_working_bytes=1))
    with pytest.raises(MemoryError, match="working memory"):
        check_working_budget(frame, OptimizationOptions(max_working_bytes=1))
    writes = []
    monkeypatch.setattr(
        optimizer, "write_parquet_bounded", lambda *a, **k: writes.append(a)
    )
    with pytest.raises(OSError, match="temporary"):
        analyze_parquet(frame, OptimizationOptions(max_temporary_bytes=1))
    assert not writes
    monkeypatch.setattr(
        optimizer.shutil, "disk_usage", lambda path: type("Disk", (), {"free": 0})()
    )
    with pytest.raises(OSError, match="free disk"):
        analyze_parquet(frame)
    assert not writes


def test_retained_sample_memory_is_budgeted_and_released_before_full_measurement(
    monkeypatch,
):
    import weakref

    frame = pl.DataFrame({"id": range(200), "category": [n % 4 for n in range(200)]})
    options = OptimizationOptions(sample_rows=30)
    samples = []
    retained = []
    original_sample = optimizer._sample
    original_budget = optimizer.check_working_budget
    original_measure = optimizer._measure

    def sample(*args):
        value = original_sample(*args)
        samples.append(weakref.ref(value))
        return value

    def budget(data, limits, **kwargs):
        retained.append(kwargs.get("retained_bytes", 0))
        return original_budget(data, limits, **kwargs)

    def measure(data, path, limits, cancel, *, verify):
        if verify:
            assert samples[0]() is None
        return original_measure(data, path, limits, cancel, verify=verify)

    monkeypatch.setattr(optimizer, "_sample", sample)
    monkeypatch.setattr(optimizer, "check_working_budget", budget)
    monkeypatch.setattr(optimizer, "_measure", measure)
    analyze_parquet(frame, options)
    assert any(amount > 0 for amount in retained)


def test_actual_encoded_size_is_checked_and_partial_file_removed(monkeypatch):
    paths = []

    def oversized_write(frame, path, **kwargs):
        paths.append(Path(path))
        Path(path).write_bytes(b"x" * 100_001)

    monkeypatch.setattr(optimizer, "write_parquet_bounded", oversized_write)
    with pytest.raises(OSError, match="Encoded Parquet"):
        analyze_parquet(
            pl.DataFrame({"id": [2, 1]}),
            OptimizationOptions(max_temporary_bytes=100_000),
        )
    assert paths and all(
        not path.exists() and not path.parent.exists() for path in paths
    )


def test_unsupported_object_serialization_fails_explicitly():
    frame = pl.DataFrame({"objects": pl.Series([object()], dtype=pl.Object)})
    with pytest.raises(ValueError, match="Object"):
        analyze_parquet(frame)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"sample_rows": 0},
        {"max_candidates": 65},
        {"finalists": 0},
        {"max_working_bytes": -1},
        {"max_temporary_bytes": True},
        {"seed": "random"},
        {"preferred_column": 2},
        {"write_options": None},
    ],
)
def test_options_are_immutable_and_validate_limits(kwargs):
    with pytest.raises(ValueError):
        OptimizationOptions(**kwargs)
    with pytest.raises(FrozenInstanceError):
        OptimizationOptions().seed = 1


def test_custom_write_options_are_retained_in_report():
    write_options = ParquetWriteOptions(compression_level=1, row_group_size=2)
    report = analyze_parquet(
        pl.DataFrame({"value": [1, 2, 3]}),
        OptimizationOptions(max_candidates=1, write_options=write_options),
    )
    assert report.write_options == write_options
    assert report.best.keys == ()
