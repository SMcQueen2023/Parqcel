"""Measure bounded Parquet sort candidates with identical native writer settings.

The search is a heuristic, not a global optimum. Only full outputs that have been
reread and verified may become the recommendation. The input is never changed.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
import random
import shutil
import tempfile
from threading import Event
from time import perf_counter

import polars as pl
from polars.datatypes import DataTypeClass

from .io import (
    DEFAULT_PARQUET_OPTIONS,
    ParquetOperationCancelled,
    ParquetWriteOptions,
    verify_parquet,
    write_parquet_bounded,
)


@dataclass(frozen=True)
class OptimizationOptions:
    sample_rows: int = 20_000
    max_candidates: int = 12
    finalists: int = 2
    max_working_bytes: int = 512 * 1024 * 1024
    max_temporary_bytes: int = 1024 * 1024 * 1024
    seed: int = 1729
    preferred_column: str | None = None
    write_options: ParquetWriteOptions = DEFAULT_PARQUET_OPTIONS

    def __post_init__(self) -> None:
        for name in (
            "sample_rows",
            "max_candidates",
            "finalists",
            "max_working_bytes",
            "max_temporary_bytes",
        ):
            value = getattr(self, name)
            if type(value) is not int or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if self.max_candidates > 64:
            raise ValueError("Measure at most 64 candidates in one optimization")
        if type(self.seed) is not int:
            raise ValueError("The sampling seed must be an integer")
        if self.preferred_column is not None and not isinstance(
            self.preferred_column, str
        ):
            raise ValueError("The preferred column must be a column name")
        if not isinstance(self.write_options, ParquetWriteOptions):
            raise ValueError("Supply validated Parquet write options")


@dataclass(frozen=True)
class CandidateResult:
    keys: tuple[str, ...]
    sample_bytes: int
    full_bytes: int | None
    seconds: float


@dataclass(frozen=True)
class OptimizationReport:
    candidates: tuple[CandidateResult, ...]
    baseline: CandidateResult
    best: CandidateResult
    row_count: int
    sample_rows: int
    write_options: ParquetWriteOptions


@dataclass(frozen=True)
class _ColumnProfile:
    name: str
    cardinality: int
    run_ratio: float
    mean_width: float
    numeric_or_temporal: bool
    position: int


def sortable_columns(frame: pl.DataFrame) -> tuple[str, ...]:
    """Scalar columns whose native ascending ordering this search supports."""
    return tuple(
        name
        for name, dtype in frame.schema.items()
        if dtype.is_numeric()
        or dtype.is_temporal()
        or dtype in (pl.String, pl.Boolean, pl.Categorical, pl.Enum)
    )


def sorted_frame(frame: pl.DataFrame, keys: Sequence[str]) -> pl.DataFrame:
    """Stable, whole-row ascending sort with nulls last; empty keys mean a clone."""
    if isinstance(keys, (str, bytes)):
        raise ValueError("Supply sort keys as a sequence of column names")
    names = tuple(keys)
    eligible = sortable_columns(frame)
    if any(not isinstance(name, str) or name not in eligible for name in names):
        raise ValueError("Sort keys must name supported scalar columns in the dataset")
    if len(set(names)) != len(names):
        raise ValueError("Sort keys must be unique")
    if not names:
        return frame.clone()
    return frame.sort(
        list(names), descending=False, nulls_last=True, maintain_order=True
    )


def _check_cancel(cancel: Event | None) -> None:
    if cancel is not None and cancel.is_set():
        raise ParquetOperationCancelled("Parquet optimization cancelled")


def _contains_object(dtype: pl.DataType | DataTypeClass) -> bool:
    if dtype == pl.Object:
        return True
    if isinstance(dtype, (pl.List, pl.Array)):
        return _contains_object(dtype.inner)
    if isinstance(dtype, pl.Struct):
        return any(_contains_object(field.dtype) for field in dtype.fields)
    return False


def check_working_budget(
    frame: pl.DataFrame,
    options: OptimizationOptions,
    *,
    sorting: bool = True,
    retained_bytes: int = 0,
) -> None:
    """Check estimated additional sort/write/verify memory before allocating it."""
    # Additional memory beyond the caller's input: sort copy/indices, encoded
    # output buffers or verification reread, and a codec/metadata allowance.
    # Include a sampled input retained by the analyzer separately. Native
    # allocator and row-group internals make this a best-effort estimate.
    if type(retained_bytes) is not int or retained_bytes < 0:
        raise ValueError("Retained working bytes must be non-negative")
    estimate = frame.estimated_size() * (3 if sorting else 2) + retained_bytes
    if sorting:
        estimate += frame.height * 16
    estimate += max(4 * 1024 * 1024, frame.width * 4096)
    if estimate > options.max_working_bytes:
        raise MemoryError(
            f"Estimated additional working memory is {estimate:,} bytes, above the "
            f"{options.max_working_bytes:,}-byte budget. Increase the working budget "
            "or optimize a smaller dataset."
        )


def _sample(frame: pl.DataFrame, options: OptimizationOptions) -> pl.DataFrame:
    count = min(frame.height, options.sample_rows)
    if count == frame.height:
        return frame.clone()
    # Sampling uniformly across the complete row range avoids a head-only bias.
    # Sorting the indices retains original relative order for the baseline.
    indices = sorted(random.Random(options.seed).sample(range(frame.height), count))
    return frame[indices]


def _candidate_keys(
    sample: pl.DataFrame, options: OptimizationOptions, cancel: Event | None
) -> tuple[tuple[str, ...], ...]:
    if sample.height < 2 or options.max_candidates == 1:
        return ((),)
    profiles: list[_ColumnProfile] = []
    for position, name in enumerate(sortable_columns(sample)):
        _check_cancel(cancel)
        series = sample[name]
        cardinality = series.n_unique()
        if cardinality <= 1:
            continue
        runs = int(series.ne_missing(series.shift(1)).sum() or 0)
        width = 0.0
        if series.dtype in (pl.String, pl.Categorical, pl.Enum):
            mean_width = series.cast(pl.String).str.len_bytes().mean()
            if isinstance(mean_width, (int, float)):
                width = float(mean_width)
        profiles.append(
            _ColumnProfile(
                name,
                cardinality,
                runs / sample.height,
                width,
                series.dtype.is_numeric() or series.dtype.is_temporal(),
                position,
            )
        )
        _check_cancel(cancel)
    if not profiles:
        return ((),)
    low_cardinality = sorted(
        profiles, key=lambda p: (p.cardinality, -p.run_ratio, -p.mean_width, p.position)
    )
    high_cardinality = sorted(
        (p for p in profiles if p.numeric_or_temporal),
        key=lambda p: (-p.cardinality, -p.run_ratio, p.position),
    )
    wide_strings = sorted(
        (p for p in profiles if p.mean_width),
        key=lambda p: (-p.mean_width, -p.run_ratio, p.cardinality, p.position),
    )
    singles: list[str] = []
    available = {p.name for p in profiles}
    preferred = options.preferred_column
    if preferred is not None and preferred in available:
        singles.append(preferred)
    # Reserve early candidates for both repeating dimensions and high-cardinality
    # numeric/time columns, whose delta encodings can benefit from sorting.
    for profile in (
        low_cardinality[:2] + high_cardinality[:2] + wide_strings[:1] + low_cardinality
    ):
        if profile.name not in singles:
            singles.append(profile.name)
    candidates: list[tuple[str, ...]] = [()]

    def add(keys: tuple[str, ...]) -> None:
        if keys not in candidates and len(candidates) < options.max_candidates:
            candidates.append(keys)

    # At most half the non-baseline budget goes to singles when pairs exist.
    single_limit = min(len(singles), max(1, (options.max_candidates - 1 + 1) // 2))
    for name in singles[:single_limit]:
        add((name,))
    first_keys = (
        [preferred] if preferred is not None and preferred in available else []
    ) + [p.name for p in low_cardinality[:3]]
    second_keys = (
        [p.name for p in high_cardinality] + [p.name for p in wide_strings] + singles
    )
    for first in first_keys:
        for second in second_keys:
            if first != second:
                add((first, second))
    for name in singles[single_limit:]:
        add((name,))
    return tuple(candidates)


def _measure(
    frame: pl.DataFrame,
    path: Path,
    options: OptimizationOptions,
    cancel: Event | None,
    *,
    verify: bool,
) -> int:
    _check_cancel(cancel)
    # Only one encoded file is retained at a time. Budget the raw data plus
    # metadata before writing; compressed output is checked again afterwards.
    estimate = max(65_536, frame.estimated_size() * 2 + frame.width * 4096)
    if estimate > options.max_temporary_bytes:
        raise OSError(
            f"Estimated temporary Parquet size ({estimate:,} bytes) exceeds the "
            f"{options.max_temporary_bytes:,}-byte budget. Increase the temporary "
            "budget or optimize a smaller dataset."
        )
    if estimate > shutil.disk_usage(path.parent).free:
        raise OSError("Insufficient free disk space for the temporary Parquet output")
    try:
        write_parquet_bounded(
            frame,
            path,
            options=options.write_options,
            cancel=cancel,
            max_temporary_bytes=options.max_temporary_bytes,
        )
        _check_cancel(cancel)
        size = path.stat().st_size
        if size > options.max_temporary_bytes:
            raise OSError(
                "Encoded Parquet output exceeded the temporary-file budget. "
                "Increase the temporary budget or optimize a smaller dataset."
            )
        if verify:
            verified_size = verify_parquet(frame, path, cancel=cancel)
            if verified_size != size:
                raise OSError("The measured Parquet file changed during verification")
        _check_cancel(cancel)
        return size
    finally:
        path.unlink(missing_ok=True)


def analyze_parquet(
    frame: pl.DataFrame,
    options: OptimizationOptions = OptimizationOptions(),
    *,
    cancel: Event | None = None,
    progress: Callable[[str], None] | None = None,
) -> OptimizationReport:
    """Measure sample candidates, then verify baseline and top full finalists.

    Runs sequentially. Cancellation is cooperative between native operations;
    it cannot interrupt an in-progress Polars sort/write/read. Working-memory
    and disk estimates are conservative best-effort checks, not allocator caps.
    Candidate byte counts always use the report's identical write options.
    """
    if not isinstance(frame, pl.DataFrame):
        raise TypeError("Supply a Polars DataFrame")
    if not isinstance(options, OptimizationOptions):
        raise TypeError("Supply validated optimization options")
    _check_cancel(cancel)
    if any(_contains_object(dtype) for dtype in frame.dtypes):
        raise ValueError(
            "Parquet cannot serialize Object columns; convert them before optimizing"
        )
    if (
        options.preferred_column is not None
        and options.preferred_column not in sortable_columns(frame)
    ):
        raise ValueError("The preferred column must be a supported scalar sort column")

    def update(message: str) -> None:
        _check_cancel(cancel)
        if progress is not None:
            progress(message)
        _check_cancel(cancel)

    update("Preparing a deterministic representative sample")
    check_working_budget(frame, options, sorting=False)
    sample = _sample(frame, options)
    retained_sample_bytes = (
        int(sample.estimated_size()) if sample.height < frame.height else 0
    )
    check_working_budget(
        sample, options, sorting=True, retained_bytes=retained_sample_bytes
    )
    update(f"Profiling {sample.height:,} sampled rows")
    keys = _candidate_keys(sample, options, cancel)
    if len(keys) > 1:
        check_working_budget(frame, options, sorting=True)
    results: list[CandidateResult] = []
    sample_count = sample.height
    with tempfile.TemporaryDirectory(prefix="parqcel-optimize-") as directory:
        path = Path(directory) / "candidate.parquet"
        for number, candidate in enumerate(keys, start=1):
            label = ", ".join(candidate) if candidate else "original order"
            update(f"Measuring sample {number}/{len(keys)}: {label}")
            start = perf_counter()
            prepared = sorted_frame(sample, candidate)
            _check_cancel(cancel)
            size = _measure(prepared, path, options, cancel, verify=False)
            results.append(
                CandidateResult(candidate, size, None, perf_counter() - start)
            )
            del prepared
        del sample
        finalists = sorted(
            results[1:], key=lambda item: (item.sample_bytes, item.keys)
        )[: options.finalists]
        measured_keys = [()] + [item.keys for item in finalists]
        for number, candidate in enumerate(measured_keys, start=1):
            label = ", ".join(candidate) if candidate else "original order"
            update(
                f"Measuring and verifying full output {number}/{len(measured_keys)}: {label}"
            )
            check_working_budget(frame, options, sorting=bool(candidate))
            start = perf_counter()
            prepared = sorted_frame(frame, candidate)
            _check_cancel(cancel)
            size = _measure(prepared, path, options, cancel, verify=True)
            for index, result in enumerate(results):
                if result.keys == candidate:
                    results[index] = replace(
                        result,
                        full_bytes=size,
                        seconds=result.seconds + perf_counter() - start,
                    )
                    break
            del prepared
    baseline = results[0]
    measured = [item for item in results if item.full_bytes is not None]
    best = min(measured, key=lambda item: (item.full_bytes or 0, bool(item.keys)))
    update(
        "Optimization measurements complete; recommendation uses verified full outputs"
    )
    return OptimizationReport(
        tuple(results),
        baseline,
        best,
        frame.height,
        sample_count,
        options.write_options,
    )
