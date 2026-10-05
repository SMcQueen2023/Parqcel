"""Declarative dataframe transformations, with a restricted Polars syntax adapter.

Suggestions are parsed as data. No generated Python is compiled or executed, and
operation names never control Python attribute lookup. This limits capabilities,
not the memory or CPU required by a legitimate dataframe operation.
"""

from __future__ import annotations

import ast
import json
import math
import operator
from dataclasses import dataclass
from typing import Any, Callable, Literal, Mapping, NoReturn, cast

import polars as pl


class TransformationValidationError(ValueError):
    """The suggestion is outside the supported transformation language."""


@dataclass(frozen=True)
class Expression:
    """An allowlisted expression and its validated, data-only arguments."""

    op: str
    args: tuple[Any, ...]


OperationKind = Literal[
    "select", "filter", "sort", "drop", "with_columns", "head", "tail", "rename"
]


@dataclass(frozen=True)
class Operation:
    op: OperationKind
    expressions: tuple[Expression, ...] = ()
    columns: tuple[str, ...] = ()
    descending: tuple[bool, ...] = ()
    count: int = 5
    renames: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class TransformationPlan:
    operations: tuple[Operation, ...]


_BINARY: dict[str, Callable[[pl.Expr, pl.Expr], pl.Expr]] = {
    "add": operator.add,
    "sub": operator.sub,
    "mul": operator.mul,
    "div": operator.truediv,
    "floordiv": operator.floordiv,
    "mod": operator.mod,
    "eq": operator.eq,
    "ne": operator.ne,
    "lt": operator.lt,
    "le": operator.le,
    "gt": operator.gt,
    "ge": operator.ge,
    "and": operator.and_,
    "or": operator.or_,
    "xor": operator.xor,
}
_UNARY: dict[str, Callable[[pl.Expr], pl.Expr]] = {
    "neg": operator.neg,
    "pos": lambda expr: expr,
    "not": operator.invert,
}
_NO_ARG_METHODS = {
    "is_null",
    "is_not_null",
    "is_nan",
    "is_not_nan",
    "is_finite",
    "abs",
    "sum",
    "mean",
    "min",
    "max",
    "count",
    "n_unique",
    "first",
    "last",
}
_DTYPES = {
    "Int8": pl.Int8,
    "Int16": pl.Int16,
    "Int32": pl.Int32,
    "Int64": pl.Int64,
    "UInt8": pl.UInt8,
    "UInt16": pl.UInt16,
    "UInt32": pl.UInt32,
    "UInt64": pl.UInt64,
    "Float32": pl.Float32,
    "Float64": pl.Float64,
    "String": pl.String,
    "Utf8": pl.String,
    "Boolean": pl.Boolean,
    "Date": pl.Date,
}
_MAX_TEXT = 16_000
_MAX_NODES = 512
_MAX_DEPTH = 32
_MAX_STEPS = 32


def _fail(message: str) -> NoReturn:
    raise TransformationValidationError(message)


def _check_data(value: Any, depth: int = 0, budget: list[int] | None = None) -> None:
    """Reject non-JSON values and excessive nesting before schema processing."""
    if budget is None:
        budget = [_MAX_NODES]
    budget[0] -= 1
    if depth > _MAX_DEPTH or budget[0] < 0:
        _fail("Transformation is too complex")
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                _fail("Object keys must be strings")
            _check_data(item, depth + 1, budget)
    elif type(value) is list:
        for item in value:
            _check_data(item, depth + 1, budget)
    elif value is None or type(value) in (str, int, float, bool):
        if isinstance(value, str) and len(value) > _MAX_TEXT:
            _fail("Literal string is too long")
        if isinstance(value, float) and not math.isfinite(value):
            _fail("Numeric literals must be finite")
    else:
        _fail("Transformation arguments must be JSON data")


def _object(value: Any, required: set[str], optional: set[str] | None = None) -> dict:
    if type(value) is not dict:
        _fail("Expected an object")
    if not required <= value.keys() or value.keys() - required - (optional or set()):
        _fail(f"Expected fields {sorted(required)}; unsupported or missing fields")
    return value


