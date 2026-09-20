"""The loopback connector: Taktus reached by Taktus, through the connector port.

A process that Taktus runs for itself — the removal test of `blueprints/self-operation/` —
needs to read the configuration of the instance it runs in, exercise processes with an
integration withheld, and record what it found. Nothing is called directly (CLAUDE.md §6): the
process names the capabilities `orchestrator.integrations`, `orchestrator.removal` and
`orchestrator.maturity`, and this connector serves them. It is an adapter like any other —
behind the action side of the connector port, with a declaration the run reads — and it
imports no component: what it needs from the instance is the `Orchestrator` protocol below,
which the composition root implements over the instance's own services
(`composition/loopback.py`). In an installation with several instances the same capabilities
can be served over the HTTP surface instead; the process does not change.

Every operation declares effect `read`. The effect field says whether an operation's effect
leaves Taktus (contracts/connector/v1 §3); a rehearsal run inside Taktus and a record in the
catalog do not leave it, so no egress entry is written for them (ADR-0022). Each call is
counted as one unit of quota, as a connector call is.
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
    Result,
)
from taktus.shared.v1 import Consumption

ADAPTER = "connector.loopback"
"""The adapter identifier the ledger records for this connector."""

INTEGRATIONS = "orchestrator.integrations"
REMOVAL = "orchestrator.removal"
MATURITY = "orchestrator.maturity"

LIST = f"{INTEGRATIONS}.list"
DESCRIBE = f"{INTEGRATIONS}.describe"
EXERCISE = f"{REMOVAL}.exercise"
RECORD = f"{MATURITY}.record"


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


DECLARATION = Capabilities.model_validate(
    {
        "contract": "connector/v1",
        "version": "1",
        "capabilities": [INTEGRATIONS, REMOVAL, MATURITY],
        "operations": [
            {
                "name": LIST,
                "capability": INTEGRATIONS,
                "effect": "read",
                "summary": "Every integration configured in this instance, by family.",
            },
            {
                "name": DESCRIBE,
                "capability": INTEGRATIONS,
                "effect": "read",
                "summary": "One integration: what it serves, its alternatives, the processes "
                "that use it.",
            },
            {
                "name": EXERCISE,
                "capability": REMOVAL,
                "effect": "read",
                "summary": "Withhold the integration, exercise the processes that use it, "
                "restore it; the removal result.",
            },
            {
                "name": RECORD,
                "capability": MATURITY,
                "effect": "read",
                "summary": "Record a removal result in the adapter's maturity and the ledger.",
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

    def __init__(self, orchestrator: Orchestrator | None = None) -> None:
        self._orchestrator = orchestrator

    def bind(self, orchestrator: Orchestrator) -> None:
        self._orchestrator = orchestrator

    async def capabilities(self) -> Capabilities:
        return DECLARATION

    async def call(self, operation: str, context: CallContext, input: Mapping[str, Any]) -> Result:
        if self._orchestrator is None:
            raise ConnectorError("the loopback connector is not bound to an instance")
        try:
            output = await self._dispatch(self._orchestrator, operation, context, dict(input))
        except UnknownIntegration as error:
            raise CallFailed(operation, _failure(Cause.NOT_FOUND, str(error))) from error
        except (KeyError, TypeError, ValueError) as error:
            raise CallFailed(
                operation, _failure(Cause.INVALID, f"{type(error).__name__}: {error}")
            ) from error
        return Result(
            output=output,
            effect=EffectReport(kind=Effect.READ),
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
        raise CallFailed(operation, _failure(Cause.NOT_FOUND, f"no operation {operation!r}"))


def _name(input: Mapping[str, Any]) -> str:
    integration = input["integration"]
    if not isinstance(integration, str) or not integration:
        raise ValueError("`integration` is the adapter identifier, such as worker.endpoint")
    return integration


def _failure(cause: Cause, detail: str) -> Error:
    return Error.model_validate(
        {"class": "failure", "cause": cause, "effect": "none", "retryable": False, "detail": detail}
    )
