"""Orchestrates the 4 stages and returns per-stage diagnostics for the UI / demo evidence."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Callable

from .. import config
from .answer import compose_answer
from .bm25 import BM25Retriever
from .chunker import chunk_documents
from .corpus import build_corpus
from .dense import DenseRetriever, Encoder, make_sentence_transformer_encoder
from .fusion import rrf
from .rerank import Scorer, make_cross_encoder_scorer, rerank


@dataclass
class RAGResult:
    query: str
    answer: str
    hits: list[dict] = field(default_factory=list)          # final chunks passed to generation
    stages: dict = field(default_factory=dict)              # per-stage diagnostics


class HybridRetriever:
    def __init__(self, chunks: list[dict], encoder: Encoder, scorer: Scorer,
                 scorer_returns_probability: bool = False, cache_dir=None):
        self.chunks = chunks
        self.bm25 = BM25Retriever(chunks)
        self.dense = DenseRetriever(chunks, encoder, cache_dir=cache_dir)
        self.scorer = scorer
        self._prob = scorer_returns_probability

    def search(self, query: str) -> RAGResult:
        s1 = self.bm25.search(query)                                   # Stage 1
        s2 = self.dense.search(query)                                  # Stage 2
        fused = rrf([[i for i, _ in s1], [i for i, _ in s2]])          # Stage 3
        pool = []
        r1 = {i: n for n, (i, _) in enumerate(s1, 1)}
        r2 = {i: n for n, (i, _) in enumerate(s2, 1)}
        for idx, score in fused:
            pool.append({**self.chunks[idx], "bm25_rank": r1.get(idx), "dense_rank": r2.get(idx), "rrf_score": score})
        kept, scored = rerank(query, pool, self.scorer, already_probability=self._prob)   # Stage 4
        stages = {
            "stage1_bm25": [{"chunk_id": self.chunks[i]["chunk_id"], "score": round(s, 3)} for i, s in s1[:10]],
            "stage2_dense": [{"chunk_id": self.chunks[i]["chunk_id"], "score": round(s, 3)} for i, s in s2[:10]],
            "stage3_rrf_pool_size": len(fused),
            "stage3_rrf_top": [{"chunk_id": pool[n]["chunk_id"], "rrf": round(pool[n]["rrf_score"], 5)} for n in range(min(10, len(pool)))],
            "stage4_scored": [{"chunk_id": c["chunk_id"], "rerank": round(c["rerank_score"], 3)} for c in scored[:10]],
            "stage4_kept": len(kept),
            "threshold": config.RERANK_THRESHOLD,
        }
        return RAGResult(query=query, answer=compose_answer(query, kept), hits=kept, stages=stages)


def build_retriever(conn: sqlite3.Connection | None = None, encoder: Encoder | None = None,
                    scorer: Scorer | None = None, cache_dir=None, **kw) -> HybridRetriever:
    """Production wiring (local models) unless an encoder/scorer is injected (tests)."""
    from .models import load_bi_encoder, load_cross_encoder
    chunks = chunk_documents(build_corpus(conn))
    if encoder is None:
        encoder = make_sentence_transformer_encoder(load_bi_encoder())
    prob = False
    if scorer is None:
        scorer = make_cross_encoder_scorer(load_cross_encoder())
    else:
        prob = kw.get("scorer_returns_probability", False)
    return HybridRetriever(chunks, encoder, scorer, scorer_returns_probability=prob, cache_dir=cache_dir)
