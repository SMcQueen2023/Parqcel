"""AST-based code validator for safe execution of LLM-generated transformations.

This module provides AST validation for executing Python code snippets that operate
on Polars DataFrames. It restricts the allowed syntax to prevent arbitrary code execution.

SECURITY WARNING:
    This validator is NOT a complete sandbox. It should be used as a defense-in-depth
    measure alongside other security controls. The validation rules are:
    
    - Only 'df', 'pl', True, False, None are allowed as free names
    - No import statements
    - No lambdas or comprehensions
    - No await/async
    - No access to dunder attributes (__globals__, __dict__, etc.)
    - Attribute access and calls only permitted on 'df' or 'pl' chains
    
    Known limitations:
    - Complex nested expressions may have edge cases
    - Does not protect against resource exhaustion (infinite loops, memory)
    - Relies on Python's exec() which is inherently risky
    
    For production use, consider:
    - Process-based isolation
    - Resource limits (timeout, memory)
    - Audit logging of executed code
    - RestrictedPython or similar sandboxing libraries
"""

from __future__ import annotations

import ast
from typing import Set


class TransformationValidationError(ValueError):
    """Raised when transformation code fails AST validation."""


def _get_root_name(node: ast.AST) -> str | None:
    """Extract the root variable name from a chain of attribute/subscript/call operations.
    
    For example:
        df.select() -> 'df'
        pl.col('x') -> 'pl'
        df['column'].sum() -> 'df'
    
    Args:
        node: An AST node to analyze
        
    Returns:
        The root identifier name, or None if not a Name node at the root
    """
    cur = node
    while True:
        if isinstance(cur, ast.Attribute):
            cur = cur.value
        elif isinstance(cur, ast.Subscript):
            cur = cur.value
        elif isinstance(cur, ast.Call):
            cur = cur.func
        else:
            break
    return cur.id if isinstance(cur, ast.Name) else None


class _TransformationValidator(ast.NodeVisitor):
    """AST visitor that enforces safety rules for transformation code."""
    
    ALLOWED_NAMES: Set[str] = {"df", "pl", "True", "False", "None"}
    DANGEROUS_ATTRS: Set[str] = {
        "__globals__",
        "__dict__",
        "__class__",
        "__mro__",
        "__subclasses__",
        "__getattribute__",
        "__builtins__",
    }
    
    ALLOWED_NODE_TYPES = (
        ast.Module,
        ast.Expr,
        ast.Assign,
        ast.Name,
        ast.Load,
        ast.Store,
        ast.Attribute,
        ast.Subscript,
        ast.Constant,
        ast.Call,
        ast.Tuple,
        ast.List,
        ast.Dict,
        ast.Set,
        ast.Compare,
        ast.BoolOp,
        ast.BinOp,
        ast.UnaryOp,
        ast.keyword,
        ast.Slice,
        # operators
        ast.Gt,
        ast.GtE,
        ast.Lt,
        ast.LtE,
        ast.Eq,
        ast.NotEq,
        ast.In,
        ast.NotIn,
        ast.And,
        ast.Or,
        ast.Add,
        ast.Sub,
        ast.Mult,
        ast.Div,
        ast.Mod,
        ast.Pow,
        ast.USub,
        ast.UAdd,
        # Bitwise operators (for Polars boolean operations using & and |)
        ast.BitAnd,
        ast.BitOr,
        ast.BitXor,
        ast.Invert,
    )
    
    def generic_visit(self, node: ast.AST) -> None:
        """Visit any node and check if its type is allowed."""
        if not isinstance(node, self.ALLOWED_NODE_TYPES):
            raise TransformationValidationError(
                f"Unsupported syntax: {type(node).__name__}"
            )
        super().generic_visit(node)
    
    def visit_Import(self, node: ast.Import) -> None:
        """Reject import statements."""
        raise TransformationValidationError(
            "Import statements are not allowed in transformation code"
        )
    
    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """Reject from-import statements."""
        raise TransformationValidationError(
            "Import statements are not allowed in transformation code"
        )
    
    def visit_Lambda(self, node: ast.Lambda) -> None:
        """Reject lambda functions."""
        raise TransformationValidationError(
            "Lambda functions are not allowed in transformation code"
        )
    
    def visit_ListComp(self, node: ast.ListComp) -> None:
        """Reject list comprehensions."""
        raise TransformationValidationError(
            "Comprehensions are not allowed in transformation code"
        )
    
    def visit_DictComp(self, node: ast.DictComp) -> None:
        """Reject dict comprehensions."""
        raise TransformationValidationError(
            "Comprehensions are not allowed in transformation code"
        )
    
    def visit_SetComp(self, node: ast.SetComp) -> None:
        """Reject set comprehensions."""
        raise TransformationValidationError(
            "Comprehensions are not allowed in transformation code"
        )
    
    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> None:
        """Reject generator expressions."""
        raise TransformationValidationError(
            "Generator expressions are not allowed in transformation code"
        )
    
    def visit_Await(self, node: ast.Await) -> None:
        """Reject await expressions."""
        raise TransformationValidationError(
            "Async/await is not allowed in transformation code"
        )
    
    def visit_Name(self, node: ast.Name) -> None:
        """Validate that only allowed names are used.
        
        Allows temporary variable assignments (Store context) since
        the validator runs in an isolated scope.
        """
        # Allow any name in Store context (assignments)
        if isinstance(node.ctx, ast.Store):
            # Still check for dunder names in assignments (handled in visit_Assign)
            self.generic_visit(node)
            return
            
        # For Load context, only allow predefined names
        if node.id not in self.ALLOWED_NAMES:
            raise TransformationValidationError(
                f"Use of name '{node.id}' is not permitted. Only {self.ALLOWED_NAMES} are allowed."
            )
        self.generic_visit(node)
    
    def visit_Attribute(self, node: ast.Attribute) -> None:
        """Validate attribute access is only on df/pl and not on dangerous attributes."""
        # Check the entire attribute chain for dangerous attributes
        cur = node
        while isinstance(cur, ast.Attribute):
            if cur.attr.startswith("__") or cur.attr in self.DANGEROUS_ATTRS:
                raise TransformationValidationError(
                    f"Access to attribute '{cur.attr}' is not permitted"
                )
            cur = cur.value
        
        # Verify the root is 'df' or 'pl'
        base = _get_root_name(node)
        if base not in ("df", "pl"):
            raise TransformationValidationError(
                f"Attribute access only permitted on 'df' or 'pl', not '{base}'"
            )
        
        self.generic_visit(node)
    
    def visit_Subscript(self, node: ast.Subscript) -> None:
        """Validate subscript operations are only on df/pl."""
        base = _get_root_name(node)
        if base not in ("df", "pl"):
            raise TransformationValidationError(
                f"Subscript only permitted on 'df' or 'pl', not '{base}'"
            )
        
        # Check if subscripting a dangerous attribute
        if isinstance(node.value, ast.Attribute):
            attr = getattr(node.value, "attr", "")
            if attr.startswith("__") or attr in self.DANGEROUS_ATTRS:
                raise TransformationValidationError(
                    f"Subscript of attribute '{attr}' is not permitted"
                )
        
        self.generic_visit(node)
    
    def visit_Call(self, node: ast.Call) -> None:
        """Validate function calls are only on df/pl chains."""
        base = _get_root_name(node)
        if base not in ("df", "pl"):
            raise TransformationValidationError(
                f"Function calls only allowed on 'df' or 'pl' chains, not '{base}'"
            )
        
        # Check for dangerous attributes in the call chain
        func = node.func
        while isinstance(func, ast.Attribute):
            if func.attr.startswith("__") or func.attr in self.DANGEROUS_ATTRS:
                raise TransformationValidationError(
                    f"Call to attribute '{func.attr}' is not permitted"
                )
            func = func.value
        
        # Reject direct function calls not on df/pl
        if isinstance(func, ast.Name) and func.id not in ("df", "pl"):
            raise TransformationValidationError(
                f"Direct function call '{func.id}()' is not permitted"
            )
        
        self.generic_visit(node)
    
    def visit_Assign(self, node: ast.Assign) -> None:
        """Validate assignments don't use dunder names."""
        for tgt in node.targets:
            if isinstance(tgt, ast.Name) and tgt.id.startswith("__"):
                raise TransformationValidationError(
                    f"Assignment to dunder name '{tgt.id}' is not allowed"
                )
        self.generic_visit(node)


