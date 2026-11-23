"""Pre-build the dense embedding cache and smoke-test the hybrid retriever."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pharma_intake import db  # noqa: E402
from pharma_intake.rag.pipeline import build_retriever  # noqa: E402

retriever = build_retriever(db.connect())
print(f"Indexed {len(retriever.chunks)} chunks.")
res = retriever.search("difficulty breathing")
print(res.answer)
