"""Lazy loaders for the local bi-encoder and cross-encoder (CPU, offline after one-time download)."""
from __future__ import annotations

import os
from functools import lru_cache

from .. import config

_MARKER = config.MODELS_DIR / ".downloaded"


def _prepare_env() -> None:
    """Point the HF cache at logs/models and go offline once models were downloaded."""
    os.environ.setdefault("HF_HOME", str(config.MODELS_DIR))
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    if _MARKER.exists():
        os.environ["HF_HUB_OFFLINE"] = "1"


class ModelsUnavailable(RuntimeError):
    pass


def models_ready() -> bool:
    return _MARKER.exists()


@lru_cache(maxsize=1)
def load_bi_encoder():
    _prepare_env()
    try:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer(config.BI_ENCODER, device="cpu")
    except Exception as exc:  # missing download / offline cache miss
        raise ModelsUnavailable(
            "Bi-encoder model not available. Run `python scripts/download_models.py` once (needs internet), "
            f"then retry. Details: {type(exc).__name__}") from exc
    model.max_seq_length = config.CHUNK_TOKENS
    return model


@lru_cache(maxsize=1)
def load_cross_encoder():
    _prepare_env()
    try:
        from sentence_transformers import CrossEncoder
        return CrossEncoder(config.CROSS_ENCODER, device="cpu", max_length=config.CHUNK_TOKENS)
    except Exception as exc:
        raise ModelsUnavailable(
            "Cross-encoder model not available. Run `python scripts/download_models.py` once (needs internet), "
            f"then retry. Details: {type(exc).__name__}") from exc
