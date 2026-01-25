import numpy as np
import pytest

from ds.dimensionality import compute_pca, compute_umap


def test_compute_pca_shape_and_variance():
    rng = np.random.RandomState(0)
    X = rng.standard_normal(size=(20, 5))
    emb, var_ratio = compute_pca(X, n_components=3)
    assert emb.shape == (20, 3)
    assert hasattr(var_ratio, "__len__") and len(var_ratio) == 3


def test_compute_umap_if_available():
    rng = np.random.RandomState(1)
    X = rng.standard_normal(size=(30, 4))
    try:
        emb = compute_umap(X, n_components=2)
    except ImportError:
        pytest.skip("umap-learn not installed")
    assert emb.shape == (30, 2)
