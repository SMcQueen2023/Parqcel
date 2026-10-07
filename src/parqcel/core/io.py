"""Dataset I/O shared by desktop and command-line workflows."""

from __future__ import annotations

import os
from collections.abc import Iterable
from concurrent.futures import CancelledError
from dataclasses import dataclass
import errno
from pathlib import Path
import shutil
import tempfile
from threading import Event
from typing import Any, BinaryIO, IO, Literal, cast

import polars as pl

CsvTypes = Literal["strings", "infer"]


@dataclass(frozen=True)
class ParquetWriteOptions:
    """Explicit native-writer settings shared by analysis and verified export."""

    compression: str = "zstd"
    compression_level: int | None = 3
    statistics: bool = True
    row_group_size: int = 131072
    data_page_size: int = 1024 * 1024

    def __post_init__(self) -> None:
        levels = {"zstd": (1, 22), "gzip": (0, 9), "brotli": (0, 11)}
        if self.compression not in {*levels, "snappy", "lz4", "uncompressed"}:
            raise ValueError("Unsupported Parquet compression codec")
        if self.compression_level is not None:
            if type(self.compression_level) is not int:
                raise ValueError("Compression level must be an integer or None")
            bounds = levels.get(self.compression)
            if bounds is None or not bounds[0] <= self.compression_level <= bounds[1]:
                raise ValueError("Compression level is invalid for the selected codec")
        if type(self.statistics) is not bool:
            raise ValueError("Statistics must be a boolean")
        for value in (self.row_group_size, self.data_page_size):
            if type(value) is not int or value <= 0:
                raise ValueError(
                    "Parquet row-group and page sizes must be positive integers"
                )

    def as_kwargs(self) -> dict[str, Any]:
        return {
            "compression": self.compression,
            "compression_level": self.compression_level,
            "statistics": self.statistics,
            "row_group_size": self.row_group_size,
            "data_page_size": self.data_page_size,
            "use_pyarrow": False,
        }


DEFAULT_PARQUET_OPTIONS = ParquetWriteOptions()
_DISK_RESERVE_BYTES = 8 * 1024 * 1024


class ParquetOperationCancelled(CancelledError):
    """Analysis or export was cancelled before publishing its output."""


class ParquetVerificationError(ValueError):
    """A Parquet round trip changed the expected dataset."""


def _check_cancelled(cancel: Event | None) -> None:
    if cancel is not None and cancel.is_set():
        raise ParquetOperationCancelled("Parquet operation cancelled")


def verify_parquet(
    frame: pl.DataFrame, path: str | Path, *, cancel: Event | None = None
) -> int:
    """Fully reread and check names, order, dtypes and exact values; return bytes.

    This intentionally allocates a second full frame. The caller must budget for
    it. NaNs compare equal to NaNs; float values otherwise have no tolerance.
    """
    _check_cancelled(cancel)
    restored = pl.read_parquet(path, glob=False)
    _check_cancelled(cancel)
    if (
        restored.columns != frame.columns
        or restored.schema != frame.schema
        or restored.shape != frame.shape
    ):
        raise ParquetVerificationError(
            "Parquet verification failed: schema or shape changed"
        )
    # Polars 1.28 can report unequal empty categoricals with distinct caches;
    # equal ordered schemas and shapes fully describe a zero-row dataset.
    if frame.height and not restored.equals(frame, null_equal=True):
        raise ParquetVerificationError(
            "Parquet verification failed: ordered values changed"
        )
    _check_cancelled(cancel)
    return Path(path).stat().st_size


def _check_destination(destination: Path, protected_paths: tuple[Path, ...]) -> None:
    resolved = os.path.normcase(str(destination.resolve()))
    for protected in protected_paths:
        if resolved == os.path.normcase(str(protected.resolve())) or (
            destination.exists()
            and protected.exists()
            and os.path.samefile(destination, protected)
        ):
            raise ValueError(
                "Optimized export must not overwrite the active source file"
            )


class _LimitedWriter:
    """Check disk/cancellation/size before native Polars writes each byte buffer.

    Polars may construct an encoded buffer in memory before calling write(); the
    size limit bounds disk usage, not the encoder's working memory.
    """

    def __init__(
        self, raw: BinaryIO, parent: Path, limit: int | None, cancel: Event | None
    ) -> None:
        self.raw, self.parent, self.limit, self.cancel = raw, parent, limit, cancel
        self.error: Exception | None = None

    def write(self, data: bytes) -> int:
        if self.error is not None:
            raise self.error
        try:
            _check_cancelled(self.cancel)
            if self.limit is not None and self.raw.tell() + len(data) > self.limit:
                raise ValueError("Parquet output exceeds the temporary file size limit")
            if shutil.disk_usage(self.parent).free < len(data) + _DISK_RESERVE_BYTES:
                raise OSError(
                    errno.ENOSPC, "Insufficient free space for Parquet export"
                )
            return self.raw.write(data)
        except Exception as exc:
            # Polars wraps Python file-writer exceptions in ComputeError. Retain
            # the original cancellation/budget/I/O exception for the caller.
            self.error = exc
            raise

    def flush(self) -> None:
        self.raw.flush()

    def tell(self) -> int:
        return self.raw.tell()


