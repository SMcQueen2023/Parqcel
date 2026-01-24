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
except Exception as e:  # pragma: no cover - runtime dependency
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
    numeric_types = (pl.Int64, pl.Int32, pl.Float64, pl.Float32)

    numeric: List[str] = []
    categorical: List[str] = []
    text: List[str] = []

    for col, dtype in schema.items():
        if dtype in numeric_types:
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


def generate_feature_matrix(
    df: pl.DataFrame,
    numeric_cols: Optional[List[str]] = None,
    categorical_cols: Optional[List[str]] = None,
    text_cols: Optional[List[str]] = None,
    scale_numeric: Optional[str] = "standard",  # 'standard'|'minmax'|None
    one_hot: bool = True,
    tfidf_max_features: int = 200,
) -> Tuple[np.ndarray, List[str]]:
    """Generate a numerical feature matrix and corresponding feature names.

    Returns (X, feature_names) where X is a 2D numpy array with shape
    (n_rows, n_features).
    """
    _ensure_sklearn()

    numeric, categorical, text = detect_columns(df)

    if numeric_cols is None:
        numeric_cols = numeric
    if categorical_cols is None:
        categorical_cols = categorical
    if text_cols is None:
        text_cols = text

    parts: List[np.ndarray] = []
    feature_names: List[str] = []

    # Numeric processing
    if numeric_cols:
        X_num = _to_numpy(df, numeric_cols).astype(float)
        if scale_numeric == "standard":
            scaler = StandardScaler()
            X_num = scaler.fit_transform(X_num)
        elif scale_numeric == "minmax":
            scaler = MinMaxScaler()
            X_num = scaler.fit_transform(X_num)
        parts.append(X_num)
        feature_names.extend(list(numeric_cols))

    # Categorical one-hot
    if categorical_cols and one_hot:
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
            X_t = vec.fit_transform(texts).toarray()
            parts.append(X_t)
            names = [f"{tcol}__tfidf__{n}" for n in vec.get_feature_names_out()]
            feature_names.extend(names)

    if parts:
        X = np.hstack(parts)
    else:
        X = np.zeros((len(df), 0))

    return X, feature_names


def add_features_to_df(df: pl.DataFrame, X: np.ndarray, feature_names: List[str]) -> pl.DataFrame:
    """Return a new Polars DataFrame with feature columns appended.

    Feature columns will be named using the given `feature_names` list.
    """
    if X.shape[1] != len(feature_names):
        raise ValueError("Number of columns in X does not match feature_names length")

    # build a dict of series
    cols = {}
    for i, name in enumerate(feature_names):
        cols[name] = list(X[:, i])

    feat_df = pl.DataFrame(cols)
    return df.hstack(feat_df)
