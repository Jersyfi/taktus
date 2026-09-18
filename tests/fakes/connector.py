"""A connector behind the action port that keeps its records in memory and honours the
contract's idempotency the way a `marked` target does: a write repeated with a key it has
seen returns the original record with `replayed: true`; a write with a new key acts again.

Three operations are declared: a read, a marked write and a write with `idempotency: none`.
`fail_next` makes the next call of an operation answer with a classified error; `unreachable`
makes every call raise ConnectorError, as a connector that is down does.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from taktus.ports.connector import (
    CallContext,
    CallFailed,
    Capabilities,
    ConnectorError,
    Effect,
    EffectReport,
    Error,
    Record,
    Result,
)
from taktus.shared.v1 import Consumption

READ = "fake.records.read"
WRITE = "fake.records.create"
BLIND = "fake.records.fire"


@dataclass
class FakeConnector:
    version: str | None = "1.2.3"
    records: dict[str, dict[str, Any]] = field(default_factory=dict)  # key -> record
    reads: dict[str, dict[str, Any]] = field(default_factory=dict)  # what a read answers, by id
    read_sequence: list[dict[str, Any]] = field(default_factory=list)  # successive read answers
    calls: list[tuple[str, CallContext, dict[str, Any]]] = field(default_factory=list)
    fail_next: dict[str, Error] = field(default_factory=dict)
    unreachable: str | None = None
    crash_after_acting: type[BaseException] | None = None
    """Raised after a write acted, before the answer: the instance dies with the effect
    outside and nothing persisted, which is what a recovery must cope with."""
    acted: int = 0

    async def capabilities(self) -> Capabilities:
        return Capabilities.model_validate(
            {
                "contract": "connector/v1",
                "version": self.version,
                "capabilities": ["fake.records"],
                "operations": [
                    {
                        "name": READ,
                        "capability": "fake.records",
                        "effect": "read",
                        "summary": "read",
                    },
                    {
                        "name": WRITE,
                        "capability": "fake.records",
                        "effect": "write",
                        "idempotency": "marked",
                        "summary": "create",
                    },
                    {
                        "name": BLIND,
                        "capability": "fake.records",
                        "effect": "write",
                        "idempotency": "none",
                        "summary": "fire",
                    },
                ],
                "credentials": [{"name": "FAKE_TOKEN", "purpose": "actions"}],
                "consumption": {"kinds": ["quota"], "unit": "requests", "window_seconds": 60},
                "permissions": "passthrough",
            }
        )

    async def call(self, operation: str, context: CallContext, input: Mapping[str, Any]) -> Result:
        self.calls.append((operation, context, dict(input)))
        if self.unreachable is not None:
            raise ConnectorError(self.unreachable)
        if (error := self.fail_next.pop(operation, None)) is not None:
            raise CallFailed(operation, error)
        if operation == READ:
            if self.read_sequence:
                answer = self.read_sequence.pop(0)
            else:
                answer = self.reads.get(
                    str(input.get("id")), {"id": input.get("id"), "found": False}
                )
            return Result(
                output=answer,
                effect=EffectReport(kind=Effect.READ),
                consumption=Consumption(quota_units=1),
            )
        if operation == WRITE:
            key = context.idempotency_key
            replayed = key in self.records
            if not replayed:
                self.acted += 1
                self.records[key] = {"id": f"rec_{len(self.records) + 1}", **dict(input)}
                if self.crash_after_acting is not None:
                    crash, self.crash_after_acting = self.crash_after_acting, None
                    raise crash
            record = self.records[key]
            return Result(
                output=dict(record),
                effect=EffectReport(
                    kind=Effect.WRITE,
                    replayed=replayed,
                    records=(Record(kind="record", id=record["id"]),),
                    content_digest=_digest(input),
                ),
                consumption=Consumption(quota_units=2 if replayed else 1),
            )
        if operation == BLIND:
            self.acted += 1
            return Result(
                output={"fired": True},
                effect=EffectReport(
                    kind=Effect.WRITE,
                    replayed=False,
                    records=(Record(kind="signal", id="fired"),),
                ),
                consumption=Consumption(quota_units=1),
            )
        raise ConnectorError(f"no such operation {operation}")


def failure(cause: str, *, effect: str = "none", retryable: bool = False) -> Error:
    return Error.model_validate(
        {
            "class": "failure",
            "cause": cause,
            "effect": effect,
            "retryable": retryable,
            "detail": f"the fake was told to fail with {cause}",
        }
    )


def _digest(input: Mapping[str, Any]) -> str:
    canonical = json.dumps(dict(input), sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(canonical).hexdigest()
