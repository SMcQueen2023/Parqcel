"""Dimensionality reduction helpers.

Provides PCA (via scikit-learn) and optional UMAP integration (if installed).
"""
from typing import Tuple, Optional
import numpy as np

try:
    from sklearn.decomposition import PCA
except Exception:  # pragma: no cover - runtime dependency
    PCA = None

try:
    import umap as _umap
except Exception:
    _umap = None


def compute_pca(
    X: np.ndarray, n_components: int = 2, random_state: Optional[int] = 0
) -> Tuple[np.ndarray, np.ndarray]:
    """Compute PCA embedding for X.

    Returns (embedding, explained_variance_ratio_).
    """
    if PCA is None:
        raise ImportError("scikit-learn is required for PCA. Install scikit-learn.")
    pca = PCA(n_components=n_components, random_state=random_state)
    embedding = pca.fit_transform(X)
    return embedding, getattr(pca, "explained_variance_ratio_", np.array([]))


def compute_umap(
    X: np.ndarray, n_components: int = 2, random_state: Optional[int] = 0
) -> np.ndarray:
    """Compute UMAP embedding if UMAP is available.

    Raises ImportError if umap is not installed.
    """
    if _umap is None:
        raise ImportError("umap-learn is required for UMAP. Install umap-learn.")
    reducer = _umap.UMAP(n_components=n_components, random_state=random_state)
    return reducer.fit_transform(X)
