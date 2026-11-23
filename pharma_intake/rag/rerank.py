"""Stage 4: cross-encoder reranking with a 0.40 relevance threshold, keeping the top 3-5 chunks."""
from __future__ import annotations

import math
from typing import Callable, Sequence

from .. import config

# scorer(query, texts) -> raw model scores (logits or probabilities), one per text
Scorer = Callable[[str, Sequence[str]], Sequence[float]]


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x)) if x >= 0 else math.exp(x) / (1.0 + math.exp(x))


def make_cross_encoder_scorer(model) -> Scorer:
    def score(query: str, texts: Sequence[str]) -> list[float]:
        # Raw logits requested explicitly so we apply exactly one sigmoid below.
        raw = model.predict([(query, t) for t in texts], activation_fn=_identity(), show_progress_bar=False)
        return [float(v) for v in raw]
    return score


def _identity():
    import torch
    return torch.nn.Identity()


def rerank(query: str, candidates: list[dict], scorer: Scorer, threshold: float = config.RERANK_THRESHOLD,
           max_k: int = config.FINAL_MAX_K, already_probability: bool = False) -> tuple[list[dict], list[dict]]:
    """Return (kept, all_scored). Scores are mapped to [0,1] via sigmoid unless already probabilities."""
    if not candidates:
        return [], []
    raw = scorer(query, [f"{c['title']}\n{c['text']}" for c in candidates])
    scored = []
    for c, r in zip(candidates, raw):
        s = float(r) if already_probability else sigmoid(float(r))
        scored.append({**c, "rerank_score": s})
    scored.sort(key=lambda c: c["rerank_score"], reverse=True)
    kept = [c for c in scored if c["rerank_score"] >= threshold][:max_k]
    return kept, scored
