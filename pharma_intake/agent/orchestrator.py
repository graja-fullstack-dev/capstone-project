"""Runs one user request through the control plane: guardrails -> router -> validated tools -> breaker."""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from .. import audit, config
from .circuit_breaker import CircuitBreaker, CircuitOpen
from .llm import LLMBackend, RuleBasedBackend, default_backend
from .memory import LongTermMemory, ShortTermMemory
from .router import DIRECT_REPLY, Route, route as route_text
from .tools import AgentContext, execute_tool, tool_definitions

SYSTEM_PROMPT = (
    "You operate a fictional-data pharma safety intake tracker (training prototype). "
    "Use ONLY the provided tools to act; never invent reference IDs, lots or statuses. "
    "You must not assess causality, recommend treatment, determine regulatory reportability, or make clinical or "
    "regulatory decisions - decline politely. Never ask for or include patient identifiers. "
    "You can request a status change but cannot approve closure: In Review -> Closed always needs a human reviewer. "
    "If a tool returns a validation error, fix the arguments once using the error details, or ask the user for the missing information; "
    "do not repeat an identical failing call."
)
ROUTE_TOOLS = {Route.INTAKE: ["submit_intake_report"], Route.STATUS: ["update_status"]}


@dataclass
class AgentRun:
    route: Route
    reply: str
    trace: list[dict] = field(default_factory=list)
    circuit_open: bool = False
    sources: list[dict] = field(default_factory=list)
    stages: dict = field(default_factory=dict)


class Orchestrator:
    def __init__(self, ctx: AgentContext, backend: LLMBackend | None = None):
        self.ctx = ctx
        self.backend = backend or default_backend()
        self.short_term = ShortTermMemory()
        self.long_term = LongTermMemory(ctx.conn)

    # -- public --
    def handle(self, user_text: str) -> AgentRun:
        self.short_term.clear()
        chosen, category = route_text(user_text)
        self.short_term.add("Thought", f"Router selected '{chosen.value}' before any tool/LLM call")
        if chosen == Route.REFUSE:
            audit.log_event(self.ctx.conn, "REFUSED", actor=self.ctx.actor, fields=[category or "out_of_scope"])
            from ..guardrails import check_scope
            reply = check_scope(user_text)[1]  # type: ignore[index]
            return self._done(chosen, reply)
        if chosen == Route.DIRECT:
            return self._done(chosen, DIRECT_REPLY)
        breaker = CircuitBreaker()
        try:
            if chosen == Route.RAG:
                return self._rag(user_text, breaker)
            return self._llm_loop(chosen, user_text, breaker)
        except CircuitOpen as exc:
            audit.log_event(self.ctx.conn, "CIRCUIT_OPEN", actor=self.ctx.actor, fields=[exc.tool])
            self.short_term.add("Observation", str(exc))
            return self._done(chosen, f"Execution halted by the circuit breaker: {exc}. Please correct the input and try again.", circuit_open=True)

    # -- internals --
    def _done(self, route: Route, reply: str, **kw) -> AgentRun:
        return AgentRun(route=route, reply=reply, trace=self.short_term.render(), **kw)

    def _call(self, name: str, args, breaker: CircuitBreaker):
        breaker.check()
        self.short_term.add("Action", f"{name}({json.dumps(args, default=str)[:200]})")
        res = execute_tool(self.ctx, name, args)
        self.short_term.add("Observation", ("OK " if res.ok else "ERROR ") + res.content[:300])
        breaker.record(name, args, valid=not res.validation_failed)
        return res

    def _rag(self, text: str, breaker: CircuitBreaker) -> AgentRun:
        res = self._call("search_knowledge", {"query": text[:300]}, breaker)
        data = json.loads(res.content)
        if not res.ok:
            msg = "; ".join(data.get("details") or [data.get("error", "search failed")])
            return self._done(Route.RAG, f"Knowledge search failed: {msg}")
        return self._done(Route.RAG, data["answer"], sources=data["sources"], stages=data["stages"])

    def _llm_loop(self, chosen: Route, text: str, breaker: CircuitBreaker) -> AgentRun:
        tools = tool_definitions(ROUTE_TOOLS[chosen])
        messages: list[dict] = [{"role": "user", "content": text}]
        for _ in range(config.MAX_AGENT_ITERATIONS):
            turn = self.backend.respond(SYSTEM_PROMPT, messages, tools, chosen)
            if turn.text:
                self.short_term.add("Thought", turn.text)
            if not turn.tool_calls:
                return self._done(chosen, turn.text or "(no response)")
            messages.append({"role": "assistant", "content": turn.raw_content})
            results = []
            for call in turn.tool_calls:  # all results go back together in ONE user message
                res = self._call(call.name, call.args, breaker)
                results.append({"type": "tool_result", "tool_use_id": call.id, "content": res.content, "is_error": not res.ok})
            messages.append({"role": "user", "content": results})
        return self._done(chosen, f"Stopped after {config.MAX_AGENT_ITERATIONS} steps without a final answer.")


__all__ = ["Orchestrator", "AgentRun", "RuleBasedBackend"]
