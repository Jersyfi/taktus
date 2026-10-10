"""The loopback connector: Taktus reached by Taktus, through the connector port.

A process that Taktus runs for itself — the removal test of `blueprints/self-operation/` —
needs to read the configuration of the instance it runs in, exercise processes with an
integration withheld, and record what it found. A process may also have the instance run the
conformance suite of an integration's contract and record that (ADR-0044). Nothing is called
directly (CLAUDE.md §6): the process names the capabilities `orchestrator.integrations`,
`orchestrator.removal`, `orchestrator.maturity` and `orchestrator.conformance`, and this
connector serves them. It is an adapter like any other —
behind the action side of the connector port, with a declaration the run reads — and it
imports no component: what it needs from the instance is the `Orchestrator` protocol below,
which the composition root implements over the instance's own services
(`composition/loopback.py`). In an installation with several instances the same capabilities
can be served over the HTTP surface instead; the process does not change.

The guides of the repository (UC-13.6) are rendered, measured and published by a process too,
S-05 of `blueprints/self-operation/`. What it asks of the instance is the capability
`orchestrator.guides`: the files a manifest names, the pages rendered from them at one commit,
the pages measured against one reading of the knowledge system, the pages published against that
reading, and a report of every page a person edited there. The instance answers through the
`Guides` protocol below, which the composition root implements over the knowledge and reporting
components (`composition/guides.py`, ADR-0066).

Every operation but two declares effect `read`. The effect field says whether an operation's
effect leaves Taktus (contracts/connector/v1 §3); a rehearsal run inside Taktus and a record in
the catalog do not leave it, so no egress entry is written for them (ADR-0022). Running a
conformance suite does leave it: the suite posts assignments to a worker, calls a model, and
writes records through a connector into the target its scenario names. That operation declares
effect `write` with idempotency `none`: a repeat runs the suite again, so the run never repeats
it on its own. Publishing the guides leaves it too: the pages are written into the knowledge
system through the capability `knowledge.pages`. That operation declares effect `write` with
idempotency `marked`, because every page is written under a key derived from the run and the
page's place, which the knowledge system keeps beside the page. Raising the report of a hand edit
is a record of the reporting component, which delivers it and records the delivery itself, as
it does for a decision request: that operation is a `read`. Each call is counted as one unit of
quota, as a connector call is; publishing counts the calls it made of the knowledge system.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from taktus.ports.connector import (
    CallContext,
    CallFailed,
    Capabilities,
    Cause,
    ConnectorError,
    Effect,
    EffectReport,
    Error,
    Record,
    Result,
)
from taktus.shared.v1 import Consumption

ADAPTER = "connector.loopback"
"""The adapter identifier the ledger records for this connector."""

INTEGRATIONS = "orchestrator.integrations"
REMOVAL = "orchestrator.removal"
MATURITY = "orchestrator.maturity"
CONFORMANCE = "orchestrator.conformance"
GUIDES = "orchestrator.guides"

LIST = f"{INTEGRATIONS}.list"
DESCRIBE = f"{INTEGRATIONS}.describe"
EXERCISE = f"{REMOVAL}.exercise"
RECORD = f"{MATURITY}.record"
RUN_SUITE = f"{CONFORMANCE}.run"
GUIDE_SOURCES = f"{GUIDES}.sources"
GUIDE_RENDER = f"{GUIDES}.render"
GUIDE_MEASURE = f"{GUIDES}.measure"
GUIDE_PUBLISH = f"{GUIDES}.publish"
GUIDE_REPORT = f"{GUIDES}.report"


class UnknownIntegration(LookupError):
    """The integration named is not configured in this instance."""


class Orchestrator(Protocol):
    """What the connector needs from the instance it runs in. Every document is JSON-shaped:
    the connector passes it through and validates nothing but the presence of what it needs."""

    async def list_integrations(self, tenant: str) -> list[dict[str, Any]]:
        """Every configured integration: `integration`, `family`, and what it serves."""
        ...

    async def describe(self, tenant: str, integration: str) -> dict[str, Any]:
        """One integration: what it serves, which other adapters serve the same, and which
        registered processes use it. Raises `UnknownIntegration`."""
        ...

    async def exercise(
        self, tenant: str, integration: str, *, run_id: str, identity: str
    ) -> dict[str, Any]:
        """Withhold the integration, exercise the processes that use it, restore it; the
        removal result as a document (`RemovalResult` of the catalog component). Raises
        `UnknownIntegration`."""
        ...

    async def record(self, tenant: str, result: dict[str, Any]) -> dict[str, Any]:
        """Write a removal result to the adapter's maturity and to the ledger; what the
        maturity now is and what is still missing."""
        ...

    async def conformance(
        self, tenant: str, integration: str, *, run_id: str, identity: str
    ) -> dict[str, Any]:
        """Run the conformance suite of the integration's contract against the endpoint the
        instance resolves for it, and record what it found: the outcome, the maturity and
        what is still missing, the ledger entry's `ledger_seq` and `content_digest`. Takes the
        identifier alone. Raises `UnknownIntegration`; `ValueError` when the suite cannot run
        as configured."""
        ...


class Guides(Protocol):
    """What the connector needs from the instance for the guides (UC-13.6, ADR-0066). Every
    document is JSON-shaped and passed through; the instance validates it. A document the
    instance cannot read raises `ValueError`, naming what is wrong."""

    async def sources(self, manifest: str) -> dict[str, Any]:
        """The files the manifest's pages take parts from: `paths`."""
        ...

    async def render(
        self,
        manifest: str,
        manifest_path: str,
        commit: str,
        files: list[Any],
        places: dict[str, Any],
    ) -> dict[str, Any]:
        """Every page of every guide, rendered from the files as they are at the commit:
        `commit`, `root` — the place at or below which every guide lies — and `rendered`, the
        document the next operations take."""
        ...

    async def measure(self, rendered: dict[str, Any], held: list[Any]) -> dict[str, Any]:
        """Every page measured against one reading of the knowledge system: `pages`, each with
        its state and what is done with it, and how many are written, kept and withheld."""
        ...

    async def publish(
        self, context: CallContext, rendered: dict[str, Any], held: list[Any]
    ) -> dict[str, Any]:
        """The pages published against that reading: `pages`, each with its action, the
        counts `created`, `updated`, `kept` and `withheld`, and `calls`, how many calls of the
        knowledge system it took."""
        ...

    async def report(
        self, tenant: str, publication: dict[str, Any], responsible: str, within_days: int
    ) -> dict[str, Any]:
        """A report of every page kept because a person's text stands, raised to whoever the
        tenant's owner-facing channel reaches with the role `responsible`: `reports`, their
        identifiers."""
        ...