def _string(value: Any) -> str:
    if type(value) is not str or not value:
        _fail("Expected a non-empty string")
    return cast(str, value)


def _strings(value: Any) -> tuple[str, ...]:
    if type(value) is str:
        return (_string(value),)
    if type(value) is not list or not value:
        _fail("Expected a non-empty list of column names")
    return tuple(_string(v) for v in value)


def _scalar(value: Any) -> Any:
    if value is not None and type(value) not in (str, int, float, bool):
        _fail("Expected a scalar literal")
    return value


def _expression(value: Any) -> Expression:
    if type(value) is not dict:
        return Expression("lit", (_scalar(value),))
    data = _object(value, {"op", "args"})
    op, args = data["op"], data["args"]
    if type(op) is not str or type(args) is not list:
        _fail("Expressions require a string op and a list of args")
    if op == "col" and len(args) == 1:
        return Expression(op, (_string(args[0]),))
    if op == "all" and not args:
        return Expression(op, ())
    if op == "lit" and len(args) == 1:
        return Expression(op, (_scalar(args[0]),))
    if op in _BINARY and len(args) == 2:
        return Expression(op, tuple(_expression(a) for a in args))
    if (op in _UNARY or op in _NO_ARG_METHODS) and len(args) == 1:
        return Expression(op, (_expression(args[0]),))
    if op in {"alias", "cast"} and len(args) == 2:
        name = _string(args[1])
        if op == "cast" and name not in _DTYPES:
            _fail(f"Unsupported dtype: {name}")
        return Expression(op, (_expression(args[0]), name))
    if op in {"fill_null", "fill_nan"} and len(args) == 2:
        return Expression(op, tuple(_expression(a) for a in args))
    if op == "round" and len(args) == 2:
        if type(args[1]) is not int or not 0 <= args[1] <= 15:
            _fail("round decimals must be an integer from 0 to 15")
        return Expression(op, (_expression(args[0]), args[1]))
    if op == "is_in" and len(args) == 2 and type(args[1]) is list:
        return Expression(
            op, (_expression(args[0]), tuple(_scalar(v) for v in args[1]))
        )
    _fail(f"Unsupported expression or arguments: {op}")
    raise AssertionError("unreachable")


def _parse_plan(data: Any) -> TransformationPlan:
    _check_data(data)
    data = _object(data, {"operations"})
    steps = data["operations"]
    if type(steps) is not list or len(steps) > _MAX_STEPS:
        _fail(f"operations must be a list with at most {_MAX_STEPS} entries")
    operations = []
    for step in steps:
        if type(step) is not dict or type(step.get("op")) is not str:
            _fail("Each operation requires a string op")
        op = step["op"]
        if op in {"select", "with_columns"}:
            key = "columns" if op == "select" else "expressions"
            _object(step, {"op", key})
            values = step[key]
            if type(values) is not list or not values:
                _fail(f"{key} must be a non-empty list")
            exprs = tuple(
                Expression("col", (_string(v),)) if type(v) is str else _expression(v)
                for v in values
            )
            operations.append(Operation(cast(OperationKind, op), expressions=exprs))
        elif op == "filter":
            _object(step, {"op", "predicate"})
            operations.append(
                Operation("filter", expressions=(_expression(step["predicate"]),))
            )
        elif op in {"sort", "drop"}:
            _object(step, {"op", "columns"}, {"descending"} if op == "sort" else None)
            columns = _strings(step["columns"])
            descending = step.get("descending", False)
            if type(descending) is bool:
                directions = (descending,) * len(columns)
            elif (
                type(descending) is list
                and len(descending) == len(columns)
                and all(type(v) is bool for v in descending)
            ):
                directions = tuple(descending)
            else:
                _fail("descending must be a boolean or one boolean per sort column")
            operations.append(
                Operation(
                    cast(OperationKind, op), columns=columns, descending=directions
                )
            )
        elif op in {"head", "tail"}:
            _object(step, {"op"}, {"count"})
            count = step.get("count", 5)
            if type(count) is not int or not 0 <= count <= 1_000_000:
                _fail("Row count must be an integer from 0 to 1000000")
            operations.append(Operation(cast(OperationKind, op), count=count))
        elif op == "rename":
            _object(step, {"op", "mapping"})
            mapping = step["mapping"]
            if type(mapping) is not dict or not mapping:
                _fail("rename requires a non-empty mapping of column names")
            operations.append(
                Operation(
                    "rename",
                    renames=tuple((_string(k), _string(v)) for k, v in mapping.items()),
                )
            )
        else:
            _fail(f"Unsupported dataframe operation: {op}")
    return TransformationPlan(tuple(operations))


