from datetime import date
from decimal import Decimal

import polars as pl
import pytest

import parqcel.core.grid as grid
from parqcel.core.grid import column_profile, find_match, raw_cell_text


@pytest.mark.parametrize("backwards", [False, True])
@pytest.mark.parametrize("columns", [None, ["b"], ["b", "a"]])
def test_find_matches_row_major_reference_in_both_directions(backwards, columns):
    frame = pl.DataFrame({"a": ["x", "other", "X"], "b": ["x", "X", None]})
    cells = [(row, column) for row in range(3) for column in range(2)]
    matching = {
        cell
        for cell in cells
        if (columns is None or frame.columns[cell[1]] in columns)
        and "x" in raw_cell_text(frame[:, cell[1]], cell[0]).lower()
    }
    for anchor in [None, *cells]:
        if anchor is None:
            ordered = list(reversed(cells)) if backwards else cells
        else:
            position = cells.index(anchor)
            ordered = (
                list(reversed(cells[:position])) + list(reversed(cells[position:]))
                if backwards
                else cells[position + 1 :] + cells[: position + 1]
            )
        expected = next((cell for cell in ordered if cell in matching), None)
        assert (
            find_match(frame, "x", columns=columns, after=anchor, backwards=backwards)
            == expected
        )


def test_find_is_literal_case_aware_and_searches_nulls_and_raw_values():
    frame = pl.DataFrame(
        {
            "text": ["a[b]", "ABC", None],
            "id": pl.Series([2**64 - 1, 2, None], dtype=pl.UInt64),
        }
    )
    assert find_match(frame, "[b]") == (0, 0)
    assert find_match(frame, "abc", case_sensitive=True) is None
    assert find_match(frame, "abc") == (1, 0)
    assert find_match(frame, "null") == (2, 0)
    assert find_match(frame, str(2**64 - 1)) == (0, 1)
    assert find_match(frame, "") is None
    assert find_match(frame, "a", columns=[]) is None
    assert find_match(pl.DataFrame(), "a") is None
    with pytest.raises(ValueError):
        find_match(frame, "a", columns=["missing"])
    with pytest.raises(ValueError):
        find_match(frame, "a", after=(3, 0))


def test_find_wraps_to_its_only_match_and_limits_rendered_chunks(monkeypatch):
    monkeypatch.setattr(grid, "_SEARCH_CHUNK_SIZE", 4)
    original = grid._raw_strings
    rendered_lengths = []

    def bounded_render(series, **kwargs):
        rendered_lengths.append(len(series))
        assert len(series) <= 4
        return original(series, **kwargs)

    monkeypatch.setattr(grid, "_raw_strings", bounded_render)
    frame = pl.DataFrame({"a": ["other"] * 9 + ["target"]})
    assert find_match(frame, "target", after=(9, 0)) == (9, 0)
    assert find_match(frame, "target", after=(9, 0), backwards=True) == (9, 0)
    assert find_match(frame, "missing") is None
    assert len(rendered_lengths) > 3


def test_raw_temporal_and_complex_values_keep_precision_and_content():
    timestamp = pl.Series("time", [1], dtype=pl.Datetime("ns"))
    assert raw_cell_text(timestamp, 0).endswith(".000000001")
    frame = pl.DataFrame({"nested": [["needle", None]], "bytes": [b"\x00data"]})
    assert raw_cell_text(frame["nested"], 0) == '["needle", null]'
    assert "\\x00" in raw_cell_text(frame["bytes"], 0)
    assert find_match(frame, "needle") == (0, 0)


def test_integer_profile_keeps_large_integer_extrema_and_mean_exact():
    frame = pl.DataFrame({"id": pl.Series([2**63, 2**63 + 2, None], dtype=pl.UInt64)})
    profile = column_profile(frame, "id")
    assert profile == {
        "name": "id",
        "dtype": "UInt64",
        "count": 3,
        "non_null": 2,
        "nulls": 1,
        "unique": 3,
        "min": 2**63,
        "max": 2**63 + 2,
        "mean": Decimal(2**63 + 1),
    }


def test_profiles_include_null_counts_and_at_most_five_typed_top_values():
    frame = pl.DataFrame({"count": ["popular"] * 5 + [None] * 3 + list("abcdef")})
    profile = column_profile(frame, "count")
    assert profile["count"] == 14
    assert profile["non_null"] == 11
    assert profile["nulls"] == 3
    assert profile["unique"] == 8
    assert profile["min"] == "a" and profile["max"] == "popular"
    assert len(profile["top_values"]) == 5
    assert profile["top_values"][:2] == [
        {"value": "popular", "count": 5},
        {"value": None, "count": 3},
    ]
    dates = column_profile(pl.DataFrame({"d": [date(2024, 1, 1), None]}), "d")
    assert dates["min"] == date(2024, 1, 1)
    assert dates["max"] == date(2024, 1, 1)


def test_empty_and_all_null_profiles_and_missing_column():
    profile = column_profile(pl.DataFrame(schema={"a": pl.Int64}), "a")
    assert profile["count"] == profile["nulls"] == profile["unique"] == 0
    assert profile["min"] is profile["max"] is profile["mean"] is None
    profile = column_profile(pl.DataFrame({"a": [None, None]}), "a")
    assert profile["non_null"] == 0
    assert profile["top_values"] == [{"value": None, "count": 2}]
    with pytest.raises(ValueError):
        column_profile(pl.DataFrame({"a": [1]}), "missing")
