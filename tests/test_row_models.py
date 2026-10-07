import polars as pl
import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QAbstractItemModelTester, QSignalSpy

from models.polars_table_model import PolarsTableModel
from parqcel.core.rows import insert_tsv_rows


@pytest.mark.parametrize("position", [0, 3, 6])
def test_insert_navigates_to_first_inserted_row_with_one_commit_and_reset(
    qapp, qtlog, position
):
    model = PolarsTableModel(pl.DataFrame({"id": range(6)}), chunk_size=3)
    model.jump_to_page(1)
    tester = QAbstractItemModelTester(
        model, QAbstractItemModelTester.FailureReportingMode.Warning
    )
    resets = QSignalSpy(model.modelReset)
    datasets = QSignalSpy(model.dataset_changed)
    pages = QSignalSpy(model.pagination_changed)
    model.insert_rows(position, 2)
    assert model.get_current_page() == position // 3
    assert model.get_dataframe().height == 8
    assert model.raw_value(model.index(position % 3, 0)) is None
    assert model.headerData(position % 3, Qt.Orientation.Vertical) == str(position + 1)
    assert len(resets) == len(datasets) == len(pages) == 1
    assert model.session.revision == 1 and len(model._undo_stack) == 1
    model.undo()
    assert model.get_dataframe()["id"].to_list() == list(range(6))
    assert model.get_current_page() < model.get_max_pages()
    model.redo()
    assert model.get_dataframe().height == 8
    assert tester.model() is model
    assert not [record for record in qtlog.records if "FAIL!" in record.message]


def test_paste_and_prepared_commit_preserve_format_and_signal_contract(qapp):
    frame = pl.DataFrame(schema={"id": pl.UInt64, "text": pl.String})
    model = PolarsTableModel(frame, chunk_size=1)
    model.set_column_format("id", "number", 2, True)
    model.insert_pasted_rows(0, str(2**64 - 1), ["id"])
    assert model.raw_value(model.index(0, 0)) == 2**64 - 1
    prepared = insert_tsv_rows(model.get_dataframe(), 1, "second", ["text"])
    model.commit_inserted_frame(prepared, 1)
    assert model.session.revision == 2 and len(model._undo_stack) == 2
    assert model.get_current_page() == 1
    assert model.column_format("id")["thousands"]
    assert model.raw_value(model.index(0, 1)) == "second"


def test_invalid_insert_emits_nothing_and_preserves_redo_and_page(qapp):
    model = PolarsTableModel(
        pl.DataFrame({"id": pl.Series([1, 2], dtype=pl.UInt8)}), chunk_size=1
    )
    model.insert_rows(1)
    model.undo()
    revision, page = model.session.revision, model.get_current_page()
    resets = QSignalSpy(model.modelReset)
    changes = QSignalSpy(model.dataset_changed)
    for operation in (
        lambda: model.insert_pasted_rows(1, "3\n256", ["id"]),
        lambda: model.insert_rows(-1),
        lambda: model.commit_inserted_frame(pl.DataFrame({"wrong": [3]}), 0),
        lambda: model.commit_inserted_frame(model.get_dataframe(), 0),
    ):
        with pytest.raises(ValueError):
            operation()
    assert model.session.revision == revision and model.get_current_page() == page
    assert model.session.can_redo
    assert not resets and not changes
