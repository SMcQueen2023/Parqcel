import json

import polars as pl
import pytest
from polars.testing import assert_frame_equal

from parqcel.core.transformations import (
    TransformationValidationError,
    execute_transformation,
    parse_transformation,
    plan_to_dict,
)


@pytest.fixture
def frame():
    return pl.DataFrame(
        {"name": ["a", "b", "c"], "amount": [3, 1, 2], "active": [True, False, True]}
    )


def test_filter_select_sort_and_head_leave_input_unchanged(frame):
    original = frame.clone()
    result = execute_transformation(
        frame,
        "df.filter(pl.col('active') & (pl.col('amount') > 1)).select(['name', 'amount']).sort('amount', descending=True).head(1)",
    )
    assert result.to_dict(as_series=False) == {"name": ["a"], "amount": [3]}
    assert_frame_equal(frame, original)


def test_with_columns_arithmetic_cast_alias_drop_and_rename(frame):
    result = execute_transformation(
        frame,
        "df.with_columns((pl.col('amount') * 2).cast(pl.Float64).alias('double'), extra=pl.col('amount') + 1).drop('active').rename({'name': 'label'})",
    )
    assert result.columns == ["label", "amount", "double", "extra"]
    assert result["double"].to_list() == [6.0, 2.0, 4.0]
    assert result["extra"].to_list() == [4, 2, 3]


def test_null_membership_and_aggregations():
    frame = pl.DataFrame({"a": [1, None, 3]})
    result = execute_transformation(
        frame,
        "df.with_columns(pl.col('a').fill_null(2)).filter(pl.col('a').is_in([2, 3])).select(pl.col('a').sum())",
    )
    assert result.item() == 5
    nulls = execute_transformation(frame, "df.filter(pl.col('a').is_null())")
    assert nulls.height == 1


def test_unary_arithmetic_and_boolean_expressions(frame):
    result = execute_transformation(
        frame,
        "df.filter(~pl.col('active')).select((-pl.col('amount')).alias('negative'), (+pl.col('amount')).alias('positive'))",
    )
    assert result.to_dict(as_series=False) == {"negative": [-1], "positive": [1]}


def test_dataframe_subscript_and_result_assignment_return_frames(frame):
    assert execute_transformation(frame, "result = df['name']").columns == ["name"]
    assert execute_transformation(frame, "df = df.tail(n=1)")["name"].to_list() == ["c"]


def test_structured_plan_and_roundtrip(frame):
    payload = {
        "operations": [
            {
                "op": "filter",
                "predicate": {
                    "op": "gt",
                    "args": [{"op": "col", "args": ["amount"]}, 1],
                },
            },
            {"op": "sort", "columns": ["amount"], "descending": False},
            {"op": "select", "columns": ["name"]},
        ]
    }
    plan = parse_transformation(payload)
    for representation in (payload, json.dumps(payload), plan, plan_to_dict(plan)):
        assert execute_transformation(frame, representation)["name"].to_list() == [
            "c",
            "a",
        ]


@pytest.mark.parametrize(
    "code",
    [
        "import os",
        "from os import path",
        "__import__('os')",
        "open('stolen', 'w')",
        "df()",
        "pl()",
        "pl.read_csv('secret.csv')",
        "pl.read_parquet('https://example.com/data')",
        "df.write_csv('output.csv')",
        "df.head().write_parquet('output.parquet')",
        "df.select(pl.read_csv('secret.csv'))",
        "df.select(pl.col('amount').map_elements(pl.read_csv))",
        "df.map_rows(pl.read_csv)",
        "df.rename(pl.read_csv)",
        "df.pipe(pl.read_csv)",
        "df.filter(pl.col('amount').map_batches(lambda values: values))",
        "df.select(pl.col('amount').__class__)",
        "df._df",
        "df._df = None",
        "pl.col = pl.read_csv",
        "df.columns = ['x']",
        "df['amount'] = 2",
        "df.select(pl.col('amount').meta.serialize(file='output'))",
        "df.select(pl.col('name').str.to_lowercase.__globals__)",
        "df.select([x for x in df])",
        "df.head(**{'n': 2})",
        "df.head(n=2, n=3)",
        "df.head(); df.write_csv('output')",
        "result = df.head(); result.head()",
    ],
)
def test_rejects_capabilities_outside_plan_language(frame, code):
    with pytest.raises(TransformationValidationError):
        execute_transformation(frame, code)


@pytest.mark.parametrize(
    "plan",
    [
        {"operations": [{"op": "write_csv", "path": "output.csv"}]},
        {
            "operations": [
                {"op": "select", "columns": [{"op": "read_csv", "args": ["secret"]}]}
            ]
        },
        {"operations": [{"op": "head", "count": True}]},
        {"operations": [{"op": "head", "count": -1}]},
        {"operations": [{"op": "sort", "columns": ["amount"], "descending": ["true"]}]},
        {
            "operations": [
                {
                    "op": "select",
                    "columns": [{"op": "col", "args": ["a"], "callback": "x"}],
                }
            ]
        },
        {
            "operations": [
                {"op": "select", "columns": [{"op": "lit", "args": [float("nan")]}]}
            ]
        },
        {
            "operations": [
                {"op": "select", "columns": [{"op": "lit", "args": [object()]}]}
            ]
        },
    ],
)
def test_rejects_malformed_or_unsafe_structured_plans(frame, plan):
    with pytest.raises(TransformationValidationError):
        execute_transformation(frame, plan)


def test_validates_entire_plan_before_running_any_operation(frame, monkeypatch):
    calls = []
    monkeypatch.setattr(
        pl.DataFrame, "select", lambda *args, **kwargs: calls.append(True)
    )
    with pytest.raises(TransformationValidationError):
        execute_transformation(
            frame,
            {
                "operations": [
                    {"op": "select", "columns": ["name"]},
                    {"op": "write_csv", "path": "output"},
                ]
            },
        )
    assert calls == []


def test_invalid_chain_never_invokes_filesystem_method(frame, monkeypatch):
    calls = []
    monkeypatch.setattr(
        pl.DataFrame, "write_csv", lambda *args, **kwargs: calls.append(True)
    )
    with pytest.raises(TransformationValidationError):
        execute_transformation(frame, "df.head().write_csv('output.csv')")
    assert calls == []


def test_rejects_excessive_complexity(frame):
    with pytest.raises(TransformationValidationError, match="at most|complex"):
        execute_transformation(frame, {"operations": [{"op": "head", "count": 1}] * 33})
