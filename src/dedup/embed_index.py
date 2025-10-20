"""Local embedding index using SentenceTransformer."""

from __future__ import annotations

import json
import os
from typing import List, Tuple

import numpy as np

from sentence_transformers import SentenceTransformer


class EmbedIndex:
    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        self.model_name = model_name
        self.model = SentenceTransformer(model_name)
        self.names: List[str] = []
        self.vecs: np.ndarray | None = None

    def build(self, names: List[str]) -> None:
        """Build the index from a list of names (strings). Vectors are L2-normalized."""
        self.names = names[:]
        raw = self.model.encode(
            self.names, show_progress_bar=False, convert_to_numpy=True
        )
        # ensure 2D (sentence-transformers may return 1D for a single input)
        raw = np.atleast_2d(raw)
        # normalize per-row
        norms = np.linalg.norm(raw, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        self.vecs = raw / norms

    def save(self, path_base: str) -> None:
        os.makedirs(os.path.dirname(path_base), exist_ok=True)
        names_path = f"{path_base}.names.json"
        vecs_path = f"{path_base}.vecs.npy"
        with open(names_path, "w", encoding="utf8") as fh:
            json.dump(self.names, fh, ensure_ascii=False)
        if self.vecs is not None:
            np.save(vecs_path, self.vecs)

    def load(self, path_base: str) -> None:
        names_path = f"{path_base}.names.json"
        vecs_path = f"{path_base}.vecs.npy"
        with open(names_path, "r", encoding="utf8") as fh:
            self.names = json.load(fh)
        self.vecs = np.load(vecs_path)

    def nearest(self, query: str, topk: int = 1) -> Tuple[str, float]:
        """Return (name, score) for nearest neighbor using dot on normalized vectors.

        Score is cosine similarity in [-1,1]. If empty index, return ('', 0.0).
        """
        if not self.names or self.vecs is None or self.vecs.size == 0:
            return "", 0.0
        qvec = self.model.encode([query], convert_to_numpy=True)
        # ensure qvec is 1D
        if qvec.ndim == 2:
            qvec = qvec[0]
        qnorm = np.linalg.norm(qvec)
        if qnorm == 0:
            return "", 0.0
        qvec = qvec / qnorm
        # compute dot product between (N,d) and (d,)
        scores = self.vecs @ qvec
        idx = int(np.argmax(scores))
        return self.names[idx], float(scores[idx])