def _validate_write_options(
    frame: pl.DataFrame, options: ParquetWriteOptions, max_temporary_bytes: int | None
) -> None:
    if not isinstance(frame, pl.DataFrame) or not isinstance(
        options, ParquetWriteOptions
    ):
        raise TypeError("A Polars DataFrame and ParquetWriteOptions are required")
    if max_temporary_bytes is not None and (
        type(max_temporary_bytes) is not int or max_temporary_bytes <= 0
    ):
        raise ValueError("Temporary file size limit must be a positive integer")


def _check_write_space(
    frame: pl.DataFrame, parent: Path, max_temporary_bytes: int | None
) -> None:
    estimate = max(frame.estimated_size() * 2, 1024 * 1024)
    if max_temporary_bytes is not None:
        estimate = min(estimate, max_temporary_bytes)
    if shutil.disk_usage(parent).free < estimate + _DISK_RESERVE_BYTES:
        raise OSError(errno.ENOSPC, "Insufficient free space for Parquet export")


def _write_bounded_frame(
    frame: pl.DataFrame,
    raw: BinaryIO,
    parent: Path,
    options: ParquetWriteOptions,
    cancel: Event | None,
    max_temporary_bytes: int | None,
) -> None:
    writer = _LimitedWriter(raw, parent, max_temporary_bytes, cancel)
    try:
        frame.write_parquet(cast(IO[bytes], writer), **options.as_kwargs())
    except Exception as exc:
        if writer.error is not None:
            raise writer.error from exc
        raise
    raw.flush()
    os.fsync(raw.fileno())
    _check_cancelled(cancel)


def write_parquet_bounded(
    frame: pl.DataFrame,
    path: str | Path,
    *,
    options: ParquetWriteOptions = DEFAULT_PARQUET_OPTIONS,
    cancel: Event | None = None,
    max_temporary_bytes: int | None = None,
) -> int:
    """Write a NEW disposable candidate file with bounded disk usage.

    This does not verify or publish the file. It never overwrites an existing
    path and removes its own partial file on failure or cancellation. Analysis
    owns successful files and must clean them up. Encoding memory is not capped.
    """
    _validate_write_options(frame, options, max_temporary_bytes)
    _check_cancelled(cancel)
    target = Path(path)
    _check_write_space(frame, target.parent, max_temporary_bytes)
    created = False
    try:
        with target.open("xb") as raw:
            created = True
            _write_bounded_frame(
                frame, raw, target.parent, options, cancel, max_temporary_bytes
            )
        _check_cancelled(cancel)
        return target.stat().st_size
    except BaseException:
        if created:
            target.unlink(missing_ok=True)
        raise


def write_parquet_verified_atomic(
    frame: pl.DataFrame,
    path: str | Path,
    *,
    options: ParquetWriteOptions = DEFAULT_PARQUET_OPTIONS,
    cancel: Event | None = None,
    max_temporary_bytes: int | None = None,
    protected_paths: Iterable[str | Path] = (),
) -> int:
    """Publish a verified copy, preserving any destination until final replace.

    Cancellation is cooperative: native encoding/reading may finish first. The
    final cancellation check precedes os.replace; once replacement starts it is
    committed. GUI callers must coordinate changes to their protected source.
    """
    _validate_write_options(frame, options, max_temporary_bytes)
    _check_cancelled(cancel)
    destination = Path(path).absolute()
    protected = tuple(Path(p) for p in protected_paths)
    _check_destination(destination, protected)
    _check_write_space(frame, destination.parent, max_temporary_bytes)
    fd, temporary = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    try:
        with os.fdopen(fd, "wb") as raw:
            _write_bounded_frame(
                frame, raw, destination.parent, options, cancel, max_temporary_bytes
            )
        _check_cancelled(cancel)
        size = verify_parquet(frame, temporary, cancel=cancel)
        if max_temporary_bytes is not None and size > max_temporary_bytes:
            raise ValueError("Parquet output exceeds the temporary file size limit")
        _check_destination(destination, protected)
        _check_cancelled(cancel)
        os.replace(temporary, destination)
        return size
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def read_dataset(path: str | Path, *, csv_types: CsvTypes = "strings") -> pl.DataFrame:
    """Read Parquet, or CSV with an explicit typing policy.

    Excel remains a legacy optional path; no reader dependency is bundled here.
    """
    source = Path(path)
    if csv_types not in ("strings", "infer"):
        raise ValueError("CSV types must be 'strings' or 'infer'.")
    if source.suffix.lower() == ".parquet":
        return pl.read_parquet(source)
    if source.suffix.lower() == ".csv":
        return pl.read_csv(
            source, infer_schema_length=0 if csv_types == "strings" else 100
        )
    if source.suffix.lower() == ".xlsx":
        return pl.read_excel(source)
    raise ValueError(f"Unsupported file extension: {source.suffix}")


def write_dataset_atomic(
    df: pl.DataFrame, path: str | Path, *, format: str = "parquet"
) -> None:
    """Write a sibling temporary file and replace the destination only on success."""
    if format not in ("parquet", "csv"):
        raise ValueError(f"Unsupported output format: {format}")
    destination = Path(path).absolute()
    fd, temporary = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    os.close(fd)
    try:
        if format == "parquet":
            df.write_parquet(temporary)
        else:
            df.write_csv(temporary)
        with open(temporary, "rb+") as saved:
            os.fsync(saved.fileno())
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
