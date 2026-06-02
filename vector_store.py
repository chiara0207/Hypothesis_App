from typing import List, Dict, Any, Tuple
import numpy as np
import logging
import time

logger = logging.getLogger(__name__)

try:
    import faiss
    logger.debug("FAISS imported successfully")
except Exception as e:
    logger.warning(f"FAISS not available: {e}. Falling back to numpy.")
    faiss = None


class VectorStore:
    def __init__(self, dim: int = None):
        self.ids: List[str] = []
        self.metadatas: List[Dict[str, Any]] = []
        self._dim = dim
        self._np_index: List[np.ndarray] = []
        self._faiss_index = None

    def _ensure_faiss(self, dim: int) -> bool:
        if faiss is None:
            return False
        if self._faiss_index is None:
            self._faiss_index = faiss.IndexFlatIP(dim)
        return True

    def add(self, ids: List[str], vectors: List[List[float]], metadatas: List[Dict[str, Any]]):
        if not vectors:
            return
        dim = len(vectors[0])
        if self._dim is None:
            self._dim = dim

        vecs_np = np.array(vectors, dtype=np.float32)
        norms = np.linalg.norm(vecs_np, axis=1, keepdims=True) + 1e-10
        vecs_np = vecs_np / norms

        if self._ensure_faiss(dim):
            self._faiss_index.add(vecs_np)
        else:
            self._np_index.append(vecs_np)

        self.ids.extend(ids)
        self.metadatas.extend(metadatas)
        logger.info(f"VectorStore: {len(self.ids)} total vectors stored")

    def query(self, vector: List[float], top_k: int = 5) -> List[Tuple[str, float, Dict[str, Any]]]:
        if self._dim is None:
            return []

        q = np.array(vector, dtype=np.float32)
        q = q / (np.linalg.norm(q) + 1e-10)

        if self._faiss_index is not None:
            D, I = self._faiss_index.search(np.expand_dims(q, axis=0), top_k)
            results = []
            for idx, score in zip(I[0], D[0]):
                if idx < 0:
                    continue
                results.append((self.ids[int(idx)], float(score), self.metadatas[int(idx)]))
            return results

        if self._np_index:
            mat = np.vstack(self._np_index)
            mat_norm = mat / (np.linalg.norm(mat, axis=1, keepdims=True) + 1e-10)
            scores = (mat_norm @ q).astype(float)
            idxs = np.argsort(-scores)[:top_k]
            return [(self.ids[int(i)], float(scores[int(i)]), self.metadatas[int(i)]) for i in idxs]

        return []

    def clear(self):
        self.ids = []
        self.metadatas = []
        self._np_index = []
        self._faiss_index = None
        self._dim = None
