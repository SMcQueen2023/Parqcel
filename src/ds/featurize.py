"""Column featurization utilities for Polars DataFrame.

Provides functions to generate numeric, categorical (one-hot), and text (TF-IDF)
features and return a combined feature matrix plus feature names. Also includes
helper to add generated feature columns back into a Polars DataFrame.

This module uses scikit-learn for transformations. If scikit-learn is not
installed the functions will raise an informative ImportError.
"""

from typing import List, Optional, Tuple
import polars as pl
import numpy as np

try:
    from sklearn.preprocessing import StandardScaler, MinMaxScaler, OneHotEncoder
    from sklearn.feature_extraction.text import TfidfVectorizer
except ImportError:  # pragma: no cover - runtime dependency
    _SKLEARN_AVAILABLE = False
else:
    _SKLEARN_AVAILABLE = True


def _ensure_sklearn():
    if not _SKLEARN_AVAILABLE:
        raise ImportError(
            "scikit-learn is required for featurization. Install it with: \n"
            "pip install scikit-learn"
        )


def detect_columns(df: pl.DataFrame) -> Tuple[List[str], List[str], List[str]]:
    """Detect numeric, categorical and text-like columns.

    Simple heuristics are used:
    - numeric: Int/Float polars dtypes
    - categorical: Utf8 with relatively small unique count (< 50)
    - text: Utf8 with larger unique count

    Returns (numeric_cols, categorical_cols, text_cols)
    """
    schema = df.schema

    numeric: List[str] = []
    categorical: List[str] = []
    text: List[str] = []

    for col, dtype in schema.items():
        if dtype.is_integer() or dtype.is_float():
            numeric.append(col)
        elif dtype in (pl.Utf8, pl.Categorical):
            # choose categorical vs text based on unique count
            try:
                n_unique = df[col].n_unique()
            except Exception:
                n_unique = 0
            if n_unique <= 50:
                categorical.append(col)
            else:
                text.append(col)

    return numeric, categorical, text


def _to_numpy(df: pl.DataFrame, cols: List[str]) -> np.ndarray:
    if not cols:
        return np.zeros((len(df), 0))
    try:
        return df.select(cols).to_numpy()
    except Exception:
        # fallback to pandas if polars version lacks to_numpy
        return df.select(cols).to_pandas().values


def _check_dense_budget(required_bytes: int, limit_bytes: int) -> None:
    if required_bytes > limit_bytes:
        raise MemoryError(
            f"Featurization needs an estimated {required_bytes:,} bytes of dense "
            f"matrix memory, above the {limit_bytes:,}-byte limit. "
            "Use fewer rows or features, or increase max_matrix_bytes."
        )


