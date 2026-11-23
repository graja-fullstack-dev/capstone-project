"""Central configuration. All tunable RAG/agent constants live here only."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOGS_DIR = ROOT / "logs"
DATA_DIR = ROOT / "data" / "seed"
SOP_DIR = DATA_DIR / "sops"
SEED_REPORTS = DATA_DIR / "reports.json"
MODELS_DIR = Path(os.environ.get("PHARMA_MODELS_DIR", LOGS_DIR / "models"))
INDEX_DIR = Path(os.environ.get("PHARMA_INDEX_DIR", LOGS_DIR / "index"))


def db_path() -> Path:
    return Path(os.environ.get("PHARMA_DB_PATH", LOGS_DIR / "app.db"))


# --- RAG (Section 5 of the case study) ---
BM25_K1 = 1.3          # spec range 1.2-1.5
BM25_B = 0.75
CHUNK_TOKENS = 512
CHUNK_OVERLAP = 64
TOP_K_PER_RETRIEVER = 50
RRF_K = 60
RERANK_THRESHOLD = 0.40
FINAL_MIN_K = 3
FINAL_MAX_K = 5
BI_ENCODER = "sentence-transformers/all-MiniLM-L6-v2"
CROSS_ENCODER = "cross-encoder/ms-marco-MiniLM-L-6-v2"

# --- Agent control plane (Section 6) ---
CIRCUIT_BREAKER_MAX_INVALID = 2     # halt when consecutive invalid count exceeds this
MAX_AGENT_ITERATIONS = 8

# --- Claude backend (opt-in; the only permitted external call) ---
ENABLE_CLAUDE_ENV = "PHARMA_ENABLE_CLAUDE"
LLM_MODEL = os.environ.get("PHARMA_LLM_MODEL", "claude-opus-5-5")


def claude_enabled() -> bool:
    return os.environ.get(ENABLE_CLAUDE_ENV) == "1"


DISCLAIMER = (
    "Training prototype with fictional data. This tool does not assess causality, "
    "recommend treatment, determine regulatory reportability, or make clinical or "
    "regulatory decisions."
)