DECLARATION = Capabilities.model_validate(
    {
        "contract": "connector/v1",
        "version": "1",
        "capabilities": [INTEGRATIONS, REMOVAL, MATURITY, CONFORMANCE, GUIDES],
        "operations": [
            {
                "name": LIST,
                "capability": INTEGRATIONS,
                "effect": "read",
                "demand": {"quota_units": 1},
                "summary": "Every integration configured in this instance, by family.",
            },
            {
                "name": DESCRIBE,
                "capability": INTEGRATIONS,
                "effect": "read",
                "demand": {"quota_units": 1},
                "summary": "One integration: what it serves, its alternatives, the processes "
                "that use it.",
            },
            {
                "name": EXERCISE,
                "capability": REMOVAL,
                "effect": "read",
                "demand": {"quota_units": 1},
                "summary": "Withhold the integration, exercise the processes that use it, "
                "restore it; the removal result.",
            },
            {
                "name": RECORD,
                "capability": MATURITY,
                "effect": "read",
                "demand": {"quota_units": 1},
                "summary": "Record a removal result in the adapter's maturity and the ledger.",
            },
            {
                "name": RUN_SUITE,
                "capability": CONFORMANCE,
                "effect": "write",
                "idempotency": "none",
                "demand": {"quota_units": 1},
                "summary": "Run the conformance suite of an integration's contract against "
                "the endpoint the instance resolves for it, and record the outcome in its "
                "maturity and the ledger. Takes the integration's identifier alone.",
            },
            {
                "name": GUIDE_SOURCES,
                "capability": GUIDES,
                "effect": "read",
                "demand": {"quota_units": 1},
                "summary": "The files the guides' manifest takes parts from.",
            },
            {
                "name": GUIDE_RENDER,
                "capability": GUIDES,
                "effect": "read",
                "demand": {"quota_units": 1},
                "summary": "Every page of the guides, rendered by rule from the repository's "
                "files as they are at one commit.",
            },
            {
                "name": GUIDE_MEASURE,
                "capability": GUIDES,
                "effect": "read",
                "demand": {"quota_units": 1},
                "summary": "Every rendered page measured by rule against one reading of the "
                "knowledge system.",
            },
            {
                "name": GUIDE_PUBLISH,
                "capability": GUIDES,
                "effect": "write",
                "idempotency": "marked",
                "demand": {"quota_units": 40},
                "summary": "The rendered pages put into the knowledge system against one "
                "reading of it; a page a person edited there is kept, and its difference "
                "returned.",
            },
            {
                "name": GUIDE_REPORT,
                "capability": GUIDES,
                "effect": "read",
                "demand": {"quota_units": 1},
                "summary": "A report of every page kept because a person's text stands, raised "
                "to whoever the owner-facing channel reaches with the role named.",
            },
        ],
        "credentials": [],
        "consumption": {"kinds": ["quota"], "unit": "calls", "window_seconds": 3600},
        "permissions": "passthrough",
    }
)


