"""A stop to repetition (ADR-0132 §4 to §5, UC-8.12).

Two loops cost money without ever failing a run: a step that makes the same outward call with
the same arguments again and again, and a step whose model answers again and again with
nothing new between. Both are counted in the run's own ledger, and a rule stops the step at its
boundary before the call that would cross the tenant's limit.

- **The same outward call.** Before every outward connector call, the run records
  `connector.called` with the digest of the call's *identity*: the operation and the digest of
  its arguments. Two calls with the same operation and the same arguments have the same
  identity, whichever step made them.
- **The same model, again.** After every answer of a language model to a step, the run records
  `model.called` for the step. A step on a model receives no tool result: every answer of the
  step in the run counts.

The rule reads those entries and nothing else: given the same entries and the same limit, it
stops the same step (ADR-0023). Its facts are the record its `repetition.stopped` entry names.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from taktus.shared.v1 import LedgerEntry

CONNECTOR_CALLED = "connector.called"
"""An outward connector call is made now, with the digest of its identity."""
MODEL_CALLED = "model.called"
"""A language model answered a step."""
STOPPED = "repetition.stopped"
"""The rule stopped a step at its boundary; the outcome names the limit, `calls` or
`model_calls`."""
REJECTED = "rejected_by_repetition"
"""The outcome of the `step.rejected` entry of a step the rule stopped."""


def identity(operation: str, arguments: Mapping[str, Any]) -> dict[str, str]:
    """What makes two calls the same call: the operation and the digest of its arguments. The
    arguments themselves are never recorded."""
    canonical = json.dumps(arguments, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return {
        "operation": operation,
        "arguments_digest": "sha256:" + hashlib.sha256(canonical).hexdigest(),
    }


def calls(entries: Iterable[LedgerEntry], digest: str) -> int:
    """How often the call of this identity was made in the run the entries are of."""
    return sum(1 for e in entries if e.kind == CONNECTOR_CALLED and e.content_digest == digest)


def answers(entries: Iterable[LedgerEntry], step_id: str) -> int:
    """How often a model answered this step in the run the entries are of."""
    return sum(1 for e in entries if e.kind == MODEL_CALLED and e.refs.step_id == step_id)


@dataclass(frozen=True)
class Stop:
    """The rule fired: the limit it applied, the action, how often it was made, the limit."""

    rule: str
    action: str
    count: int
    limit: int

    def reason(self, step_id: str) -> str:
        what = (
            f"called {self.action} with the same arguments"
            if self.rule == "calls"
            else f"asked its model ({self.action}) without a new tool result"
        )
        return (
            f"step {step_id!r} {what} {self.count} time(s) in this run, and the tenant's limit "
            f"is {self.limit}: stopped at its boundary by rule, and an incident is raised "
            "(ADR-0132)"
        )

    def document(self, *, run_id: str, step_id: str, process_version: str) -> dict[str, Any]:
        return {
            "rule": f"repetition.{self.rule}",
            "run_id": run_id,
            "step_id": step_id,
            "process_version": process_version,
            "action": self.action,
            "count": self.count,
            "limit": self.limit,
        }


def stop(rule: str, action: str, count: int, limit: int) -> Stop | None:
    """The rule itself: the next call would be one more than the limit allows."""
    return Stop(rule=rule, action=action, count=count, limit=limit) if count >= limit else None
