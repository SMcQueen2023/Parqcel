"""Compatibility validation API backed by the declarative transformation parser.

New callers should use ``execute_transformation`` from the core module. These
helpers retain AST inspection for older callers; application execution never
compiles or executes generated Python.
"""

from __future__ import annotations

import ast

from parqcel.core.transformations import (
    TransformationValidationError,
    parse_transformation,
)

__all__ = [
    "TransformationValidationError",
    "validate_transformation_code",
    "prepare_transformation_for_execution",
]


def validate_transformation_code(code: str) -> ast.Module:
    """Validate the supported Polars subset and return its AST for inspection."""
    parse_transformation(code)
    try:
        return ast.parse(code, mode="exec")
    except SyntaxError as exc:
        raise TransformationValidationError(f"Syntax error: {exc}") from exc


def prepare_transformation_for_execution(
    code: str, result_var_name: str = "__parqcel_result__"
) -> tuple[ast.Module, str]:
    """Legacy AST result capture; prefer the core's data-only executor."""
    if not result_var_name.isidentifier():
        raise TransformationValidationError("Result variable must be an identifier")
    tree = validate_transformation_code(code)
    if tree.body and isinstance(tree.body[-1], ast.Expr):
        tree.body[-1] = ast.Assign(
            targets=[ast.Name(id=result_var_name, ctx=ast.Store())],
            value=tree.body[-1].value,
        )
    return ast.fix_missing_locations(tree), result_var_name
