"""Corpus = fictional SOP markdown files + saved reports (only intake fields; no audit data)."""
from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

from .. import config


def load_sops(sop_dir: Path | None = None) -> list[dict]:
    docs = []
    for p in sorted((sop_dir or config.SOP_DIR).glob("*.md")):
        text = p.read_text(encoding="utf-8")
        title = next((ln.lstrip("# ").strip() for ln in text.splitlines() if ln.startswith("#")), p.stem)
        docs.append({"doc_id": f"SOP:{p.stem}", "source": f"SOP ({p.name})", "title": title, "text": text})
    return docs


def load_reports(conn: sqlite3.Connection) -> list[dict]:
    docs = []
    rows = conn.execute("SELECT r.*, a.event_description, a.event_onset_date FROM reports r"
                        " LEFT JOIN ae_details a ON a.ref_id = r.ref_id ORDER BY r.ref_id")
    for r in rows:
        lines = [f"Reference: {r['ref_id']}", f"Type: {r['report_type']}", f"Product: {r['product_name']}",
                 f"Batch/Lot: {r['batch_id']}", f"Date received: {r['date_received']}",
                 f"Reporter type: {r['reporter_type']}", f"Status: {r['status']}", f"Description: {r['description']}"]
        if r["event_description"]:
            lines += [f"Event description: {r['event_description']}", f"Event onset date: {r['event_onset_date']}"]
        docs.append({"doc_id": f"REPORT:{r['ref_id']}", "source": f"Report {r['ref_id']}",
                     "title": f"{r['report_type']} {r['ref_id']} - {r['product_name']} {r['batch_id']}",
                     "text": "\n".join(lines)})
    return docs


def build_corpus(conn: sqlite3.Connection | None = None, sop_dir: Path | None = None) -> list[dict]:
    docs = load_sops(sop_dir)
    if conn is not None:
        docs += load_reports(conn)
    return docs


def corpus_hash(chunks: list[dict]) -> str:
    h = hashlib.sha256()
    for c in chunks:
        h.update(c["chunk_id"].encode())
        h.update(c["text"].encode())
    return h.hexdigest()
