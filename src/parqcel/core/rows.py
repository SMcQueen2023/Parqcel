"""Atomic, schema-preserving insertion of blank and clipboard rows."""

from __future__ import annotations

from collections.abc import Sequence
import csv
import io
from threading import Lock

import polars as pl

from .values import is_editable_dtype, parse_cell_value

MAX_INSERT_CELLS = 100_000
MAX_PASTE_BYTES = 10 * 1024 * 1024
_CSV_LIMIT_LOCK = Lock()


def _validate_position(frame: pl.DataFrame, position: int) -> None:
    if type(position) is not int or not 0 <= position <= frame.height:
        raise ValueError("Insertion position must be between zero and the row count")
    if not frame.width:
        raise ValueError("Add a column before inserting rows")


def _validate_count(frame: pl.DataFrame, count: int) -> None:
    if type(count) is not int or count <= 0:
        raise ValueError("The number of inserted rows must be a positive integer")
    if count * frame.width > MAX_INSERT_CELLS:
        raise ValueError(
            f"Insert at most {MAX_INSERT_CELLS:,} cells at once, including omitted "
            "columns. Paste or add fewer rows."
        )


def _insert(frame: pl.DataFrame, rows: pl.DataFrame, position: int) -> pl.DataFrame:
    # Concatenating native slices preserves untouched nanoseconds, nested values,
    # and integer precision; no existing column is converted through Python.
    return pl.concat(
        [frame.slice(0, position), rows, frame.slice(position)], rechunk=False
    )


def insert_blank_rows(
    frame: pl.DataFrame, position: int, count: int = 1
) -> pl.DataFrame:
    """Insert all-null rows at a zero-based boundary in ``[0, frame.height]``.

    Preserve the schema, including complex/read-only columns. At most 100,000
    inserted cells are allowed, counting every dataset column.
    """
    _validate_position(frame, position)
    _validate_count(frame, count)
    rows = pl.DataFrame(
        [
            pl.Series(name, [None] * count, dtype=dtype)
            for name, dtype in frame.schema.items()
        ]
    )
    return _insert(frame, rows, position)


def _read_tsv(text: str, frame: pl.DataFrame, column_count: int) -> list[list[str]]:
    if not isinstance(text, str) or not text:
        raise ValueError("The clipboard contains no text rows")
    if len(text) > MAX_PASTE_BYTES or len(text.encode("utf-8")) > MAX_PASTE_BYTES:
        raise ValueError("Clipboard text exceeds 10 MiB. Paste a smaller range.")
    records: list[list[str]] = []
    width: int | None = None
    # csv's field limit is process-global. Serialize our temporary increase so
    # large quoted fields within the clipboard budget can be parsed correctly.
    with _CSV_LIMIT_LOCK:
        previous_limit = csv.field_size_limit()
        csv.field_size_limit(max(previous_limit, MAX_PASTE_BYTES))
        try:
            reader = csv.reader(
                io.StringIO(text, newline=""), delimiter="\t", strict=True
            )
            for row in reader:
                row = row or [""]
                if width is None:
                    width = len(row)
                    if width > column_count:
                        raise ValueError(
                            f"Clipboard has {width:,} fields but only "
                            f"{column_count:,} target columns are available"
                        )
                elif len(row) != width:
                    raise ValueError(
                        "Clipboard rows must have the same number of fields"
                    )
                _validate_count(frame, len(records) + 1)
                records.append(row)
        except csv.Error as exc:
            raise ValueError(f"Invalid quoted TSV clipboard text: {exc}") from exc
        finally:
            csv.field_size_limit(previous_limit)
    return records


def insert_tsv_rows(
    frame: pl.DataFrame, position: int, text: str, columns: Sequence[str]
) -> pl.DataFrame:
    """Parse rectangular, quoted TSV and insert it atomically without headers.

    Map fields to the first N names in ``columns`` in their supplied order.
    Missing dataset columns receive null. Empty string fields stay empty in
    String columns; blank non-string fields become null, matching cell edits.
    Read-only dtypes accept only blank fields, represented as null. Literal
    ``null`` has no special meaning. Invalid fields reject the entire paste.

    Text is limited to 10 MiB in UTF-8 and insertion to 100,000 total cells,
    including omitted columns. Existing dataframe values and dtypes are retained.
    """
    _validate_position(frame, position)
    if isinstance(columns, (str, bytes)):
        raise ValueError("Supply target columns as a sequence of column names")
    names = list(columns)
    if not names or any(not isinstance(name, str) for name in names):
        raise ValueError("Choose at least one named target column")
    if len(set(names)) != len(names):
        raise ValueError("Target column names must be unique")
    if any(name not in frame.columns for name in names):
        raise ValueError("All target columns must exist in the dataset")
    records = _read_tsv(text, frame, len(names))
    if not records:
        raise ValueError("The clipboard contains no text rows")
    values: dict[str, list] = {name: [] for name in names[: len(records[0])]}
    schema = frame.schema
    for row_number, record in enumerate(records, start=1):
        for name, field in zip(values, record):
            dtype = schema[name]
            try:
                if not is_editable_dtype(dtype) and not field.strip():
                    value = None
                else:
                    value = parse_cell_value(field, dtype)
            except (
                ValueError,
                TypeError,
                OverflowError,
                pl.exceptions.PolarsError,
            ) as exc:
                raise ValueError(
                    f"Clipboard row {row_number:,}, column {name!r}: {exc}"
                ) from exc
            values[name].append(value)
    try:
        rows = pl.DataFrame(
            [
                pl.Series(
                    name,
                    values[name] if name in values else [None] * len(records),
                    dtype=dtype,
                    strict=True,
                )
                for name, dtype in schema.items()
            ]
        )
        return _insert(frame, rows, position)
    except (ValueError, TypeError, OverflowError, pl.exceptions.PolarsError) as exc:
        raise ValueError(
            f"Clipboard rows cannot preserve the dataset schema: {exc}"
        ) from exc
