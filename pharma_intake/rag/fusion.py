"""Stage 3: Reciprocal Rank Fusion, score(d) = sum over rankers of 1 / (k + rank), k=60."""
from __future__ import annotations

from .. import config


def rrf(rankings: list[list[int]], k: int = config.RRF_K) -> list[tuple[int, float]]:
    """rankings: lists of chunk indices, best first (rank starts at 1). Returns [(idx, score)] best first."""
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, idx in enumerate(ranking, start=1):
            scores[idx] = scores.get(idx, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
