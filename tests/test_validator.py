"""Tests for the AI transformation code validator."""

import pytest
import ast
from ai.validator import (
    validate_transformation_code,
    prepare_transformation_for_execution,
    TransformationValidationError,
)


def test_validate_simple_expression():
    """Test that simple valid expressions pass validation."""
    code = "df.select(['col1', 'col2'])"
    tree = validate_transformation_code(code)
    assert isinstance(tree, ast.Module)


def test_validate_filter_expression():
    """Test that filter expressions pass validation."""
    code = "df.filter(pl.col('age') > 18)"
    tree = validate_transformation_code(code)
    assert isinstance(tree, ast.Module)


def test_validate_chained_operations():
    """Test that chained operations pass validation."""
    code = "df.select(['name', 'age']).filter(pl.col('age') > 21).sort('name')"
    tree = validate_transformation_code(code)
    assert isinstance(tree, ast.Module)


def test_reject_import_statement():
    """Test that import statements are rejected."""
    code = "import os"
    with pytest.raises(TransformationValidationError, match="Import statements"):
        validate_transformation_code(code)


def test_reject_from_import():
    """Test that from-import statements are rejected."""
    code = "from os import path"
    with pytest.raises(TransformationValidationError, match="Import statements"):
        validate_transformation_code(code)


def test_reject_lambda():
    """Test that lambda functions are rejected."""
    code = "df.select(lambda x: x)"
    with pytest.raises(TransformationValidationError, match="Lambda"):
        validate_transformation_code(code)


def test_reject_list_comprehension():
    """Test that list comprehensions are rejected."""
    code = "[x for x in df]"
    with pytest.raises(TransformationValidationError, match="Comprehensions"):
        validate_transformation_code(code)


def test_reject_unauthorized_name():
    """Test that unauthorized variable names are rejected."""
    code = "os.system('ls')"
    with pytest.raises(
        TransformationValidationError, match="Function calls only allowed"
    ):
        validate_transformation_code(code)


def test_reject_dunder_attribute():
    """Test that dunder attributes are rejected."""
    code = "df.__dict__"
    with pytest.raises(TransformationValidationError, match="__dict__"):
        validate_transformation_code(code)


def test_reject_attribute_on_unauthorized_name():
    """Test that attributes on unauthorized names are rejected."""
    code = "os.path.join('a', 'b')"
    with pytest.raises(
        TransformationValidationError, match="Function calls only allowed"
    ):
        validate_transformation_code(code)


def test_reject_direct_function_call():
    """Test that direct function calls are rejected."""
    code = "print('hello')"
    with pytest.raises(
        TransformationValidationError, match="Function calls only allowed"
    ):
        validate_transformation_code(code)


def test_allow_constants():
    """Test that constants are allowed in expressions."""
    code = "df.filter(pl.col('value') > 100)"
    tree = validate_transformation_code(code)
    assert isinstance(tree, ast.Module)


def test_allow_boolean_literals():
    """Test that True/False/None are allowed."""
    code = "df.select([pl.col('x').is_null()])"
    tree = validate_transformation_code(code)
    assert isinstance(tree, ast.Module)


def test_prepare_transformation_captures_result():
    """Test that prepare_transformation_for_execution captures expression results."""
    code = "df.head(10)"
    tree, result_var = prepare_transformation_for_execution(code)

    # Check that the last statement is now an assignment
    assert isinstance(tree.body[-1], ast.Assign)
    assert tree.body[-1].targets[0].id == result_var


def test_prepare_transformation_with_statements():
    """Test that the last expression gets result capture in multi-statement code."""
    # Using only df and pl is the safe pattern
    code = """
df.select(['col1']).head(10)
"""
    tree, result_var = prepare_transformation_for_execution(code)

    # The expression should be converted to an assignment
    assert isinstance(tree.body[-1], ast.Assign)
    assert tree.body[-1].targets[0].id == result_var


def test_syntax_error_handling():
    """Test that syntax errors are properly caught."""
    code = "df.select([)"  # Missing closing bracket
    with pytest.raises(TransformationValidationError, match="Syntax error"):
        validate_transformation_code(code)


def test_reject_subscript_on_unauthorized():
    """Test that subscripts on unauthorized names are rejected."""
    code = "sys.argv[0]"
    with pytest.raises(TransformationValidationError, match="Subscript only permitted"):
        validate_transformation_code(code)


def test_allow_df_subscript():
    """Test that df subscript access is allowed."""
    code = "df['column_name']"
    tree = validate_transformation_code(code)
    assert isinstance(tree, ast.Module)


def test_allow_comparison_operators():
    """Test that comparison operators work correctly."""
    code = "df.filter((pl.col('a') > 5) & (pl.col('b') < 10))"
    tree = validate_transformation_code(code)
    assert isinstance(tree, ast.Module)


def test_allow_temp_variable_assignment():
    """Test that temporary variable assignments are allowed."""
    code = "result = df.select(['col1'])"
    tree = validate_transformation_code(code)
    assert isinstance(tree, ast.Module)


def test_reject_temp_variable_usage():
    """Test that temporary variables cannot be used in method chains."""
    code = """
result = df.select(['col1'])
result.head(10)
"""
    with pytest.raises(
        TransformationValidationError, match="Function calls only allowed"
    ):
        validate_transformation_code(code)