class LoopbackConnector:
    """Bound to its orchestrator after construction: the connector sits in the pool the run
    engine resolves from, and the orchestrator needs that engine — so the composition root
    creates the connector first, the engine second, and binds the orchestrator last."""

    def __init__(
        self, orchestrator: Orchestrator | None = None, guides: Guides | None = None
    ) -> None:
        self._orchestrator = orchestrator
        self._guides = guides

    def bind(self, orchestrator: Orchestrator | None = None, guides: Guides | None = None) -> None:
        if orchestrator is not None:
            self._orchestrator = orchestrator
        if guides is not None:
            self._guides = guides

    async def capabilities(self) -> Capabilities:
        return DECLARATION

    async def call(self, operation: str, context: CallContext, input: Mapping[str, Any]) -> Result:
        try:
            if operation.startswith(f"{GUIDES}."):
                return await self._guide(operation, context, dict(input))
            if self._orchestrator is None:
                raise ConnectorError("the loopback connector is not bound to an instance")
            output = await self._dispatch(self._orchestrator, operation, context, dict(input))
        except UnknownIntegration as error:
            raise CallFailed(operation, _failure(Cause.NOT_FOUND, str(error))) from error
        except (KeyError, TypeError, ValueError) as error:
            raise CallFailed(
                operation, _failure(Cause.INVALID, f"{type(error).__name__}: {error}")
            ) from error
        return Result(
            output=output,
            effect=_effect(operation, output),
            consumption=Consumption(quota_units=1),
        )

    async def _dispatch(
        self,
        orchestrator: Orchestrator,
        operation: str,
        context: CallContext,
        input: dict[str, Any],
    ) -> dict[str, Any]:
        tenant = context.tenant
        if operation == LIST:
            return {"integrations": await orchestrator.list_integrations(tenant)}
        if operation == DESCRIBE:
            return await orchestrator.describe(tenant, _name(input))
        if operation == EXERCISE:
            return await orchestrator.exercise(
                tenant, _name(input), run_id=context.run_id, identity=context.identity
            )
        if operation == RECORD:
            result = input["result"]
            if not isinstance(result, Mapping):
                raise ValueError("`result` is the document the exercise answered")
            return await orchestrator.record(tenant, dict(result))
        if operation == RUN_SUITE:
            return await orchestrator.conformance(
                tenant, _name(input), run_id=context.run_id, identity=context.identity
            )
        raise CallFailed(operation, _failure(Cause.NOT_FOUND, f"no operation {operation!r}"))

    async def _guide(self, operation: str, context: CallContext, input: dict[str, Any]) -> Result:
        guides = self._guides
        if guides is None:
            raise CallFailed(
                operation, _failure(Cause.NOT_FOUND, "this instance publishes no guides")
            )
        if operation == GUIDE_SOURCES:
            output = await guides.sources(_text(input, "manifest"))
        elif operation == GUIDE_RENDER:
            output = await guides.render(
                _text(input, "manifest"),
                _text(input, "manifest_path"),
                _text(input, "commit"),
                _list(input, "files"),
                _mapping(input, "places"),
            )
        elif operation == GUIDE_MEASURE:
            output = await guides.measure(_mapping(input, "rendered"), _list(input, "held"))
        elif operation == GUIDE_PUBLISH:
            output = await guides.publish(
                context, _mapping(input, "rendered"), _list(input, "held")
            )
            return Result(
                output=output,
                effect=_published(output),
                consumption=Consumption(quota_units=max(1, int(output.get("calls", 1)))),
            )
        elif operation == GUIDE_REPORT:
            days = input.get("within_days", 7)
            if not isinstance(days, int) or isinstance(days, bool) or days < 0:
                raise ValueError("`within_days` is a number of days, zero or more")
            output = await guides.report(
                context.tenant,
                _mapping(input, "publication"),
                _text(input, "responsible"),
                days,
            )
        else:
            raise CallFailed(operation, _failure(Cause.NOT_FOUND, f"no operation {operation!r}"))
        return Result(
            output=output,
            effect=EffectReport(kind=Effect.READ),
            consumption=Consumption(quota_units=1),
        )


