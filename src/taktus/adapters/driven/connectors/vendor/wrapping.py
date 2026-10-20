"""A vendor's MCP server as operations of the connector contract (ADR-0117).

Two ways in, and one rule between them: **an effect nobody declared is never believed to stay
inside.**

- **With a manifest**, the operations are what the manifest lists, and nothing else. A tool it
  calls a read must not be one its vendor marks as acting.
- **Without one**, the operations are the tools the vendor marks as reading, each a read. Every
  other tool is withheld: it is not declared and not served, so a call to it is refused before
  the vendor's server is reached.

Every call reads the vendor's tool listing again, in the same session and with the same
credential, before it calls the tool. A tool that has gone, or that its vendor now marks as
acting where it is declared a read, is refused as `unexpected` and not called: the interface
changed under the declaration (ADR-0047). That is two requests per call, and the default
demand says so.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

from taktus.adapters.driven.connectors.serving import Call, Outcome, TargetError, invalid
from taktus.adapters.driven.connectors.vendor.manifest import Manifest, ManifestRecord
from taktus.adapters.driven.connectors.vendor.upstream import (
    Exchange,
    Upstream,
    VendorTool,
    refusal,
)

type Json = dict[str, Any]

CONTRACT = "connector/v1"
VERSION = "1.0.0"
DEFAULT_CREDENTIAL = "VENDOR_TOKEN"
REQUESTS_PER_CALL = 2
"""The listing and the call: what one operation costs at the vendor's server."""
SUMMARY_LIMIT = 500
DETAIL_LIMIT = 300


@dataclass(frozen=True)
class Planned:
    """One declared operation, and how it reaches the vendor's tool."""

    name: str
    capability: str
    tool: str
    effect: str
    summary: str
    idempotency: str | None = None
    key_argument: str | None = None
    replayed: str | None = None
    record: ManifestRecord | None = None
    demand: Json | None = None

    @property
    def outward(self) -> bool:
        return self.effect != "read"

    def declared(self) -> Json:
        operation: Json = {
            "name": self.name,
            "capability": self.capability,
            "effect": self.effect,
            "demand": self.demand or {"quota_units": REQUESTS_PER_CALL},
            "summary": self.summary,
        }
        if self.idempotency is not None:
            operation["idempotency"] = self.idempotency
        return operation


@dataclass(frozen=True)
class Withheld:
    """A tool of the vendor's server that is not served, and why."""

    tool: str
    reason: str


@dataclass(frozen=True)
class Plan:
    """What the connector declares, and what it withheld."""

    capabilities: tuple[str, ...]
    credential: str
    operations: tuple[Planned, ...]
    manifest: str | None
    """The digest of the manifest; None when the server is served without one."""
    withheld: tuple[Withheld, ...] = ()

    def declaration(self) -> Json:
        wrapped: Json = {} if self.manifest is None else {"manifest": self.manifest}
        return {
            "contract": CONTRACT,
            "version": VERSION,
            "capabilities": list(self.capabilities),
            "operations": [op.declared() for op in self.operations],
            "credentials": [{"name": self.credential, "purpose": "actions"}],
            "consumption": {"kinds": ["quota"], "unit": "requests", "window_seconds": 60},
            "permissions": "passthrough",
            "wrapped": wrapped,
        }


class PlanError(ValueError):
    """The vendor's server cannot be served as declared."""


def _summary(tool: str, description: str | None) -> str:
    text = " ".join((description or "").split())
    return text[:SUMMARY_LIMIT] if text else f"The vendor's tool {tool}."


def operation_segment(tool: str) -> str:
    """The last segment of an operation name for a tool's name: lowercase, every character the
    contract does not allow in a segment replaced by `_`, a letter first."""
    segment = re.sub(r"[^a-z0-9_-]", "_", tool.lower())
    return segment if segment[:1].isalpha() else "t" + segment


