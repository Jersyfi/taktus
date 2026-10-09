"""A block: a stretch of time in which a step of a run could not go on, and why (ADR-0015).

Every block is booked to one of seven *accounts*, the causes ADR-0015 names. A block also has a
*cause token*: the engine's own word for what held the step, such as `at_capacity` or
`rejected_by_admission`. The account says which limit or which wait the time belongs to; the
token says how the engine met it. Several tokens book to one account.

A block is *open* while the step waits. The step run carries it (`StepRun.block`), so that a
wait survives a restart and its start is never lost. When the wait ends, the engine writes the
block's record and clears it (ADR-0043).

A block for want of an adapter — no configured worker offers what the step requires, no
configured connector serves its capability, or the connector does not offer its operation — is
a *lack*: the step failed for it and waits, until the configuration or the product changes, for
the step to start again (ADR-0046). It carries what was lacking, an identifier only.

A block on a person names no person. Who answered is the audit's, in the ledger entry of the
answer; the block holds the time only (ADR-0015, protective rule).
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Literal

from pydantic import Field

from taktus.shared.v1 import StepId, Value

type Account = Literal[
    "limit.provider",
    "limit.quota",
    "limit.budget",
    "limit.compute",
    "wait.human",
    "wait.external",
    "wait.dependency",
]

ACCOUNTS: tuple[Account, ...] = (
    "limit.provider",
    "limit.quota",
    "limit.budget",
    "limit.compute",
    "wait.human",
    "wait.external",
    "wait.dependency",
)
"""The seven accounts of ADR-0015 §1, in its order. There is no eighth: a cause the engine
meets later books to one of these."""

CAUSE_PATTERN = r"^[a-z][a-z0-9_]*$"
"""A cause token is a ledger outcome token: the record's entry carries it."""

# The cause tokens the engine knows, each with the account it books to. A new kind of wait —
# an anchor's halt, for one — adds its token here and books to an existing account.
AT_CAPACITY = "at_capacity"
"""The step's worker holds as many assignments as it declares (ADR-0037)."""
REJECTED_BY_CAPACITY = "rejected_by_capacity"
"""The platform the instance runs on cannot hold the job (docs/architecture/platform.md)."""
REJECTED_BY_ADMISSION = "rejected_by_admission"
"""The step's reservation does not fit what is left of the run's budget (ADR-0005)."""
HALTED_AT_LIMIT = "halted_at_limit"
"""The worker halted at its boundary before crossing its ceiling (W-14)."""
AT_PROVIDER_LIMIT = "at_provider_limit"
"""The model's provider answered at its rate limit."""
AWAITING_CONFIRMATION = "awaiting_confirmation"
"""The step waits for a person to confirm it (level 2, ADR-0039)."""
AWAITING_PERFORMANCE = "awaiting_performance"
"""The step waits for a person to perform its act (level 1, ADR-0039)."""
AWAITING_DECISION = "awaiting_decision"
"""The step's act is anchored, and waits for its decision requests to be decided (ADR-0042)."""
WAITING_ON_STATE = "waiting_on_state"
"""A `wait` step waits for an external state: a pipeline, a partner system."""
WAITING_ON_CLOCK = "waiting_on_clock"
"""A `wait` step waits for a time to pass."""
HELD_BACK = "held_back"
"""The step depends on a step that waits, and cannot start before it ends."""
NO_WORKER = "no_worker"
"""No configured worker offers the capabilities the step requires (NTC-0002, ADR-0046)."""
NO_CONNECTOR = "no_connector"
"""No configured connector serves the capability the step calls (NTC-0002, ADR-0046)."""
OPERATION_UNSUPPORTED = "operation_unsupported"
"""The connector that serves the capability does not offer the operation (NTC-0002,
ADR-0046)."""

LACKS: frozenset[str] = frozenset({NO_WORKER, NO_CONNECTOR, OPERATION_UNSUPPORTED})
"""The causes that are a lack of an adapter. Each books to `wait.dependency`: the step depends
on an adapter the instance does not have (ADR-0046)."""
LACK_ACCOUNT: Account = "wait.dependency"

CLOSED_BY_ADMISSION: frozenset[str] = frozenset(
    {REJECTED_BY_CAPACITY, REJECTED_BY_ADMISSION, HALTED_AT_LIMIT}
)
"""The causes a block ends with once the step is admitted again: what refused it was a limit
that admission checks."""


def limit_account(kinds: Iterable[str]) -> Account:
    """The account of a refusal or a halt at the run's own limits, from the consumption kinds
    that did not fit: `limit.quota` when quota alone did not fit, `limit.budget` otherwise.
    Quota is counted against a provider's window or a subscription; currency, tokens and
    compute seconds are the budget a person configured for the run."""
    named = set(kinds)
    return "limit.quota" if named == {"quota"} else "limit.budget"


class OpenBlock(Value):
    """A block that has not ended: what the step run carries while it waits."""

    account: Account
    cause: str = Field(pattern=CAUSE_PATTERN)
    since: datetime
    on: StepId | None = None
    """For a step held back: the step it depends on that waited when the block began."""
    role: str | None = Field(default=None, min_length=1)
    """For a wait on a person addressed to a role — an anchor's decision request — the role.
    Never a person."""
    lacking: str | None = Field(default=None, min_length=1)
    """For a lack: what no configured adapter offers — the capabilities, comma-separated, or
    the operation. An identifier, never a text."""
