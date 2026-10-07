from datetime import date, datetime, time
import csv
import io

import polars as pl
import pytest

from parqcel.core import rows
from parqcel.core.rows import insert_blank_rows, insert_tsv_rows
from parqcel.core.session import DatasetSession


def typed_frame():
    return pl.DataFrame(
        {
            "id": pl.Series([2**64 - 1, 2**63 + 1], dtype=pl.UInt64),
            "when": pl.Series([1, 2], dtype=pl.Datetime("ns")),
            "text": ["original", "second"],
            "nested": [[1, None], [2]],
        }
    )


@pytest.mark.parametrize("position", [0, 1, 2])
def test_blank_insertion_preserves_existing_values_schema_and_nanoseconds(position):
    frame = typed_frame()
    result = insert_blank_rows(frame, position, 2)
    assert result.schema == frame.schema
    assert result.height == 4 and frame.height == 2
    assert result.slice(position, 2).null_count().row(0) == (2, 2, 2, 2)
    assert pl.concat([result.head(position), result.slice(position + 2)]).equals(frame)
    assert result["when"].drop_nulls().cast(pl.Int64).to_list() == [1, 2]
    assert result["id"].drop_nulls().to_list() == [2**64 - 1, 2**63 + 1]


def test_insert_into_empty_typed_dataset_and_read_only_columns():
    frame = pl.DataFrame(
        schema={
            "n": pl.Int8,
            "category": pl.Categorical,
            "choice": pl.Enum(["a", "b"]),
            "struct": pl.Struct({"x": pl.Int64}),
            "binary": pl.Binary,
            "decimal": pl.Decimal(8, 2),
        }
    )
    blank = insert_blank_rows(frame, 0)
    assert blank.schema == frame.schema
    assert blank.row(0) == (None,) * frame.width
    pasted = insert_tsv_rows(frame, 0, "3\t\t\t\t\t\n", frame.columns)
    assert pasted.schema == frame.schema
    assert pasted.row(0) == (3, None, None, None, None, None)
    with pytest.raises(ValueError, match="column 'category'"):
        insert_tsv_rows(frame, 0, "a", ["category"])


def test_tsv_quoting_visual_mapping_omitted_columns_and_no_header_guessing():
    frame = typed_frame()
    output = io.StringIO(newline="")
    csv.writer(output, delimiter="\t", lineterminator="\n").writerows(
        [["embedded\ttab", str(2**64 - 1)], ['line one\n"line two"', "7"]]
    )
    result = insert_tsv_rows(frame, 1, output.getvalue(), ["text", "id", "when"])
    assert result["text"].to_list() == [
        "original",
        "embedded\ttab",
        'line one\n"line two"',
        "second",
    ]
    assert result["id"].to_list() == [2**64 - 1, 2**64 - 1, 7, 2**63 + 1]
    assert result["when"].cast(pl.Int64).to_list() == [1, None, None, 2]
    assert result["nested"].to_list() == [[1, None], None, None, [2]]
    assert insert_tsv_rows(frame, 0, "text", ["text"])["text"][0] == "text"


def test_blank_fields_preserve_string_semantics_and_other_columns_become_null():
    frame = pl.DataFrame(schema={"s": pl.String, "n": pl.Int64, "b": pl.Boolean})
    result = insert_tsv_rows(frame, 0, '\t \t\n"null"\t4\tyes\n', frame.columns)
    assert result.rows() == [("", None, None), ("null", 4, True)]
    one_blank = insert_tsv_rows(frame, 0, "\n", ["n"])
    assert one_blank.row(0) == (None, None, None)


