"""CONTRACT 2, the client side: how the core reaches a connector (contracts/connector/v1).

Two directions, governed differently (§1 of the contract). **Actions**: the core calls an
operation with a call context — who acts, for which step, under which idempotency key, with
which credential by name — and receives a result that repeats the operation's declared effect,
or a classified failure. **Intake**: a delivery — headers, the raw body, when it arrived —
becomes an accepted intake, the channel's half of a command, or a refusal with its reason.

The shapes are bound the way the worker contract's are (frozen, closed; `tests/contract` holds
them to `Connector.json` and its examples). The core never sees a URL or a transport; the
adapter under `adapters/driven/connectors/mcp` speaks MCP to the connector.

What the core does with a declaration is the point of the action direction: the effect of every
operation — `read`, `write`, `delivery` — is a field, so that the run records `write` and
`delivery` as egress entries (ADR-0022) without a judgement; and the idempotency of every
outward operation says whether the run may repeat a call whose outcome it does not know
(`native`, `marked`) or never may (`none`; ADR-0024).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal, Protocol

from pydantic import Field, model_validator

from taktus.ports.worker import ConsumptionDeclaration, CredentialReference
from taktus.shared.v1 import AutonomyLevel, Capability, Consumption, Digest, Value

OPERATION_PATTERN = r"^[a-z][a-z0-9]*(\.[a-z][a-z0-9_-]*){2,}$"
IDEMPOTENCY_KEY_PATTERN = r"^[A-Za-z0-9_.:-]{16,128}$"
CREDENTIAL_NAME_PATTERN = r"^[A-Z][A-Z0-9_]*$"
EVENT_PATTERN = r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$"


class ConnectorError(Exception):
    """The connector did not answer, or answered with something the contract does not allow.
    The message names the connector's endpoint and the fault, never a credential."""


# --- the declaration (§3) ---------------------------------------------------------------------


class Effect(StrEnum):
    """Whether the effect of an operation leaves Taktus. `write` and `delivery` do."""

    READ = "read"
    WRITE = "write"
    DELIVERY = "delivery"


OUTWARD: frozenset[Effect] = frozenset({Effect.WRITE, Effect.DELIVERY})
"""The effects that leave the system: the run records them as `egress.write` and
`egress.delivery` (ADR-0022 §4), and correcting their result afterwards is anchored."""


class Idempotency(StrEnum):
    """How a repeat of an outward operation is recognised (§4 of the contract)."""

    NATIVE = "native"
    MARKED = "marked"
    NONE = "none"


class Operation(Value):
    name: str = Field(pattern=OPERATION_PATTERN)
    capability: Capability
    effect: Effect
    idempotency: Idempotency | None = None
    summary: str = Field(min_length=1)

    @model_validator(mode="after")
    def _outward_declares_idempotency(self) -> Operation:
        if (self.effect is Effect.READ) == (self.idempotency is not None):
            raise ValueError(
                "an operation declares its idempotency exactly when its effect leaves the system"
            )
        if not self.name.startswith(self.capability + "."):
            raise ValueError(f"operation {self.name!r} is not named by its capability")
        return self

    @property
    def outward(self) -> bool:
        return self.effect in OUTWARD

    @property
    def repeatable(self) -> bool:
        """Whether the run may send the same call with the same key again on its own: the
        connector recognises the repeat. `none` is honest and means never."""
        return self.idempotency in (Idempotency.NATIVE, Idempotency.MARKED)


class CredentialNeed(Value):
    name: str = Field(pattern=CREDENTIAL_NAME_PATTERN)
    purpose: Literal["actions", "intake"]


class SignatureScheme(StrEnum):
    """There is no scheme `none`: an intake declaration without a signature is not valid."""

    HMAC_SHA256 = "hmac-sha256"


class IntakeSignature(Value):
    scheme: SignatureScheme


