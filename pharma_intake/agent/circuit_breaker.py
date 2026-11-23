"""Step 5: halt when the exact same tool+arguments fail validation more than N consecutive times."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from .. import config


class CircuitOpen(Exception):
    def __init__(self, tool: str, count: int):
        super().__init__(f"Circuit breaker open: '{tool}' called with identical invalid arguments {count} times in a row")
        self.tool, self.count = tool, count


def signature(tool: str, args: Any) -> str:
    canon = json.dumps(args, sort_keys=True, default=str, separators=(",", ":"))
    return f"{tool}:{hashlib.sha256(canon.encode()).hexdigest()[:16]}"


class CircuitBreaker:
    def __init__(self, max_invalid: int = config.CIRCUIT_BREAKER_MAX_INVALID):
        self.max_invalid = max_invalid
        self._sig: str | None = None
        self._count = 0
        self.open = False
        self.tool: str | None = None

    def check(self) -> None:
        if self.open:
            raise CircuitOpen(self.tool or "?", self._count)

    def record(self, tool: str, args: Any, valid: bool) -> None:
        """Record a call outcome; opens the breaker when consecutive identical invalid calls exceed the limit."""
        if valid:
            self._sig, self._count = None, 0
            return
        sig = signature(tool, args)
        self._count = self._count + 1 if sig == self._sig else 1
        self._sig = sig
        if self._count > self.max_invalid:
            self.open, self.tool = True, tool
            raise CircuitOpen(tool, self._count)

    @property
    def consecutive_invalid(self) -> int:
        return self._count