def without_manifest(
    tools: list[VendorTool], capability: str, credential: str = DEFAULT_CREDENTIAL
) -> Plan:
    """The tools the vendor marks as reading, each a read of `capability`; every other tool
    withheld. Raises `PlanError` when nothing is left to serve."""
    withheld: list[Withheld] = []
    candidates: dict[str, list[VendorTool]] = {}
    for tool in tools:
        if not tool.marked_as_reading:
            withheld.append(
                Withheld(
                    tool.name,
                    "its vendor does not mark it as only reading; a manifest can declare its "
                    "effect",
                )
            )
            continue
        candidates.setdefault(f"{capability}.{operation_segment(tool.name)}", []).append(tool)
    operations: list[Planned] = []
    for name, same in sorted(candidates.items()):
        if len(same) > 1:
            withheld.extend(
                Withheld(t.name, f"another tool's name gives the same operation {name}")
                for t in same
            )
            continue
        tool = same[0]
        operations.append(
            Planned(name, capability, tool.name, "read", _summary(tool.name, tool.description))
        )
    if not operations:
        raise PlanError(
            "the vendor's server marks no tool as only reading, so without a manifest there is "
            "nothing to serve"
        )
    return Plan((capability,), credential, tuple(operations), None, tuple(withheld))


def with_manifest(manifest: Manifest, digest: str, tools: list[VendorTool] | None = None) -> Plan:
    """The operations the manifest lists. Where the vendor's listing is at hand (`tools`), a
    tool it does not list, or one declared a read that its vendor marks as acting, is a
    `PlanError`; every tool it lists that the manifest does not is withheld."""
    listed = {tool.name: tool for tool in tools} if tools is not None else None
    operations: list[Planned] = []
    for op in manifest.operations:
        if listed is not None:
            problem = contradiction(op.effect.value, listed.get(op.tool), op.tool)
            if problem:
                raise PlanError(problem)
        description = listed[op.tool].description if listed is not None else None
        operations.append(
            Planned(
                name=op.name,
                capability=op.capability,
                tool=op.tool,
                effect=op.effect.value,
                summary=op.summary or _summary(op.tool, description),
                idempotency=None if op.idempotency is None else op.idempotency.value,
                key_argument=op.key_argument,
                replayed=op.replayed,
                record=op.record,
                demand=None if op.demand is None else op.demand.document(),
            )
        )
    declared = {op.tool for op in manifest.operations}
    withheld = tuple(
        Withheld(name, "the manifest does not list it")
        for name in sorted(listed or {})
        if name not in declared
    )
    return Plan(
        tuple(manifest.capabilities),
        manifest.credential,
        tuple(operations),
        digest,
        withheld,
    )


def contradiction(effect: str, tool: VendorTool | None, name: str) -> str | None:
    """Why the vendor's listing does not admit the declared effect, or None."""
    if tool is None:
        return f"the vendor's server does not list the tool {name!r}"
    if effect == "read" and tool.marked_as_acting:
        return (
            f"the tool {name!r} is declared a read, and its vendor marks it as doing more than "
            "reading"
        )
    return None


def pointer(document: Any, path: str) -> Any:
    """The value a JSON pointer (RFC 6901) names in `document`; KeyError when there is none."""
    current = document
    for raw in path.split("/")[1:]:
        segment = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict) and segment in current:
            current = current[segment]
        elif isinstance(current, list) and segment.isdigit() and int(segment) < len(current):
            current = current[int(segment)]
        else:
            raise KeyError(path)
    return current


