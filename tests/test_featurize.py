import polars as pl
import numpy as np

from ds.featurize import generate_feature_matrix, add_features_to_df


def test_generate_feature_matrix_basic():
    df = pl.DataFrame(
        {
            "num": [1.0, 2.0, 3.0, 4.0],
            "cat": ["a", "b", "a", "c"],
            "text": ["hello world", "foo bar", "hello", "baz"],
        }
    )

    X, names = generate_feature_matrix(df, tfidf_max_features=10)
    assert X.shape[0] == df.height
    assert len(names) == X.shape[1]


def test_add_features_to_df():
    df = pl.DataFrame({"num": [1, 2, 3]})
    X = np.array([[0.1, 1], [0.2, 2], [0.3, 3]])
    names = ["f1", "f2"]
    new_df = add_features_to_df(df, X, names)
    assert "f1" in new_df.columns
    assert "f2" in new_df.columns
    assert new_df.height == 3