class IntakeDeclaration(Value):
    events: tuple[str, ...] = Field(min_length=1)
    signature: IntakeSignature

    @model_validator(mode="after")
    def _events_are_dotted(self) -> IntakeDeclaration:
        for event in self.events:
            if re.fullmatch(EVENT_PATTERN, event) is None:
                raise ValueError(f"{event!r} is not an event kind")
        return self


class Capabilities(Value):
    """`Capabilities`: what a connector declares about itself, served as one MCP resource."""

    contract: Literal["connector/v1"]
    version: str | None = Field(default=None, min_length=1)
    capabilities: tuple[Capability, ...] = Field(min_length=1)
    operations: tuple[Operation, ...]
    intake: IntakeDeclaration | None = None
    credentials: tuple[CredentialNeed, ...]
    consumption: ConsumptionDeclaration
    permissions: Literal["passthrough"]

    @model_validator(mode="after")
    def _operations_belong_to_declared_capabilities(self) -> Capabilities:
        declared = set(self.capabilities)
        names = [op.name for op in self.operations]
        if len(set(names)) != len(names):
            raise ValueError("an operation is declared twice")
        for op in self.operations:
            if op.capability not in declared:
                raise ValueError(f"operation {op.name!r} belongs to an undeclared capability")
        return self

    def operation(self, name: str) -> Operation | None:
        for op in self.operations:
            if op.name == name:
                return op
        return None


# --- a call (§5, §6) ----------------------------------------------------------------------------


class CallContext(Value):
    """Who acts, for which attempt of which step of which run, and with whose credentials — by
    name. The idempotency key is chosen by the run for one attempt, stable across a resume of
    that attempt after a restart, and never reused."""

    tenant: str = Field(min_length=1)
    identity: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    step_id: str = Field(min_length=1)
    attempt: int = Field(ge=1)
    idempotency_key: str = Field(pattern=IDEMPOTENCY_KEY_PATTERN)
    credentials: tuple[CredentialReference, ...]
    autonomy_level: AutonomyLevel | None = None


def idempotency_key(run_id: str, step_id: str, attempt: int) -> str:
    """The run's key for one attempt of one step: derived, never stored, so that a resumed
    attempt after a restart derives the same one. The prefix names whose key it is where the
    mark ends up in a record outside."""
    return f"taktus:{run_id}:{step_id}:{attempt}"


class Arguments(Value):
    context: CallContext
    # The operation's own input; its shape belongs to the operation.
    input: dict[str, Any]


class Record(Value):
    """One external record an outward call created, updated or delivered."""

    kind: str = Field(pattern=r"^[a-z][a-z0-9_.-]*$")
    id: str = Field(min_length=1)
    url: str | None = Field(default=None, min_length=1)


class EffectReport(Value):
    """What the call did to the outside: the declared effect, and for an outward one whether
    the key was recognised, which records went out and the digest of what was written."""

    kind: Effect
    replayed: bool | None = None
    records: tuple[Record, ...] | None = Field(default=None, min_length=1)
    content_digest: Digest | None = None

    @model_validator(mode="after")
    def _outward_reports_its_records(self) -> EffectReport:
        if self.kind is Effect.READ:
            if (
                self.replayed is not None
                or self.records is not None
                or self.content_digest is not None
            ):
                raise ValueError("a read reports no replay, no records and no digest")
        elif self.replayed is None or self.records is None:
            raise ValueError("an outward effect says whether it was replayed and what went out")
        return self


class Result(Value):
    """The structured content of a successful call."""

    # The operation's own output; its shape belongs to the operation.
    output: dict[str, Any]
    effect: EffectReport
    consumption: Consumption


class Cause(StrEnum):
    UNAUTHENTICATED = "unauthenticated"
    FORBIDDEN = "forbidden"
    NOT_FOUND = "not_found"
    INVALID = "invalid"
    CONFLICT = "conflict"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


