"""Sliding-window chunker (512 tokens, 64 overlap). Tokens approximated by whitespace words."""
from __future__ import annotations

import re
from typing import Iterable

from .. import config


def chunk_text(text: str, size: int = config.CHUNK_TOKENS, overlap: int = config.CHUNK_OVERLAP) -> list[str]:
    if overlap >= size:
        raise ValueError("overlap must be smaller than chunk size")
    words = re.findall(r"\S+", text)
    if not words:
        return []
    step, out, start = size - overlap, [], 0
    while True:
        out.append(" ".join(words[start:start + size]))
        if start + size >= len(words):
            return out
        start += step


def chunk_documents(docs: Iterable[dict]) -> list[dict]:
    """docs: {doc_id, source, title, text}. Returns chunk dicts with stable chunk_id."""
    chunks = []
    for d in docs:
        for i, piece in enumerate(chunk_text(d["text"])):
            chunks.append({"chunk_id": f"{d['doc_id']}#{i}", "doc_id": d["doc_id"], "source": d["source"],
                           "title": d["title"], "text": piece})
    return chunks
