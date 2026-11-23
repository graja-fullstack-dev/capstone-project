"""Step 1: type-safe tool registry. Every call is repaired + validated against a Pydantic schema first."""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from typing import Any, Callable

from pydantic import BaseModel

from .. import repository, workflow
from ..schemas import SearchKnowledgeArgs, Status, SubmitIntakeReportArgs, UpdateStatusArgs
from ..validation import validate_with


@dataclass
class ToolResult:
    ok: bool
    content: str                       # JSON string (what the model / UI sees)
    repairs: list[str] = field(default_factory=list)
    validation_failed: bool = False    # True only for schema/argument errors (feeds the circuit breaker)


@dataclass
class AgentContext:
    conn: sqlite3.Connection
    retriever_factory: Callable[[], Any] | None = None    # returns HybridRetriever (lazy; models are heavy)
    actor: str = "agent"

    def retriever(self):
        """Rebuilt per search so newly saved reports are included; heavy models are cached in rag.models."""
        if self.retriever_factory is None:
            raise RuntimeError("Knowledge search is not configured")
        return self.retriever_factory()


def _inline_refs(schema: dict) -> dict:
    """Resolve $ref/$defs so the tool schema is self-contained for the LLM."""
    defs = schema.get("$defs", {})

    def walk(node):
        if isinstance(node, dict):
            if "$ref" in node:
                return walk(defs[node["$ref"].split("/")[-1]])
            return {k: walk(v) for k, v in node.items() if k not in ("$defs", "title")}
        if isinstance(node, list):
            return [walk(v) for v in node]
        return node
    return walk(schema)


@dataclass
class ToolSpec:
    name: str
    description: str
    model: type[BaseModel]
    handler: Callable[[AgentContext, Any], dict]

    def anthropic_def(self) -> dict:
        return {"name": self.name, "description": self.description,
                "input_schema": _inline_refs(self.model.model_json_schema())}


def _submit(ctx: AgentContext, a: SubmitIntakeReportArgs) -> dict:
    ref = repository.create_report(ctx.conn, a, actor=ctx.actor)
    return {"status": "saved", "ref_id": ref, "report_status": Status.NEW.value}


def _update(ctx: AgentContext, a: UpdateStatusArgs) -> dict:
    r = workflow.request_transition(ctx.conn, a.ref_id, a.target_status, actor=a.reviewer_code)  # WorkflowError -> is_error result
    if r["pending_approval"]:  # HITL gate: the agent can never approve its own closure request
        return {"status": "awaiting_human_approval", "ref_id": a.ref_id,
                "message": "Closure requested. The report is frozen until a human reviewer approves on the Review Approvals page."}
    return {"status": "updated", "ref_id": a.ref_id, "report_status": r["status"]}


def _search(ctx: AgentContext, a: SearchKnowledgeArgs) -> dict:
    res = ctx.retriever().search(a.query)
    return {"answer": res.answer,
            "sources": [{"source": c["source"], "chunk_id": c["chunk_id"], "relevance": round(c["rerank_score"], 3)} for c in res.hits],
            "stages": res.stages}


REGISTRY: dict[str, ToolSpec] = {t.name: t for t in [
    ToolSpec("submit_intake_report",
             "Save a new fictional intake report. Batch must match LOT-12345. Adverse events also need event_description and event_onset_date. Never include patient identifiers.",
             SubmitIntakeReportArgs, _submit),
    ToolSpec("update_status",
             "Request a status change: New -> In Review (immediate) or In Review -> Closed (requires human approval; report is frozen until a reviewer decides).",
             UpdateStatusArgs, _update),
    ToolSpec("search_knowledge",
             "Hybrid search (BM25 + semantic + RRF + cross-encoder) over SOPs and saved reports. Returns cited excerpts only.",
             SearchKnowledgeArgs, _search),
]}


def tool_definitions(names: list[str] | None = None) -> list[dict]:
    return [REGISTRY[n].anthropic_def() for n in (names or REGISTRY)]


def execute_tool(ctx: AgentContext, name: str, raw_args: Any) -> ToolResult:
    spec = REGISTRY.get(name)
    if spec is None:
        return ToolResult(False, json.dumps({"error": f"Unknown tool '{name}'", "available": list(REGISTRY)}), validation_failed=True)
    if not isinstance(raw_args, dict):
        return ToolResult(False, json.dumps({"error": "Tool arguments must be a JSON object"}), validation_failed=True)
    outcome = validate_with(spec.model, raw_args)
    if not outcome.ok:
        return ToolResult(False, json.dumps({"error": "validation_failed", "details": outcome.errors}),
                          repairs=outcome.repairs, validation_failed=True)
    try:
        payload = spec.handler(ctx, outcome.model)
    except Exception as exc:  # handler failure is not an argument error
        return ToolResult(False, json.dumps({"error": f"{type(exc).__name__}: {exc}"}), repairs=outcome.repairs)
    return ToolResult(True, json.dumps(payload, default=str), repairs=outcome.repairs)
