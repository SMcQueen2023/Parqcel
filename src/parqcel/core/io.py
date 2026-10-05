"""Dataset I/O shared by desktop and command-line workflows."""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
from typing import Literal

import polars as pl

CsvTypes = Literal["strings", "infer"]


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
