from PyQt6.QtCore import QRegularExpression
from PyQt6.QtGui import QRegularExpressionValidator
from PyQt6.QtWidgets import QInputDialog, QLineEdit

# Map from filter operation to lambda for string
STRING_OPERATIONS = {
    "contains": lambda value, filter_value: filter_value.lower() in value.lower(),
    "starts with": lambda value, filter_value: value.lower().startswith(filter_value.lower()),
    "ends with": lambda value, filter_value: value.lower().endswith(filter_value.lower()),
    "equals": lambda value, filter_value: value.lower() == filter_value.lower(),
}

# Map from filter operation to lambda for numeric/date
NUMERIC_DATE_OPERATIONS = {
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    "==": lambda a, b: a == b,
    ">=": lambda a, b: a >= b,
    ">": lambda a, b: a > b,
}


class BaseFilter:
    def __init__(self, column_name, operation, filter_value):
        self.column_name = column_name
        self.operation = operation
        self.filter_value = filter_value

    def matches(self, value):
        raise NotImplementedError("Subclasses must implement this method")


class StringFilter(BaseFilter):
    def matches(self, value):
        if value is None:
            return False
        return STRING_OPERATIONS[self.operation](str(value), self.filter_value)


class NumericDateFilter(BaseFilter):
    def __init__(self, column_name, operation, filter_value, cast_func=float):
        super().__init__(column_name, operation, filter_value)
        self.cast_func = cast_func

    def matches(self, value):
        try:
            return NUMERIC_DATE_OPERATIONS[self.operation](self.cast_func(value), self.cast_func(self.filter_value))
        except Exception:
            return False


# Factory method to get filter object
def create_filter(column_name, column_dtype, operation, value):
    if column_dtype in ("string", "str"):
        return StringFilter(column_name, operation, value)
    elif column_dtype in ("int", "float", "date", "datetime"):
        # Use appropriate cast functions here if needed
        cast_func = float if column_dtype in ("int", "float") else str
        return NumericDateFilter(column_name, operation, value, cast_func=cast_func)
    else:
        raise ValueError(f"Unsupported dtype for filtering: {column_dtype}")


# GUI helpers
def get_string_filter_input(parent, column_name):
    operations = list(STRING_OPERATIONS.keys())
    op, ok = QInputDialog.getItem(parent, f"Filter {column_name}", "Operation:", operations, editable=False)
    if not ok:
        return None

    value, ok = QInputDialog.getText(parent, f"Filter {column_name}", f"Enter text to match:")
    if not ok:
        return None

    return op, value


def get_numeric_filter_input(parent, column_name):
    operations = list(NUMERIC_DATE_OPERATIONS.keys())
    op, ok = QInputDialog.getItem(parent, f"Filter {column_name}", "Operation:", operations, editable=False)
    if not ok:
        return None

    value, ok = QInputDialog.getText(parent, f"Filter {column_name}", f"Enter numeric value to match:")
    if not ok:
        return None

    return op, value

def apply_filter(df, filter_object):
    """
    Apply the given filter object to the DataFrame `df`.

    :param df: DataFrame to apply the filter to.
    :param filter_object: Filter object (either StringFilter or NumericDateFilter).
    :return: Filtered DataFrame.
    """
    column_name = filter_object.column_name
    operation = filter_object.operation
    filter_value = filter_object.filter_value

    # Apply the filter based on the type
    if isinstance(filter_object, StringFilter):
        return df.filter(df[column_name].str.contains(filter_value, literal=True))
    elif isinstance(filter_object, NumericDateFilter):
        return df.filter(df[column_name].apply(lambda x: filter_object.matches(x)))
    else:
        raise ValueError(f"Unsupported filter type: {type(filter_object)}")