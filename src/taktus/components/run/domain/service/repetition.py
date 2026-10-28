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

A worker's step is counted from what its worker reports (ADR-0144). A `tool.called` the worker
marks `outward` is recorded as `connector.called`, with the same identity: the tool and the
digest of the arguments the worker reported. A `model.called` is recorded as the engine's own.
A tool call that answers the step after a model's answer is recorded as `tool.result`, and the
model's answers are counted from there. The worker reports a call after it made it, so its step
is stopped at the worker's next boundary once a count has crossed the limit.

The rule reads those entries and nothing else: given the same entries and the same limit, it
stops the same step (ADR-0023). Its facts are the record its `repetition.stopped` entry names.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from taktus.shared.v1 import LedgerEntry

CONNECTOR_CALLED = "connector.called"
"""An outward connector call is made now, with the digest of its identity."""
MODEL_CALLED = "model.called"
"""A language model answered a step."""
TOOL_RESULT = "tool.result"
"""A worker's tool call answered its step after a model's answer: the model's next answer has
a tool result before it (ADR-0144)."""
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


def reported(operation: str, arguments_digest: str) -> dict[str, str]:
    """The identity of a call a worker reported: the tool and the digest of its arguments the
    worker computed. The worker never transmits the arguments themselves (W-09)."""
    return {"operation": operation, "arguments_digest": arguments_digest}


def calls(entries: Iterable[LedgerEntry], digest: str) -> int:
    """How often the call of this identity was made in the run the entries are of."""
    return sum(1 for e in entries if e.kind == CONNECTOR_CALLED and e.content_digest == digest)


def answers(entries: Iterable[LedgerEntry], step_id: str) -> int:
    """How often a model answered this step in the run the entries are of since the last tool
    result of the step. A step on the engine's own model receives no tool result: every answer
    counts."""
    count = 0
    for e in entries:
        if e.refs.step_id != step_id:
            continue
        if e.kind == MODEL_CALLED:
            count += 1
        elif e.kind == TOOL_RESULT:
            count = 0
    return count


@dataclass(frozen=True)
class Stop:
    """The rule fired: the limit it applied, the action, how often it was made, the limit."""

    rule: str
    action: str
    count: int
    limit: int
    worker: bool = False
    """Counted from a worker's reports, after the call was made: the worker is asked to stop at
    its next boundary (ADR-0144)."""

    def reason(self, step_id: str) -> str:
        what = (
            f"called {self.action} with the same arguments"
            if self.rule == "calls"
            else f"asked its model ({self.action}) without a new tool result"
        )
        where = (
            "its worker is stopped at its next boundary by rule"
            if self.worker
            else "stopped at its boundary by rule"
        )
        return (
            f"step {step_id!r} {what} {self.count} time(s) in this run, and the tenant's limit "
            f"is {self.limit}: {where}, and an incident is raised (ADR-0132)"
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


@dataclass
class Watch:
    """The rule over a worker's stream as it arrives (ADR-0144): seeded from the run's ledger,
    and kept in step with the entries the run records for each report. A count that crosses
    the limit is a stop; the call that crossed it was made already."""

    calls_limit: int
    model_calls_limit: int
    made: Counter[str] = field(default_factory=Counter)
    """How often each identity's call was made in the run, by its digest."""
    streak: int = 0
    """The model's answers of the step since its last tool result."""

    @classmethod
    def of(
        cls,
        entries: Iterable[LedgerEntry],
        step_id: str,
        *,
        calls_limit: int,
        model_calls_limit: int,
    ) -> Watch:
        seen = list(entries)
        made = Counter(
            e.content_digest
            for e in seen
            if e.kind == CONNECTOR_CALLED and e.content_digest is not None
        )
        return cls(
            calls_limit=calls_limit,
            model_calls_limit=model_calls_limit,
            made=made,
            streak=answers(seen, step_id),
        )

    def called(self, digest: str, action: str) -> Stop | None:
        """An outward call was made: a stop where it crossed the limit."""
        self.made[digest] += 1
        count = self.made[digest]
        if count > self.calls_limit:
            return Stop("calls", action, count, self.calls_limit, worker=True)
        return None

    def answered(self, action: str) -> Stop | None:
        """A model answered: a stop where its answers without a tool result crossed the limit."""
        self.streak += 1
        if self.streak > self.model_calls_limit:
            return Stop("model_calls", action, self.streak, self.model_calls_limit, worker=True)
        return None

    def resulted(self) -> bool:
        """A tool call answered the step: whether it ended a run of answers, and is recorded."""
        ended = self.streak > 0
        self.streak = 0
        return ended
