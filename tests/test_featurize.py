import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("sklearn")

import polars as pl

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


def test_numeric_generation_and_append_preserve_source_with_collisions():
    df = pl.DataFrame({"num": [1.0, 2.0, 3.0], "num__standard": [9, 9, 9]})
    X, names = generate_feature_matrix(df, numeric_cols=["num"])
    assert names == ["num__standard__2"]
    result = add_features_to_df(df, X, names)
    assert result.select(df.columns).equals(df)
    assert result.width == 3
    assert abs(result[names[0]].mean()) < 1e-9


def test_duplicate_feature_names_keep_every_feature():
    df = pl.DataFrame({"a": [1, 2]})
    result = add_features_to_df(df, np.array([[3, 4], [5, 6]]), ["a", "a"])
    assert result.columns == ["a", "a__2", "a__3"]
    assert result["a__2"].to_list() == [3, 5]
    assert result["a__3"].to_list() == [4, 6]


@pytest.mark.parametrize(
    "matrix,names",
    [
        (np.array([1, 2]), ["f"]),
        (np.zeros((3, 1)), ["f"]),
        (np.zeros((2, 2)), ["f"]),
    ],
)
def test_invalid_feature_shape_is_rejected(matrix, names):
    with pytest.raises(ValueError):
        add_features_to_df(pl.DataFrame({"a": [1, 2]}), matrix, names)


def test_numeric_budget_rejects_before_numpy_conversion(monkeypatch):
    import ds.featurize as module

    def unexpected_conversion(*args, **kwargs):
        pytest.fail("Dense numeric conversion must not run above the budget")

    monkeypatch.setattr(module, "_to_numpy", unexpected_conversion)
    with pytest.raises(MemoryError, match="fewer rows or features"):
        generate_feature_matrix(pl.DataFrame({"a": [1, 2, 3]}), max_matrix_bytes=47)


def test_categorical_budget_rejects_before_encoder_allocation(monkeypatch):
    import ds.featurize as module

    def unexpected_encoder(*args, **kwargs):
        pytest.fail("Dense one-hot encoding must not run above the budget")

    monkeypatch.setattr(module, "OneHotEncoder", unexpected_encoder)
    with pytest.raises(MemoryError, match="96 bytes"):
        generate_feature_matrix(
            pl.DataFrame({"category": ["a", "b", "a"]}), max_matrix_bytes=95
        )


def test_text_budget_rejects_before_sparse_matrix_is_densified(monkeypatch):
    from scipy.sparse import csr_matrix

    def unexpected_densification(*args, **kwargs):
        pytest.fail("TF-IDF must stay sparse when its dense result exceeds the budget")

    monkeypatch.setattr(csr_matrix, "toarray", unexpected_densification)
    with pytest.raises(MemoryError, match="96 bytes"):
        generate_feature_matrix(
            pl.DataFrame({"text": ["alpha beta", "beta gamma"]}),
            numeric_cols=[],
            categorical_cols=[],
            text_cols=["text"],
            max_matrix_bytes=95,
        )


def test_combined_components_and_output_share_one_budget():
    frame = pl.DataFrame({"num": [1, 2, 3], "category": ["a", "b", "a"]})
    # Components are 24 and 48 bytes; both individually fit, but retaining them
    # alongside the 72-byte output needs 144 bytes.
    with pytest.raises(MemoryError, match="144 bytes"):
        generate_feature_matrix(frame, max_matrix_bytes=120)
    matrix, names = generate_feature_matrix(frame, max_matrix_bytes=144)
    assert matrix.shape == (3, 3)
    assert len(names) == 3
    assert matrix.nbytes == 72


def test_text_at_dense_budget_boundary_and_empty_features():
    matrix, names = generate_feature_matrix(
        pl.DataFrame({"text": ["alpha beta", "beta gamma"]}),
        numeric_cols=[],
        categorical_cols=[],
        text_cols=["text"],
        max_matrix_bytes=96,
    )
    assert matrix.shape == (2, 3)
    assert len(names) == 3
    empty, names = generate_feature_matrix(
        pl.DataFrame({"a": [1, 2]}),
        numeric_cols=[],
        categorical_cols=[],
        text_cols=[],
        max_matrix_bytes=0,
    )
    assert empty.shape == (2, 0)
    assert names == []