def _literal(node: ast.AST) -> Any:
    """Read literal data without evaluating Python."""
    if isinstance(node, ast.Constant):
        return _scalar(node.value)
    if isinstance(node, (ast.List, ast.Tuple)):
        return [_literal(item) for item in node.elts]
    if isinstance(node, ast.Dict):
        pairs = [
            (_literal(k), _literal(v))
            for k, v in zip(node.keys, node.values)
            if k is not None
        ]
        if len(pairs) != len(node.keys) or any(type(k) is not str for k, _ in pairs):
            _fail("Only literal string keys are supported")
        return dict(pairs)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        value = _literal(node.operand)
        if type(value) in (int, float):
            return -value if isinstance(node.op, ast.USub) else value
    _fail("Only literal arguments are supported here")


def _expr_data(op: str, *args: Any) -> dict:
    return {"op": op, "args": list(args)}


_AST_BINARY = {
    ast.Add: "add",
    ast.Sub: "sub",
    ast.Mult: "mul",
    ast.Div: "div",
    ast.FloorDiv: "floordiv",
    ast.Mod: "mod",
    ast.BitAnd: "and",
    ast.BitOr: "or",
    ast.BitXor: "xor",
    ast.Eq: "eq",
    ast.NotEq: "ne",
    ast.Lt: "lt",
    ast.LtE: "le",
    ast.Gt: "gt",
    ast.GtE: "ge",
}


def _ast_expression(node: ast.AST) -> dict:
    if isinstance(node, ast.Constant):
        return _expr_data("lit", _scalar(node.value))
    if (
        isinstance(node, ast.Subscript)
        and isinstance(node.value, ast.Name)
        and node.value.id == "df"
    ):
        return _expr_data("col", _string(_literal(node.slice)))
    if isinstance(node, ast.BinOp) and type(node.op) in _AST_BINARY:
        return _expr_data(
            _AST_BINARY[type(node.op)],
            _ast_expression(node.left),
            _ast_expression(node.right),
        )
    if (
        isinstance(node, ast.Compare)
        and len(node.ops) == 1
        and type(node.ops[0]) in _AST_BINARY
    ):
        return _expr_data(
            _AST_BINARY[type(node.ops[0])],
            _ast_expression(node.left),
            _ast_expression(node.comparators[0]),
        )
    if isinstance(node, ast.UnaryOp) and isinstance(
        node.op, (ast.USub, ast.UAdd, ast.Invert)
    ):
        op = {ast.USub: "neg", ast.UAdd: "pos", ast.Invert: "not"}[type(node.op)]
        return _expr_data(op, _ast_expression(node.operand))
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        method = node.func.attr
        if node.keywords:
            _fail("Expression keyword arguments are not supported")
        if isinstance(node.func.value, ast.Name) and node.func.value.id == "pl":
            if method in {"col", "lit"} and len(node.args) == 1:
                return _expr_data(method, _literal(node.args[0]))
            if method == "all" and not node.args:
                return _expr_data("all")
            _fail(f"Unsupported Polars function: {method}")
        receiver = _ast_expression(node.func.value)
        if method in _NO_ARG_METHODS and not node.args:
            return _expr_data(method, receiver)
        if method == "round" and not node.args:
            return _expr_data("round", receiver, 0)
        if method in {"alias", "is_in", "round"} and len(node.args) == 1:
            return _expr_data(method, receiver, _literal(node.args[0]))
        if method in {"fill_null", "fill_nan"} and len(node.args) == 1:
            return _expr_data(method, receiver, _ast_expression(node.args[0]))
        if method == "cast" and len(node.args) == 1:
            dtype = node.args[0]
            if (
                isinstance(dtype, ast.Attribute)
                and isinstance(dtype.value, ast.Name)
                and dtype.value.id == "pl"
            ):
                return _expr_data("cast", receiver, dtype.attr)
        _fail(f"Unsupported expression method: {method}")
    _fail(f"Unsupported expression syntax: {type(node).__name__}")
    raise AssertionError("unreachable")