@dataclass(frozen=True)
class Wrapper:
    """The connector's configuration: where the vendor answers, and what is declared."""

    upstream: Upstream
    plan: Plan

    def operations(self) -> dict[str, Any]:
        """One operation function per declared operation, as `serving.Served` takes them."""
        functions: dict[str, Any] = {}
        for planned in self.plan.operations:

            async def operation(
                config: Wrapper, call: Call, input: Json, planned: Planned = planned
            ) -> Outcome:
                return await config.invoke(planned, call, input)

            functions[planned.name] = operation
        return functions

    async def invoke(self, planned: Planned, call: Call, input: Json) -> Outcome:
        arguments = dict(input)
        if planned.key_argument is not None:
            if planned.key_argument in arguments:
                raise invalid(
                    f"the input names {planned.key_argument!r}, which carries the idempotency key"
                )
            arguments[planned.key_argument] = call.key
        sent = False
        failure: TargetError | None = None
        exchange = Exchange()
        try:
            async with self.upstream.session(call.token, exchange) as session:
                call.count()
                problem = contradiction(
                    planned.effect,
                    {t.name: t for t in await session.tools()}.get(planned.tool),
                    planned.tool,
                )
                if problem:
                    failure = TargetError(
                        "unexpected",
                        "none",
                        False,
                        f"{problem}; the interface changed under the declaration, and the "
                        "tool was not called",
                    )
                else:
                    call.count()
                    sent = True
                    answer = await session.call(planned.tool, arguments)
        except Exception as error:
            raise self._failed(planned, error, exchange, sent=sent) from None
        if failure is not None:
            raise failure
        if answer.is_error:
            raise invalid(
                "the vendor's tool answered with an error: "
                + (" ".join(answer.text.split())[:DETAIL_LIMIT] or "without a text")
            )
        output: Json = (
            dict(answer.structured)
            if isinstance(answer.structured, dict)
            else {"text": answer.text}
        )
        if not planned.outward:
            return Outcome(output=output, effect={"kind": "read"})
        return Outcome(output=output, effect=self._effect(planned, answer.structured, arguments))

    def _effect(self, planned: Planned, structured: Any, arguments: Json) -> Json:
        record = planned.record
        if record is None:  # unreachable: the manifest names a record for every outward tool
            raise self._unread(planned, "the operation names no record")
        try:
            identifier = pointer(structured, record.id)
            replayed = (
                pointer(structured, planned.replayed) if planned.replayed is not None else False
            )
        except KeyError as missing:
            raise self._unread(planned, f"the answer has nothing at {missing.args[0]}") from None
        if not isinstance(identifier, str | int) or isinstance(identifier, bool):
            raise self._unread(planned, f"the answer at {record.id} is not an identifier")
        if not isinstance(replayed, bool):
            raise self._unread(planned, f"the answer at {planned.replayed} is not true or false")
        entry: Json = {"kind": record.kind, "id": str(identifier)}
        if record.url is not None:
            try:
                url = pointer(structured, record.url)
            except KeyError:
                url = None
            if isinstance(url, str) and url:
                entry["url"] = url
        canonical = json.dumps(arguments, sort_keys=True, separators=(",", ":"))
        return {
            "kind": planned.effect,
            "replayed": replayed,
            "records": [entry],
            "content_digest": "sha256:" + hashlib.sha256(canonical.encode()).hexdigest(),
        }

    def _unread(self, planned: Planned, why: str) -> TargetError:
        """An answer to an outward call that cannot be read: the vendor may have acted."""
        return TargetError(
            "unknown",
            "unknown",
            planned.idempotency == "native",
            f"the vendor's tool answered, and the answer cannot be read: {why}",
        )

    def _failed(
        self, planned: Planned, error: Exception, exchange: Exchange, *, sent: bool
    ) -> TargetError:
        """A request that failed. The type alone: an error's text can quote the request."""
        status = exchange.refused
        what = f"{type(error).__name__} at {self.upstream.where}"
        if status == 401:
            return TargetError(
                "unauthenticated",
                "none",
                False,
                "the vendor's server did not accept the requesting identity's credential",
            )
        if status == 403:
            return TargetError(
                "forbidden",
                "none",
                False,
                "the vendor's server refused the requesting identity",
            )
        refused = refusal(error)
        if refused is not None:
            return invalid(
                f"the vendor's server refused the request: {refused.error.message[:DETAIL_LIMIT]}"
            )
        if sent and planned.outward:
            return TargetError(
                "unknown",
                "unknown",
                planned.idempotency == "native",
                f"the call was sent and its answer did not arrive: {what}",
            )
        return TargetError("unavailable", "none", True, f"the vendor's server failed: {what}")
