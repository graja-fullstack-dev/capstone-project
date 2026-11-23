"""Stage 2: dense semantic retrieval (bi-encoder + cosine similarity) with an on-disk embedding cache."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

import numpy as np

from .. import config
from .corpus import corpus_hash

Encoder = Callable[[list[str]], np.ndarray]


def _doc_text(c: dict) -> str:
    return f"{c['title']}\n{c['text']}"


class DenseRetriever:
    def __init__(self, chunks: list[dict], encoder: Encoder, cache_dir: Path | None = None):
        self.chunks, self.encoder = chunks, encoder
        self.embeddings = self._load_or_build(cache_dir if cache_dir is not None else config.INDEX_DIR)

    @staticmethod
    def _normalize(m: np.ndarray) -> np.ndarray:
        m = np.asarray(m, dtype=np.float32)
        n = np.linalg.norm(m, axis=1, keepdims=True)
        return m / np.clip(n, 1e-12, None)

    def _load_or_build(self, cache_dir: Path) -> np.ndarray:
        digest = corpus_hash(self.chunks)
        emb_path, meta_path = cache_dir / "dense.npy", cache_dir / "dense.json"
        if emb_path.exists() and meta_path.exists():
            try:
                if json.loads(meta_path.read_text())["hash"] == digest:
                    return np.load(emb_path)
            except (ValueError, KeyError, OSError):
                pass
        emb = self._normalize(self.encoder([_doc_text(c) for c in self.chunks])) if self.chunks else np.zeros((0, 1), np.float32)
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
            np.save(emb_path, emb)
            meta_path.write_text(json.dumps({"hash": digest}))
        except OSError:
            pass  # cache is an optimization only
        return emb

    def search(self, query: str, top_k: int = config.TOP_K_PER_RETRIEVER) -> list[tuple[int, float]]:
        if not len(self.chunks):
            return []
        q = self._normalize(self.encoder([query]))[0]
        sims = self.embeddings @ q  # cosine: both sides unit-norm
        order = np.argsort(-sims)[:top_k]
        return [(int(i), float(sims[i])) for i in order]


def make_sentence_transformer_encoder(model) -> Encoder:
    return lambda texts: model.encode(texts, batch_size=16, show_progress_bar=False, convert_to_numpy=True)
