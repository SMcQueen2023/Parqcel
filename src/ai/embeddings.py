from __future__ import annotations

from typing import List, Optional, Tuple
import numpy as np

try:
    from sentence_transformers import SentenceTransformer
except Exception:  # pragma: no cover - optional runtime dependency
    SentenceTransformer = None

try:
    import faiss
except Exception:
    faiss = None

from sklearn.feature_extraction.text import TfidfVectorizer


class Embedder:
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model_name = model_name
        if SentenceTransformer is not None:
            self.model = SentenceTransformer(model_name)
        else:
            self.model = None
            self._tfidf = TfidfVectorizer(max_features=4096)
            self._tfidf_fitted = False

    def encode(self, texts: List[str]) -> np.ndarray:
        if self.model is not None:
            arr = self.model.encode(texts, show_progress_bar=False)
            return np.asarray(arr)
        # Fallback to TF-IDF dense vectors
        if not self._tfidf_fitted:
            mat = self._tfidf.fit_transform(texts)
            self._tfidf_fitted = True
        else:
            mat = self._tfidf.transform(texts)
        return mat.toarray()


class EmbeddingStore:
    """Simple in-memory embedding store with optional FAISS index.

    Stores ids and associated vectors. Provides nearest-neighbor search by
    cosine similarity. Save/load via `numpy.savez`.
    """

    def __init__(self, dim: Optional[int] = None):
        self.ids: List[str] = []
        self.vectors: Optional[np.ndarray] = None
        self.dim = dim
        self._faiss_index = None

    def add(self, ids: List[str], vecs: np.ndarray):
        if self.vectors is None:
            self.vectors = np.asarray(vecs)
        else:
            self.vectors = np.vstack([self.vectors, vecs])
        self.ids.extend(ids)
        self.dim = self.vectors.shape[1]
        self._build_faiss()

    def _build_faiss(self):
        if faiss is None:
            self._faiss_index = None
            return
        # Normalize for cosine (inner product on normalized vectors)
        vecs = np.asarray(self.vectors).astype("float32")
        faiss.normalize_L2(vecs)
        idx = faiss.IndexFlatIP(vecs.shape[1])
        idx.add(vecs)
        self._faiss_index = idx

    def search(self, query_vec: np.ndarray, top_k: int = 5) -> List[Tuple[str, float]]:
        q = np.asarray(query_vec).reshape(1, -1).astype("float32")
        # normalize
        q_norms = np.linalg.norm(q, axis=1, keepdims=True)
        q_norms[q_norms == 0] = 1.0
        q = q / q_norms
        if self._faiss_index is not None:
            D, I = self._faiss_index.search(q, top_k)
            results = []
            for score, idx in zip(D[0], I[0]):
                if idx < 0:
                    continue
                results.append((self.ids[idx], float(score)))
            return results
        # Fallback: compute cosine with numpy
        if self.vectors is None:
            return []
        vecs = np.asarray(self.vectors)
        vecs_norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        vecs_norms[vecs_norms == 0] = 1.0
        vecs_norm = vecs / vecs_norms
        q_norm = q[0]
        sims = vecs_norm.dot(q_norm)
        top_idx = np.argsort(-sims)[:top_k]
        return [(self.ids[i], float(sims[i])) for i in top_idx]

    def save(self, path: str):
        np.savez(path, ids=np.array(self.ids), vectors=self.vectors)

    def load(self, path: str):
        data = np.load(path)
        self.ids = data["ids"].tolist()
        self.vectors = data["vectors"]
        self._build_faiss()
