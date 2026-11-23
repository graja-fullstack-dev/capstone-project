"""Extractive, cited answers. No generative model: the output is quoted source text only."""
from __future__ import annotations

from .. import config

NO_RESULT = ("No sufficiently relevant record or SOP found (no candidate cleared the relevance "
             f"threshold of {config.RERANK_THRESHOLD:.2f}). Try different keywords such as a lot number or product name.")


def _excerpt(text: str, limit: int = 450) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[:limit].rsplit(" ", 1)[0] + " ..."


def compose_answer(query: str, chunks: list[dict]) -> str:
    if not chunks:
        return NO_RESULT
    lines = [f"Top {len(chunks)} relevant source(s) for: \"{query}\"", ""]
    for n, c in enumerate(chunks, 1):
        lines.append(f"[{n}] {c['source']} - {c['title']} (relevance {c['rerank_score']:.2f})")
        lines.append(f"    \"{_excerpt(c['text'])}\"")
    lines += ["", config.DISCLAIMER]
    return "\n".join(lines)
