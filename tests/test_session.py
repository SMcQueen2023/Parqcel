import polars as pl
import pytest

from parqcel.core.session import DatasetSession


def test_revisions_dirty_and_saved_state_follow_undo_redo():
    session = DatasetSession(pl.DataFrame({"a": [1]}), "original.parquet")
    assert not session.dirty
    session.set_cell(0, "a", "2")
    assert session.revision == 1 and session.dirty
    assert session.mark_saved(1, "saved.parquet")
    session.set_cell(0, "a", "3")
    assert session.revision == 2 and session.dirty
    assert session.undo()
    assert session.revision == 3 and not session.dirty
    assert session.redo()
    assert session.revision == 4 and session.dirty


def test_stale_save_does_not_clear_dirty_or_replace_path():
    session = DatasetSession(pl.DataFrame({"a": [1]}), "original.parquet")
    saved_revision = session.revision
    session.set_cell(0, "a", "2")
    assert not session.mark_saved(saved_revision, "stale.parquet")
    assert session.source_path == "original.parquet"
    assert session.dirty


def test_failed_mutation_preserves_revision_and_redo():
    session = DatasetSession(pl.DataFrame({"a": pl.Series([1], dtype=pl.Int8)}))
    session.set_cell(0, "a", "2")
    session.undo()
    before = session.revision
    with pytest.raises(ValueError):
        session.set_cell(0, "a", "128")
    with pytest.raises(TypeError):
        session.commit(None)
    assert session.revision == before
    assert not session.can_undo
    assert session.can_redo
    assert not session.dirty
    assert session.redo()
    assert session.dataframe["a"].to_list() == [2]


def test_session_owns_snapshots_and_bounds_history():
    original = pl.DataFrame({"a": [1], "b": [2]})
    session = DatasetSession(original, max_history=2)
    original.drop_in_place("b")
    session.dataframe.drop_in_place("a")
    assert session.dataframe.columns == ["a", "b"]
    for value in range(2, 6):
        session.set_cell(0, "a", str(value))
    assert len(session.undo_history) == 2
    assert session.undo() and session.undo()
    assert not session.undo()
    assert session.dataframe["a"].to_list() == [3]
    assert len(session.redo_history) == 2


def test_history_byte_limit_and_new_branch_clear_redo():
    session = DatasetSession(pl.DataFrame({"a": [1]}), max_history_bytes=1)
    session.set_cell(0, "a", "2")
    assert not session.can_undo
    session = DatasetSession(pl.DataFrame({"a": [1]}))
    session.set_cell(0, "a", "2")
    session.undo()
    session.set_cell(0, "a", "3")
    assert not session.can_redo


def test_native_cell_edit_preserves_untouched_nanoseconds_and_nulls():
    frame = pl.DataFrame({"t": pl.Series([1, 2, None], dtype=pl.Datetime("ns"))})
    session = DatasetSession(frame)
    session.set_cell(2, "t", "2024-01-01T01:02:03")
    assert session.dataframe["t"].cast(pl.Int64).head(2).to_list() == [1, 2]
    assert session.dataframe.schema == frame.schema