def test_typed_paste_reuses_strict_scalar_rules():
    frame = pl.DataFrame(
        schema={
            "day": pl.Date,
            "instant": pl.Datetime("us"),
            "clock": pl.Time,
            "f": pl.Float32,
        }
    )
    result = insert_tsv_rows(
        frame,
        0,
        "2024-01-02\t2024-01-02T03:04:05.123456\t03:04:05\t1.25",
        frame.columns,
    )
    assert result.schema == frame.schema
    assert result.row(0) == (
        date(2024, 1, 2),
        datetime(2024, 1, 2, 3, 4, 5, 123456),
        time(3, 4, 5),
        1.25,
    )
    timezone_frame = pl.DataFrame(schema={"instant": pl.Datetime("ns", "UTC")})
    result = insert_tsv_rows(
        timezone_frame, 0, "2024-01-02T03:04:05+01:00", ["instant"]
    )
    assert result.schema == timezone_frame.schema
    assert result["instant"].dt.hour()[0] == 2


@pytest.mark.parametrize(
    "text, columns, match",
    [
        ("18446744073709551616", ["id"], "row 1.*column 'id'"),
        ("-1", ["id"], "row 1.*column 'id'"),
        ("1970-01-01T00:00:00.000000001", ["when"], "six fractional"),
        ("[3]", ["nested"], "not supported"),
        ("a\tb", ["text"], "target columns"),
        ("a\tb\nc", ["text", "id"], "same number"),
        ('"unterminated', ["text"], "quoted TSV"),
        ("", ["text"], "no text"),
        ("x", ["missing"], "exist"),
        ("x", ["text", "text"], "unique"),
        ("x", [], "at least one"),
        ("x", "text", "sequence"),
    ],
)
def test_invalid_pastes_are_atomic_and_preserve_redo(text, columns, match):
    original = typed_frame()
    session = DatasetSession(original)
    session.insert_rows(1)
    session.undo()
    revision = session.revision
    with pytest.raises(ValueError, match=match):
        session.insert_pasted_rows(1, text, columns)
    assert session.dataframe.equals(original)
    assert session.revision == revision
    assert session.can_redo and not session.can_undo and not session.dirty


@pytest.mark.parametrize(
    "position,count", [(-1, 1), (3, 1), (True, 1), (0, 0), (0, -1), (0, 1.5), (0, True)]
)
def test_invalid_blank_insertions_do_not_mutate(position, count):
    session = DatasetSession(typed_frame())
    with pytest.raises(ValueError):
        session.insert_rows(position, count)
    assert session.revision == 0 and not session.can_undo


def test_budgets_include_omitted_columns_and_utf8_bytes(monkeypatch):
    frame = typed_frame()
    monkeypatch.setattr(rows, "MAX_INSERT_CELLS", 7)
    with pytest.raises(ValueError, match="including omitted"):
        insert_tsv_rows(frame, 0, "1\n2", ["id"])
    with pytest.raises(ValueError, match="including omitted"):
        insert_blank_rows(frame, 0, 2)
    monkeypatch.setattr(rows, "MAX_PASTE_BYTES", 5)
    with pytest.raises(ValueError, match="10 MiB"):
        insert_tsv_rows(frame, 0, "\u00e9\u00e9\u00e9", ["text"])


def test_long_field_within_byte_budget_and_csv_global_limit_restored():
    field = "x" * 200_000
    previous_limit = csv.field_size_limit()
    result = insert_tsv_rows(
        pl.DataFrame(schema={"text": pl.String}), 0, field, ["text"]
    )
    assert result["text"][0] == field
    assert csv.field_size_limit() == previous_limit


def test_schema_required_and_each_success_is_one_history_entry():
    with pytest.raises(ValueError, match="Add a column"):
        insert_blank_rows(pl.DataFrame(), 0)
    frame = typed_frame()
    session = DatasetSession(frame)
    session.insert_pasted_rows(2, "9\n10", ["id"])
    assert session.revision == 1 and len(session.undo_history) == 1
    assert session.dataframe.height == 4
    session.undo()
    assert session.dataframe.equals(frame) and not session.dirty
    session.redo()
    assert session.dataframe["id"].to_list() == [2**64 - 1, 2**63 + 1, 9, 10]
    assert session.revision == 3 and session.dirty
