"""Shared view-only formatting for editor and preview table models."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, localcontext
import html
from typing import Any

import polars as pl
from PyQt6.QtCore import QModelIndex, Qt

from parqcel.core.grid import raw_cell_text

_MODES = {"auto", "number", "percent", "scientific", "date", "datetime"}
_DEFAULT_FORMAT = {"mode": "auto", "precision": 2, "thousands": False}


def display_value(value: Any, dtype: pl.DataType, raw: str, options: dict) -> str:
    if value is None:
        return "null"
    mode = options["mode"]
    if mode == "date" and isinstance(value, (datetime, date)):
        return (
            value.date().isoformat()
            if isinstance(value, datetime)
            else value.isoformat()
        )
    if mode == "datetime" and isinstance(value, (datetime, date)):
        return raw
    if dtype.is_numeric() and (
        mode in {"number", "percent", "scientific"} or options["thousands"]
    ):
        with localcontext() as context:
            context.prec = max(50, len(raw) + options["precision"] + 10)
            number = Decimal(value) if isinstance(value, int) else Decimal(str(value))
            precision = (
                0 if mode == "auto" and dtype.is_integer() else options["precision"]
            )
            grouping = "," if options["thousands"] else ""
            if mode == "scientific":
                return format(number, f".{precision}E")
            if mode == "percent":
                return format(number * 100, f"{grouping}.{precision}f") + "%"
            return format(number, f"{grouping}.{precision}f")
    return raw


class TablePresentation:
    """Mixin: subclasses supply their current page through _presentation_frame."""

    dataChanged: Any
    index: Any

    def _init_presentation(self) -> None:
        self._column_formats: dict[str, dict] = {}

    def _presentation_frame(self) -> pl.DataFrame:
        raise NotImplementedError

    def get_column_names(self) -> list[str]:
        return list(self._presentation_frame().columns)

    def page_dataframe(self) -> pl.DataFrame:
        return self._presentation_frame().clone()

    def _valid_cell(self, index: QModelIndex) -> bool:
        frame = self._presentation_frame()
        return (
            index.isValid()
            and 0 <= index.row() < frame.height
            and 0 <= index.column() < frame.width
        )

    def raw_value(self, index: QModelIndex) -> Any:
        if not self._valid_cell(index):
            return None
        return self._presentation_frame()[index.row(), index.column()]

    def column_format(self, name: str) -> dict:
        if name not in self.get_column_names():
            raise ValueError(f"Column '{name}' not found")
        return dict(self._column_formats.get(name, _DEFAULT_FORMAT))

    def set_column_format(
        self, name: str, mode: str = "auto", precision: int = 2, thousands: bool = False
    ) -> None:
        if mode not in _MODES:
            raise ValueError(f"Unsupported display format: {mode}")
        if type(precision) is not int or not 0 <= precision <= 15:
            raise ValueError("Display precision must be an integer from 0 to 15")
        if type(thousands) is not bool:
            raise ValueError("Thousands separator must be a boolean")
        self.column_format(name)  # Validate the column without mutating preferences.
        self._column_formats[name] = {
            "mode": mode,
            "precision": precision,
            "thousands": thousands,
        }
        frame = self._presentation_frame()
        if frame.height:
            column = frame.columns.index(name)
            self.dataChanged.emit(
                self.index(0, column),
                self.index(frame.height - 1, column),
                [Qt.ItemDataRole.DisplayRole],
            )

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not self._valid_cell(index):
            return None
        frame = self._presentation_frame()
        column = frame.columns[index.column()]
        dtype = frame.schema[column]
        if role == Qt.ItemDataRole.TextAlignmentRole:
            horizontal = (
                Qt.AlignmentFlag.AlignRight
                if dtype.is_numeric()
                else Qt.AlignmentFlag.AlignLeft
            )
            return int(horizontal | Qt.AlignmentFlag.AlignVCenter)
        if role not in (
            Qt.ItemDataRole.DisplayRole,
            Qt.ItemDataRole.EditRole,
            Qt.ItemDataRole.ToolTipRole,
        ):
            return None
        raw = raw_cell_text(frame[column], index.row())
        if role == Qt.ItemDataRole.EditRole:
            return raw
        value = self.raw_value(index)
        if role == Qt.ItemDataRole.ToolTipRole:
            text = "null" if value is None else raw
            return f"<pre>{html.escape(str(dtype))}\n{html.escape(text)}</pre>"
        return display_value(value, dtype, raw, self.column_format(column))