def generate_feature_matrix(
    df: pl.DataFrame,
    numeric_cols: Optional[List[str]] = None,
    categorical_cols: Optional[List[str]] = None,
    text_cols: Optional[List[str]] = None,
    scale_numeric: Optional[str] = "standard",  # 'standard'|'minmax'|None
    one_hot: bool = True,
    tfidf_max_features: int = 200,
    max_matrix_bytes: int = 256 * 1024 * 1024,
) -> Tuple[np.ndarray, List[str]]:
    """Generate a numerical feature matrix and corresponding feature names.

    Returns (X, feature_names) where X is a 2D numpy array with shape
    (n_rows, n_features).

    ``max_matrix_bytes`` bounds estimated simultaneously retained dense feature
    components plus the combined output (roughly twice the final float64 matrix).
    It is not a process memory limit: the source frame, pandas/text conversions,
    TF-IDF vocabulary/sparse matrices, and estimator scratch space are excluded.
    Raises MemoryError before a dense allocation would exceed this estimate.
    """
    _ensure_sklearn()
    if scale_numeric not in (None, "standard", "minmax"):
        raise ValueError("Numeric scaling must be standard, minmax, or None")
    if not isinstance(max_matrix_bytes, int) or max_matrix_bytes < 0:
        raise ValueError("max_matrix_bytes must be a non-negative integer")

    numeric, categorical, text = detect_columns(df)

    if numeric_cols is None:
        numeric_cols = numeric
    if categorical_cols is None:
        categorical_cols = categorical
    if text_cols is None:
        text_cols = text

    parts: List[np.ndarray] = []
    feature_names: List[str] = []
    dense_bytes = 0

    def check_component(width: int) -> None:
        component_bytes = df.height * width * np.dtype(np.float64).itemsize
        # Reserve for both the component arrays and final hstack output. This
        # also covers input/output copies during numeric conversion/scaling.
        _check_dense_budget(2 * (dense_bytes + component_bytes), max_matrix_bytes)

    # Numeric processing
    if numeric_cols:
        check_component(len(numeric_cols))
        X_num = _to_numpy(df, numeric_cols).astype(np.float64, copy=False)
        if scale_numeric == "standard":
            scaler = StandardScaler()
            X_num = scaler.fit_transform(X_num)
        elif scale_numeric == "minmax":
            scaler = MinMaxScaler()
            X_num = scaler.fit_transform(X_num)
        parts.append(X_num)
        dense_bytes += X_num.nbytes
        suffix = scale_numeric or "numeric"
        feature_names.extend(f"{name}__{suffix}" for name in numeric_cols)

    # Categorical one-hot
    if categorical_cols and one_hot:
        category_width = sum(df[column].n_unique() for column in categorical_cols)
        check_component(category_width)
        # Use pandas DataFrame as scikit-learn expects 2D array-like with columns
        try:
            cat_df = df.select(categorical_cols).to_pandas()
        except Exception:
            # last resort: convert each series to list
            cat_df = None
        # Construct OneHotEncoder compatibly across scikit-learn versions
        try:
            encoder = OneHotEncoder(sparse_output=False, handle_unknown="ignore")
        except TypeError:
            # Older versions used `sparse` keyword
            encoder = OneHotEncoder(sparse=False, handle_unknown="ignore")

        if cat_df is not None:
            X_cat = encoder.fit_transform(cat_df)
        else:
            rows = [[df[c][i] for c in categorical_cols] for i in range(len(df))]
            X_cat = encoder.fit_transform(rows)
        parts.append(X_cat)
        dense_bytes += X_cat.nbytes
        names = list(encoder.get_feature_names_out(categorical_cols))
        feature_names.extend(names)

    # Text TF-IDF
    if text_cols:
        for tcol in text_cols:
            vec = TfidfVectorizer(max_features=tfidf_max_features)
            # convert to python list of strings
            series = df[tcol].fill_null("")
            try:
                texts = series.to_list()
            except Exception:
                texts = list(series)
            sparse_text = vec.fit_transform(texts)
            check_component(sparse_text.shape[1])
            X_t = sparse_text.toarray()
            del sparse_text
            parts.append(X_t)
            dense_bytes += X_t.nbytes
            names = [f"{tcol}__tfidf__{n}" for n in vec.get_feature_names_out()]
            feature_names.extend(names)

    if parts:
        # Check actual shapes/dtypes too, before allocating the combined array.
        output_bytes = (
            df.height
            * sum(part.shape[1] for part in parts)
            * np.result_type(*(part.dtype for part in parts)).itemsize
        )
        _check_dense_budget(dense_bytes + output_bytes, max_matrix_bytes)
        X = np.hstack(parts)
    else:
        X = np.zeros((len(df), 0))

    return X, _unique_feature_names(feature_names, df.columns)


def _unique_feature_names(names: List[str], existing: List[str]) -> List[str]:
    """Keep generated names deterministic and never overwrite source columns."""
    used = set(existing)
    unique = []
    for name in names:
        if not isinstance(name, str) or not name:
            raise ValueError("Feature names must be non-empty strings")
        candidate = name
        suffix = 2
        while candidate in used:
            candidate = f"{name}__{suffix}"
            suffix += 1
        used.add(candidate)
        unique.append(candidate)
    return unique


def add_features_to_df(
    df: pl.DataFrame, X: np.ndarray, feature_names: List[str]
) -> pl.DataFrame:
    """Return a new Polars DataFrame with feature columns appended.

    Names that collide with source or earlier feature columns receive a numeric
    suffix. Both source values and every generated feature are preserved.
    """
    if X.ndim != 2:
        raise ValueError("Feature matrix must have two dimensions")
    if X.shape[0] != df.height:
        raise ValueError("Feature matrix row count must match the dataset")
    if X.shape[1] != len(feature_names):
        raise ValueError("Number of columns in X does not match feature_names length")
    names = _unique_feature_names(feature_names, df.columns)
    if not names:
        return df.clone()
    return df.hstack([pl.Series(name, X[:, i]) for i, name in enumerate(names)])