class Error(Value):
    """The structured content of a failed call: a failure in the sense of ADR-0021 — the step
    did not complete — with its cause, whether the outward effect happened, and whether the
    same call with the same key may be repeated without a second effect."""

    class_: Literal["failure"] = Field(alias="class")
    cause: Cause
    effect: Literal["none", "unknown"]
    retryable: bool
    detail: str = Field(min_length=1)
    consumption: Consumption | None = None

    @model_validator(mode="after")
    def _the_effect_is_unknown_exactly_when_the_cause_is(self) -> Error:
        if (self.cause is Cause.UNKNOWN) != (self.effect == "unknown"):
            raise ValueError("the effect is unknown exactly when the cause is unknown")
        return self


class CallFailed(Exception):
    """The connector answered the call with a classified error. The error is the connector's
    word on what happened outside; the run decides what follows from it."""

    def __init__(self, operation: str, error: Error) -> None:
        self.operation = operation
        self.error = error
        super().__init__(f"{operation}: {error.cause} — {error.detail}")


# --- intake (§7) ----------------------------------------------------------------------------------


class Delivery(Value):
    """`IntakeArguments`: one event as it arrived, before anything is believed about it."""

    headers: Mapping[str, str]
    body: str
    received_at: datetime


class SenderKind(StrEnum):
    PERSON = "person"
    AUTOMATION = "automation"


class Sender(Value):
    account: str = Field(min_length=1)
    kind: SenderKind


class IntakeIntent(Value):
    raw: str


class IntakeReplyTo(Value):
    channel: Capability
    address: str = Field(min_length=1)
    thread: str | None = None


class Intake(Value):
    """`Intake`: an accepted event, normalised as far as the channel can — the command of the
    shared kernel without identity and org_path, which the identity component adds."""

    event_id: str = Field(min_length=1)
    event: str = Field(pattern=EVENT_PATTERN)
    channel: Capability
    sender: Sender
    intent: IntakeIntent
    context: dict[str, Any]
    reply_to: IntakeReplyTo
    occurred_at: datetime


class RefusalReason(StrEnum):
    UNSIGNED = "unsigned"
    BAD_SIGNATURE = "bad_signature"
    MALFORMED = "malformed"
    UNSUPPORTED_EVENT = "unsupported_event"
    OWN_ACTION = "own_action"


class Refusal(Value):
    reason: RefusalReason
    detail: str = Field(min_length=1)


class IntakeResult(Value):
    """Exactly one of `accepted` and `refused`."""

    accepted: Intake | None = None
    refused: Refusal | None = None

    @model_validator(mode="after")
    def _exactly_one(self) -> IntakeResult:
        if (self.accepted is None) == (self.refused is None):
            raise ValueError("an intake result is exactly one of accepted and refused")
        return self


# --- the port -------------------------------------------------------------------------------------


class IntakeConnector(Protocol):
    async def intake(self, delivery: Delivery) -> IntakeResult:
        """Hand the delivery to the connector's `intake` tool and return what it decided.
        Raises `ConnectorError` when the connector cannot be reached or breaks the contract."""
        ...


class ActionConnector(Protocol):
    async def capabilities(self) -> Capabilities:
        """The declaration, read from the connector. Raises `ConnectorError` when it cannot be
        read or does not validate."""
        ...

    async def call(self, operation: str, context: CallContext, input: Mapping[str, Any]) -> Result:
        """Call one operation. A classified failure is `CallFailed`; a connector that cannot be
        reached, or answers with a shape the contract does not allow, is `ConnectorError`."""
        ...


@dataclass(frozen=True)
class ResolvedConnector:
    """A configured connector, as the run receives it from its pool: the connector, the
    identifier of its adapter configuration — what the ledger and the provenance record carry,
    never a product name — and its declaration, read once."""

    adapter: str
    connector: ActionConnector
    declaration: Capabilities

    @property
    def version(self) -> str | None:
        return self.declaration.version
