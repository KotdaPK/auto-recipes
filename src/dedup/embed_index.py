"""Local embedding index using SentenceTransformer."""

from __future__ import annotations

import json
import os
from typing import List, Tuple

import numpy as np

from sentence_transformers import SentenceTransformer
import logging

logger = logging.getLogger(__name__)


class EmbedIndex:
    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        self.model_name = model_name
        self.model = SentenceTransformer(model_name)
        self.names: List[str] = []
        self.vecs: np.ndarray | None = None

    def _encode_and_normalize(self, texts: List[str]) -> np.ndarray:
        raw = self.model.encode(texts, show_progress_bar=False, convert_to_numpy=True)
        raw = np.atleast_2d(raw)
        norms = np.linalg.norm(raw, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return raw / norms

    def build(self, names: List[str]) -> None:
        """Build the index from a list of names (strings). Vectors are L2-normalized."""
        self.names = names[:]
        if not self.names:
            self.vecs = None
            return
        self.vecs = self._encode_and_normalize(self.names)
        logger.info("EmbedIndex built for %d names using model %s", len(self.names), self.model_name)

    def save(self, path_base: str) -> None:
        os.makedirs(os.path.dirname(path_base), exist_ok=True)
        names_path = f"{path_base}.names.json"
        vecs_path = f"{path_base}.vecs.npy"
        with open(names_path, "w", encoding="utf8") as fh:
            json.dump(self.names, fh, ensure_ascii=False)
        if self.vecs is not None:
            np.save(vecs_path, self.vecs)
        logger.info("EmbedIndex saved to %s (names %s, vecs %s)", names_path, names_path, vecs_path)

    def load(self, path_base: str) -> None:
        names_path = f"{path_base}.names.json"
        vecs_path = f"{path_base}.vecs.npy"
        with open(names_path, "r", encoding="utf8") as fh:
            self.names = json.load(fh)
        self.vecs = np.load(vecs_path)
        logger.info("EmbedIndex loaded from %s", path_base)

    def add_name(self, name: str) -> None:
        """Append a new canonical name and its embedding to the index."""
        if not name:
            return
        new_vec = self._encode_and_normalize([name])
        if self.vecs is None or self.vecs.size == 0:
            self.vecs = new_vec
        else:
            self.vecs = np.vstack([self.vecs, new_vec])
        self.names.append(name)
        logger.debug("EmbedIndex appended name '%s' (total=%d)", name, len(self.names))

    def nearest(self, query: str, topk: int = 1) -> Tuple[str, float]:
        """Return (name, score) for nearest neighbor using dot on normalized vectors.

        Score is cosine similarity in [-1,1]. If empty index, return ('', 0.0).
        """
        if not self.names or self.vecs is None or self.vecs.size == 0:
            logger.debug("EmbedIndex empty when querying nearest for '%s'", query)
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
        logger.debug("EmbedIndex nearest for '%s' -> %s (score=%s)", query, self.names[idx], float(scores[idx]))
        return self.names[idx], float(scores[idx])
