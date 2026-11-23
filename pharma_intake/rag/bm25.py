"""Stage 1: lexical sparse retrieval (BM25Okapi, k1=1.3, b=0.75)."""
from __future__ import annotations

import re

from rank_bm25 import BM25Okapi

from .. import config

_TOKEN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


def tokenize(text: str) -> list[str]:
    """Lowercase; keep codes like LOT-88392 whole AND emit their parts so partial queries still match."""
    out: list[str] = []
    for tok in _TOKEN.findall(text.lower()):
        out.append(tok)
        if "-" in tok:
            out.extend(tok.split("-"))
    return out


class BM25Retriever:
    def __init__(self, chunks: list[dict], k1: float = config.BM25_K1, b: float = config.BM25_B):
        self.chunks = chunks
        self._bm25 = BM25Okapi([tokenize(c["title"] + " " + c["text"]) for c in chunks], k1=k1, b=b)

    def search(self, query: str, top_k: int = config.TOP_K_PER_RETRIEVER) -> list[tuple[int, float]]:
        """Return [(chunk_index, score)] best-first, only chunks sharing at least one query term."""
        q = tokenize(query)
        if not q or not self.chunks:
            return []
        scores = self._bm25.get_scores(q)
        qset = set(q)
        ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        hits = []
        for i in ranked:
            if len(hits) >= top_k:
                break
            toks = set(tokenize(self.chunks[i]["title"] + " " + self.chunks[i]["text"]))
            if qset & toks:
                hits.append((i, float(scores[i])))
        return hits