def validate_transformation_code(code: str) -> ast.Module:
    """Parse and validate transformation code for safe execution.
    
    This function parses Python code and validates it against security rules
    to ensure it can be safely executed in a restricted environment.
    
    Args:
        code: Python code string to validate
        
    Returns:
        Validated and parsed AST Module
        
    Raises:
        TransformationValidationError: If code violates safety rules
        SyntaxError: If code is not valid Python
        
    Example:
        >>> tree = validate_transformation_code("df.select(['col1', 'col2'])")
        >>> # tree can now be safely compiled and executed
    """
    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError as e:
        raise TransformationValidationError(
            f"Syntax error in transformation code: {e}"
        ) from e
    
    # Run validation
    _TransformationValidator().visit(tree)
    
    return tree


def prepare_transformation_for_execution(
    code: str, result_var_name: str = "__parqcel_result__"
) -> tuple[ast.Module, str]:
    """Validate and prepare transformation code for execution.
    
    This function:
    1. Validates the code using AST analysis
    2. If the last statement is an expression, wraps it in an assignment
       to capture the result
    3. Fixes missing location information in the AST
    
    Args:
        code: Python code string to prepare
        result_var_name: Name of variable to capture result in
        
    Returns:
        Tuple of (prepared AST tree, result variable name)
        
    Raises:
        TransformationValidationError: If code violates safety rules
    """
    tree = validate_transformation_code(code)
    
    # If last node is an Expr, replace it with assignment to capture result
    if tree.body and isinstance(tree.body[-1], ast.Expr):
        expr_node = tree.body[-1]
        assign = ast.Assign(
            targets=[ast.Name(id=result_var_name, ctx=ast.Store())],
            value=expr_node.value,
        )
        tree.body[-1] = assign
    
    # Fix any missing lineno/col_offset information before compiling
    tree = ast.fix_missing_locations(tree)
    
    return tree, result_var_name
