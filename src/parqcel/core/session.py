"""Transactional dataset ownership, revisions and bounded undo history."""

from dataclasses import dataclass
from collections.abc import Sequence
from pathlib import Path
from uuid import uuid4

import polars as pl

from .values import parse_cell_value
from .rows import insert_blank_rows, insert_tsv_rows


@dataclass(frozen=True)
class _Snapshot:
    frame: pl.DataFrame
    state_id: str


class DatasetSession:
    """Own a dataset independently of Qt.

    DataFrame access returns shallow clones, retaining Polars' shared buffers
    while protecting session state from caller-side in-place mutations.
    Revisions never decrease, including undo/redo. Dirty state tracks the saved
    content identity, so undoing back to saved content becomes clean again.
    """

    def __init__(
        self,
        dataframe: pl.DataFrame,
        source_path: str | Path | None = None,
        *,
        max_history: int = 20,
        max_history_bytes: int = 256 * 1024 * 1024,
    ) -> None:
        if not isinstance(dataframe, pl.DataFrame):
            raise TypeError("Dataset must be a Polars DataFrame")
        if max_history < 0 or max_history_bytes < 0:
            raise ValueError("History limits must be non-negative")
        self.id = uuid4().hex
        self.revision = 0
        self.source_path = str(source_path) if source_path is not None else None
        self.max_history = max_history
        self.max_history_bytes = max_history_bytes
        self._current = _Snapshot(dataframe.clone(), uuid4().hex)
        self._saved_state_id = self._current.state_id
        self._undo: list[_Snapshot] = []
        self._redo: list[_Snapshot] = []

    @property
    def session_id(self) -> str:
        return self.id

    @property
    def dataframe(self) -> pl.DataFrame:
        return self.get_dataframe()

    def get_dataframe(self) -> pl.DataFrame:
        return self._current.frame.clone()

    @property
    def dirty(self) -> bool:
        return self._current.state_id != self._saved_state_id

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    @property
    def undo_history(self) -> tuple[pl.DataFrame, ...]:
        return tuple(item.frame.clone() for item in self._undo)

    @property
    def redo_history(self) -> tuple[pl.DataFrame, ...]:
        return tuple(item.frame.clone() for item in self._redo)

    def _trim_history(self, history: list[_Snapshot]) -> None:
        # Estimated sizes conservatively count shared buffers more than once.
        retained_bytes = sum(item.frame.estimated_size() for item in history)
        while history and (
            len(history) > self.max_history or retained_bytes > self.max_history_bytes
        ):
            retained_bytes -= history.pop(0).frame.estimated_size()

    def commit(self, dataframe: pl.DataFrame) -> None:
        if not isinstance(dataframe, pl.DataFrame):
            raise TypeError("Dataset must be a Polars DataFrame")
        next_state = _Snapshot(dataframe.clone(), uuid4().hex)
        self._undo.append(self._current)
        self._trim_history(self._undo)
        self._redo.clear()
        self._current = next_state
        self.revision += 1

    def set_cell(self, row: int, column: str, value: object) -> None:
        frame = self._current.frame
        if row < 0 or row >= frame.height:
            raise IndexError("Row is outside the dataset")
        if column not in frame.columns:
            raise ValueError(f"Column '{column}' not found")
        dtype = frame.schema[column]
        parsed = parse_cell_value(value, dtype)
        # Native Polars slices preserve all untouched values (including temporal
        # precision) without converting an entire column into Python objects.
        original = frame[column]
        replacement = pl.Series(column, [parsed], dtype=dtype, strict=True)
        updated = pl.concat(
            [original.slice(0, row), replacement, original.slice(row + 1)],
            rechunk=False,
        )
        self.commit(frame.with_columns(updated))

    def undo(self) -> bool:
        if not self._undo:
            return False
        self._redo.append(self._current)
        self._trim_history(self._redo)
        self._current = self._undo.pop()
        self.revision += 1
        return True

    def insert_rows(self, position: int, count: int = 1) -> None:
        """Insert null rows as one transaction, validating before history changes."""
        self.commit(insert_blank_rows(self._current.frame, position, count))

    def insert_pasted_rows(
        self, position: int, text: str, columns: Sequence[str]
    ) -> None:
        """Insert a complete typed TSV paste as one undoable transaction."""
        self.commit(insert_tsv_rows(self._current.frame, position, text, columns))

    def redo(self) -> bool:
        if not self._redo:
            return False
        self._undo.append(self._current)
        self._trim_history(self._undo)
        self._current = self._redo.pop()
        self.revision += 1
        return True

    def mark_saved(self, revision: int, path: str | Path) -> bool:
        """Acknowledge a completed save only if it saved this current revision."""
        if revision != self.revision:
            return False
        self.source_path = str(path)
        self._saved_state_id = self._current.state_id
        return True
