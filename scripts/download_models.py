"""One-time download of the local retrieval models into logs/models (needs internet ONCE; offline afterwards)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pharma_intake import config  # noqa: E402

config.MODELS_DIR.mkdir(parents=True, exist_ok=True)
os.environ["HF_HOME"] = str(config.MODELS_DIR)
os.environ.pop("HF_HUB_OFFLINE", None)

from sentence_transformers import CrossEncoder, SentenceTransformer  # noqa: E402

print(f"Downloading {config.BI_ENCODER} ...")
SentenceTransformer(config.BI_ENCODER, device="cpu")
print(f"Downloading {config.CROSS_ENCODER} ...")
CrossEncoder(config.CROSS_ENCODER, device="cpu")
(config.MODELS_DIR / ".downloaded").write_text("ok", encoding="utf-8")
print(f"Done. Models cached in {config.MODELS_DIR}; the app now runs fully offline.")