def _ast_steps(node: ast.AST) -> list[dict]:
    if isinstance(node, ast.Name) and node.id == "df":
        return []
    if (
        isinstance(node, ast.Subscript)
        and isinstance(node.value, ast.Name)
        and node.value.id == "df"
    ):
        columns = _literal(node.slice)
        return [{"op": "select", "columns": list(_strings(columns))}]
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
        _fail("Expected a supported dataframe method on df")
    node = cast(ast.Call, node)
    func = cast(ast.Attribute, node.func)
    steps = _ast_steps(func.value)
    op = func.attr
    kwargs = {}
    for keyword in node.keywords:
        if keyword.arg is None or keyword.arg in kwargs:
            _fail("Expanded or duplicate keyword arguments are not supported")
        kwargs[keyword.arg] = keyword.value
    args = list(node.args)
    if len(args) == 1 and isinstance(args[0], (ast.List, ast.Tuple)):
        args = list(args[0].elts)
    if op in {"select", "with_columns"}:
        expressions = [
            (
                _ast_expression(arg)
                if not (isinstance(arg, ast.Constant) and type(arg.value) is str)
                else arg.value
            )
            for arg in args
        ]
        if op == "select" and kwargs:
            _fail("select keyword arguments are not supported")
        for name, value in kwargs.items():
            expressions.append(_expr_data("alias", _ast_expression(value), name))
        steps.append(
            {"op": op, "columns" if op == "select" else "expressions": expressions}
        )
    elif op == "filter" and len(args) == 1 and not kwargs:
        steps.append({"op": op, "predicate": _ast_expression(args[0])})
    elif op in {"sort", "drop"} and not (
        set(kwargs) - ({"descending"} if op == "sort" else set())
    ):
        step = {"op": op, "columns": [_literal(arg) for arg in args]}
        if "descending" in kwargs:
            step["descending"] = _literal(kwargs["descending"])
        steps.append(step)
    elif op in {"head", "tail"} and len(args) <= 1 and not (set(kwargs) - {"n"}):
        if args and kwargs:
            _fail("Row count was supplied twice")
        count_node = args[0] if args else kwargs.get("n")
        steps.append(
            {"op": op, "count": _literal(count_node) if count_node is not None else 5}
        )
    elif op == "rename" and len(args) == 1 and not kwargs:
        steps.append({"op": op, "mapping": _literal(args[0])})
    else:
        _fail(f"Unsupported dataframe method or arguments: {op}")
    return steps


def _parse_code(code: str) -> TransformationPlan:
    try:
        tree = ast.parse(code, mode="exec")
    except (SyntaxError, RecursionError) as exc:
        raise TransformationValidationError(
            f"Syntax error in transformation: {exc}"
        ) from exc
    if sum(1 for _ in ast.walk(tree)) > _MAX_NODES:
        _fail("Transformation is too complex")
    if len(tree.body) != 1:
        _fail("Use one dataframe expression or a single result assignment")
    statement = tree.body[0]
    if isinstance(statement, ast.Expr):
        value = statement.value
    elif (
        isinstance(statement, ast.Assign)
        and len(statement.targets) == 1
        and isinstance(statement.targets[0], ast.Name)
        and statement.targets[0].id in {"df", "result"}
    ):
        value = statement.value
    else:
        _fail("Only a dataframe expression or assignment to df/result is supported")
    try:
        return _parse_plan({"operations": _ast_steps(value)})
    except RecursionError as exc:
        raise TransformationValidationError("Transformation is too complex") from exc


def _expression_data(expr: Expression) -> dict:
    return _expr_data(
        expr.op,
        *[
            (
                _expression_data(arg)
                if isinstance(arg, Expression)
                else list(arg) if isinstance(arg, tuple) else arg
            )
            for arg in expr.args
        ],
    )