def _published(output: Mapping[str, Any]) -> EffectReport:
    """The pages written are the records that went out. A publication that wrote none acted on
    nothing, as a repeat does: it is reported replayed, naming every page it measured."""
    pages = [p for p in output.get("pages", ()) if isinstance(p, Mapping)]
    written = [p for p in pages if p.get("action") in ("created", "updated")]
    named = written or pages
    if not named:
        raise ValueError("a publication names at least one page")
    return EffectReport(
        kind=Effect.WRITE,
        replayed=not written,
        records=tuple(
            Record(kind="knowledge.page", id="/".join(str(n) for n in p.get("place", ())) or "-")
            for p in named
        ),
    )


def _text(input: Mapping[str, Any], name: str) -> str:
    value = input[name]
    if not isinstance(value, str) or not value:
        raise ValueError(f"`{name}` is a text")
    return value


def _list(input: Mapping[str, Any], name: str) -> list[Any]:
    value = input[name]
    if not isinstance(value, list):
        raise ValueError(f"`{name}` is a list")
    return value


def _mapping(input: Mapping[str, Any], name: str) -> dict[str, Any]:
    value = input.get(name, {})
    if not isinstance(value, Mapping):
        raise ValueError(f"`{name}` is an object")
    return dict(value)


def _effect(operation: str, output: Mapping[str, Any]) -> EffectReport:
    """A read for every operation but the suite's run, which reports the ledger entry that
    records it as the record that went out, and the digest of its evidence."""
    if operation != RUN_SUITE:
        return EffectReport(kind=Effect.READ)
    return EffectReport(
        kind=Effect.WRITE,
        replayed=False,
        records=(Record(kind="conformance.tested", id=str(output["ledger_seq"])),),
        content_digest=output.get("content_digest"),
    )


def _name(input: Mapping[str, Any]) -> str:
    integration = input["integration"]
    if not isinstance(integration, str) or not integration:
        raise ValueError("`integration` is the adapter identifier, such as worker.endpoint")
    return integration


def _failure(cause: Cause, detail: str) -> Error:
    return Error.model_validate(
        {"class": "failure", "cause": cause, "effect": "none", "retryable": False, "detail": detail}
    )
