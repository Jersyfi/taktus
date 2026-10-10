"""A knowledge system behind the action port that keeps its pages in memory and honours the
capability `knowledge.pages` the way a wiki behind a connector must (ADR-0065): a page has a text
and a mark kept beside it; a write names the digest it expects to replace and ends `conflict`
otherwise; a write whose key the page already carries, with the same text, is a repeat.

`edit` is a person changing a page by hand in the knowledge system; `before_write` runs once
before the next write acts, which is how a test makes a page change between the list and the
write.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from taktus.ports.connector import (
    CallContext,
    CallFailed,
    Capabilities,
    Effect,
    EffectReport,
    Error,
    Record,
    Result,
)
from taktus.shared.v1 import Consumption

CAPABILITY = "knowledge.pages"


def digest(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class StoredPage:
    body: str
    mark: str | None
    key: str | None = None


@dataclass
class FakeKnowledgeSystem:
    pages: dict[tuple[str, ...], StoredPage] = field(default_factory=dict)
    calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    before_write: Callable[[], None] | None = None

    def edit(self, place: tuple[str, ...], change: Callable[[str], str]) -> None:
        page = self.pages[place]
        page.body = change(page.body)

    def put_foreign(self, place: tuple[str, ...], body: str) -> None:
        self.pages[place] = StoredPage(body=body, mark=None)

    async def capabilities(self) -> Capabilities:
        operation = {"capability": CAPABILITY, "demand": {"quota_units": 1}, "summary": "page"}
        return Capabilities.model_validate(
            {
                "contract": "connector/v1",
                "version": "1",
                "capabilities": [CAPABILITY],
                "operations": [
                    {**operation, "name": f"{CAPABILITY}.list", "effect": "read"},
                    {**operation, "name": f"{CAPABILITY}.read", "effect": "read"},
                    {
                        **operation,
                        "name": f"{CAPABILITY}.write",
                        "effect": "write",
                        "idempotency": "marked",
                    },
                ],
                "credentials": [],
                "consumption": {"kinds": ["quota"], "unit": "calls", "window_seconds": 60},
                "permissions": "passthrough",
            }
        )

    async def call(self, operation: str, context: CallContext, input: Mapping[str, Any]) -> Result:
        self.calls.append((operation, dict(input)))
        place = tuple(input["place"])
        if operation == f"{CAPABILITY}.list":
            pages = [
                {"place": list(p), "digest": digest(s.body), "mark": s.mark}
                for p, s in sorted(self.pages.items())
                if p[: len(place)] == place
            ]
            return _read({"pages": pages})
        if operation == f"{CAPABILITY}.read":
            if place not in self.pages:
                raise CallFailed(operation, _failure("not_found", "no page"))
            stored = self.pages[place]
            return _read(
                {
                    "place": list(place),
                    "body": stored.body,
                    "digest": digest(stored.body),
                    "mark": stored.mark,
                }
            )
        if operation == f"{CAPABILITY}.write":
            if self.before_write is not None:
                hook, self.before_write = self.before_write, None
                hook()
            body, written = input["body"], digest(input["body"])
            stored = self.pages.get(place)
            if stored is not None and stored.key == context.idempotency_key:
                if digest(stored.body) == written:
                    return _written(place, written, replayed=True)
            held = digest(stored.body) if stored is not None else None
            if held != input["expected"]:
                raise CallFailed(operation, _failure("conflict", "the page changed"))
            self.pages[place] = StoredPage(
                body=body, mark=input["mark"], key=context.idempotency_key
            )
            return _written(place, written, replayed=False)
        raise CallFailed(operation, _failure("not_found", f"no operation {operation}"))


def _read(output: dict[str, Any]) -> Result:
    return Result(
        output=output, effect=EffectReport(kind=Effect.READ), consumption=Consumption(quota_units=1)
    )


def _written(place: tuple[str, ...], written: str, *, replayed: bool) -> Result:
    return Result(
        output={"place": list(place), "digest": written},
        effect=EffectReport(
            kind=Effect.WRITE,
            replayed=replayed,
            records=(Record(kind="page", id="/".join(place)),),
            content_digest=written,
        ),
        consumption=Consumption(quota_units=1),
    )


def _failure(cause: str, detail: str) -> Error:
    return Error.model_validate(
        {"class": "failure", "cause": cause, "effect": "none", "retryable": False, "detail": detail}
    )