def plan_to_dict(plan: TransformationPlan) -> dict:
    """Serialize a plan to the public JSON schema."""
    steps = []
    for step in plan.operations:
        data: dict[str, Any] = {"op": step.op}
        if step.op in {"select", "with_columns"}:
            data["columns" if step.op == "select" else "expressions"] = [
                _expression_data(expr) for expr in step.expressions
            ]
        elif step.op == "filter":
            if len(step.expressions) != 1:
                _fail("filter requires one predicate")
            data["predicate"] = _expression_data(step.expressions[0])
        elif step.op in {"sort", "drop"}:
            data["columns"] = list(step.columns)
            if step.op == "sort":
                data["descending"] = list(step.descending)
        elif step.op in {"head", "tail"}:
            data["count"] = step.count
        elif step.op == "rename":
            data["mapping"] = dict(step.renames)
        steps.append(data)
    return {"operations": steps}


def parse_transformation(
    code_or_plan: str | TransformationPlan | Mapping[str, Any],
) -> TransformationPlan:
    """Validate a structured plan or adapt a restricted Polars expression to it."""
    if isinstance(code_or_plan, TransformationPlan):
        return _parse_plan(plan_to_dict(code_or_plan))
    if isinstance(code_or_plan, str):
        if len(code_or_plan) > _MAX_TEXT:
            _fail("Transformation text is too long")
        if code_or_plan.lstrip().startswith("{"):
            try:
                data = json.loads(code_or_plan)
            except (ValueError, RecursionError) as exc:
                raise TransformationValidationError(
                    "Invalid transformation JSON"
                ) from exc
            return _parse_plan(data)
        return _parse_code(code_or_plan)
    return _parse_plan(code_or_plan)


def _compile_expression(expr: Expression) -> pl.Expr:
    op, args = expr.op, expr.args
    if op == "col":
        return pl.col(args[0])
    if op == "all":
        return pl.all()
    if op == "lit":
        return pl.lit(args[0])
    if op in _BINARY:
        return _BINARY[op](_compile_expression(args[0]), _compile_expression(args[1]))
    if op in _UNARY:
        return _UNARY[op](_compile_expression(args[0]))
    value = _compile_expression(args[0])
    # Explicit dispatch: suggestions cannot name any other attribute or method.
    if op == "alias":
        return value.alias(args[1])
    if op == "cast":
        return value.cast(_DTYPES[args[1]])
    if op == "fill_null":
        return value.fill_null(_compile_expression(args[1]))
    if op == "fill_nan":
        return value.fill_nan(_compile_expression(args[1]))
    if op == "round":
        return value.round(args[1])
    if op == "is_in":
        return value.is_in(list(args[1]))
    methods = {
        "is_null": value.is_null,
        "is_not_null": value.is_not_null,
        "is_nan": value.is_nan,
        "is_not_nan": value.is_not_nan,
        "is_finite": value.is_finite,
        "abs": value.abs,
        "sum": value.sum,
        "mean": value.mean,
        "min": value.min,
        "max": value.max,
        "count": value.count,
        "n_unique": value.n_unique,
        "first": value.first,
        "last": value.last,
    }
    return methods[op]()


def execute_transformation(
    df: pl.DataFrame, code_or_plan: str | TransformationPlan | Mapping[str, Any]
) -> pl.DataFrame:
    """Execute only owned Polars operations, leaving the supplied frame unchanged."""
    plan = parse_transformation(code_or_plan)
    result = df.clone()
    for step in plan.operations:
        if step.op == "select":
            result = result.select(
                [_compile_expression(expr) for expr in step.expressions]
            )
        elif step.op == "filter":
            result = result.filter(_compile_expression(step.expressions[0]))
        elif step.op == "sort":
            result = result.sort(list(step.columns), descending=list(step.descending))
        elif step.op == "drop":
            result = result.drop(list(step.columns))
        elif step.op == "with_columns":
            result = result.with_columns(
                [_compile_expression(expr) for expr in step.expressions]
            )
        elif step.op == "head":
            result = result.head(step.count)
        elif step.op == "tail":
            result = result.tail(step.count)
        elif step.op == "rename":
            result = result.rename(dict(step.renames))
    return result
