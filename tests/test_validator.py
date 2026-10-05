"""Legacy validation uses the same capability restrictions as execution."""

import ast

import pytest

from ai.validator import (
    TransformationValidationError,
    prepare_transformation_for_execution,
    validate_transformation_code,
)


@pytest.mark.parametrize(
    "code",
    [
        "df.select(['col1', 'col2'])",
        "df.filter(pl.col('age') > 18)",
        "df.select(['name', 'age']).filter(pl.col('age') > 21).sort('name')",
        "df.select([pl.col('x').is_null()])",
        "df['column_name']",
        "df.filter((pl.col('a') > 5) & (pl.col('b') < 10))",
        "result = df.select(['col1'])",
    ],
)
def test_validate_supported_expression(code):
    assert isinstance(validate_transformation_code(code), ast.Module)


@pytest.mark.parametrize(
    "code",
    [
        "import os",
        "from os import path",
        "df.select(lambda x: x)",
        "[x for x in df]",
        "os.system('ls')",
        "df.__dict__",
        "df._df",
        "os.path.join('a', 'b')",
        "print('hello')",
        "sys.argv[0]",
        "result = df.select(['col1'])\nresult.head(10)",
        "df.write_csv('output.csv')",
        "pl.read_csv('secret.csv')",
        "df.head().write_csv('output.csv')",
        "df.select(pl.col('x').map_elements(pl.read_csv))",
        "df.columns = ['changed']",
        "pl.col = pl.read_csv",
        "df()",
        "pl()",
    ],
)
def test_reject_unsupported_or_side_effecting_code(code):
    with pytest.raises(TransformationValidationError):
        validate_transformation_code(code)


def test_prepare_transformation_captures_result():
    tree, result_var = prepare_transformation_for_execution("df.head(10)")
    assert isinstance(tree.body[-1], ast.Assign)
    assert tree.body[-1].targets[0].id == result_var


def test_syntax_error_handling():
    with pytest.raises(TransformationValidationError, match="Syntax error"):
        validate_transformation_code("df.select([)")
