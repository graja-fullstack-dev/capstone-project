import numpy as np

from pharma_intake.rag.answer import NO_RESULT, compose_answer
from pharma_intake.rag.bm25 import BM25Retriever, tokenize
from pharma_intake.rag.chunker import chunk_documents, chunk_text
from pharma_intake.rag.corpus import load_sops
from pharma_intake.rag.fusion import rrf
from pharma_intake.rag.pipeline import HybridRetriever
from pharma_intake.rag.rerank import rerank, sigmoid


def test_chunker_sizes_and_overlap():
    words = [f"w{i}" for i in range(1200)]
    chunks = chunk_text(" ".join(words))
    assert [len(c.split()) for c in chunks] == [512, 512, 304]
    assert chunks[1].split()[:64] == chunks[0].split()[-64:]


def test_tokenizer_keeps_codes_and_parts():
    assert {"lot-88392", "lot", "88392"} <= set(tokenize("LOT-88392"))


def test_bm25_exact_lot_hit_ranks_first():
    chunks = [{"chunk_id": str(i), "title": t, "text": x} for i, (t, x) in enumerate([
        ("A", "tablets discolored LOT-45210 blister"), ("B", "anaphylaxis reported LOT-88392 injection"), ("C", "general SOP text")])]
    hits = BM25Retriever(chunks).search("LOT-88392")
    assert hits[0][0] == 1


def test_rrf_math_k60():
    fused = dict(rrf([[10, 20], [20, 30]], k=60))
    assert abs(fused[20] - (1 / 62 + 1 / 61)) < 1e-12
    assert abs(fused[10] - 1 / 61) < 1e-12 and abs(fused[30] - 1 / 62) < 1e-12
    assert rrf([[10, 20], [20, 30]])[0][0] == 20


def test_rerank_threshold_040_and_top5():
    cands = [{"chunk_id": str(i), "title": "t", "text": "x", "source": "s"} for i in range(8)]
    raw = [3, 2.5, 2, 1.5, 1, 0.5, -0.5, -3]  # logits; sigmoid(-0.5)=0.378 < 0.40
    kept, _ = rerank("q", cands, lambda q, t: raw)
    assert len(kept) == 5 and all(c["rerank_score"] >= 0.40 for c in kept)
    kept_all, _ = rerank("q", cands, lambda q, t: raw, max_k=10)
    assert len(kept_all) == 6 and abs(sigmoid(0.0) - 0.5) < 1e-9


def test_nothing_above_threshold_gives_no_result_not_a_guess():
    kept, _ = rerank("q", [{"chunk_id": "1", "title": "t", "text": "x", "source": "s"}], lambda q, t: [-4])
    assert kept == [] and compose_answer("q", kept) == NO_RESULT


def test_pipeline_with_fake_models_and_dense_cache(tmp_path):
    chunks = chunk_documents(load_sops())
    calls = []

    def enc(texts):
        calls.append(len(texts))
        return np.stack([np.random.default_rng(sum(map(ord, t)) % 9973).normal(size=16) for t in texts])

    def fake_score(q, texts):
        return [5.0 if "lot" in t.lower() else -5.0 for t in texts]

    r = HybridRetriever(chunks, enc, fake_score, cache_dir=tmp_path)
    res = r.search("lot number format")
    assert res.hits and all(h["rerank_score"] >= 0.40 for h in res.hits) and "Training prototype" in res.answer
    assert {"stage1_bm25", "stage2_dense", "stage3_rrf_pool_size", "stage4_scored"} <= set(res.stages)
    HybridRetriever(chunks, enc, fake_score, cache_dir=tmp_path)  # second build must reuse the cache
    assert calls.count(len(chunks)) == 1
