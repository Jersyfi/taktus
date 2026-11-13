"""A failure's escalation, as the governance component reads it (UC-4.5, ADR-0252).

A run that escalated stopped at the boundary of a step that failed. **`Escalated`** is what the
composition root reads of it from the run, its process version and the ledger: the step that
failed with its cause, what was tried before the run stopped, what the run reached outside, and
the maintained instructions for doing the failed step by hand. Every field is the record's own;
nothing is guessed. It names no person (principle 14): the actor of a reaction is the ledger's.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from pydantic import Field

from taktus.shared.v1 import Value


class ByHand(Value):
    """How a person does the failed step without Taktus: its maintained instructions (ADR-0180)."""

    system: str = Field(min_length=1)
    do: str = Field(min_length=1)
    expertise: str = Field(min_length=1)
    credentials: tuple[str, ...] = ()
    """Each credential by its parameter, never a value."""
    done: str = Field(min_length=1)


class Escalated(Value):
    run_id: str = Field(min_length=1)
    process_version: str = Field(min_length=1)
    escalated_at: datetime
    step_id: str | None = None
    """The step that failed; None where the record names none."""
    cause: str | None = None
    """The token the ledger names the failure by."""
    reason: str | None = None
    attempts: int = Field(default=1, ge=0)
    """How often the failed step was started."""
    healed: tuple[str, ...] = ()
    """The failures a heal answered before the run stopped (ADR-0160), by their tokens."""
    finished: tuple[str, ...] = ()
    """The steps that completed before the failure; a resume repeats none of them."""
    reached: tuple[str, ...] = ()
    """The adapters the run's steps called."""
    left: int = Field(default=0, ge=0)
    """How many outward effects the run recorded as having left the system (ADR-0022)."""
    by_hand: ByHand | None = None
    instructions: str | None = None
    """The process version's sequence by hand, from its takeover instructions."""
    breaks: str | None = None
    """The clause of a data contract with a partner that the failed step broke, in words:
    the fields the message lacks and who answers for the contract (UC-15.3, ADR-0303). None
    where the step exchanges under no contract."""


class Target(Value):
    """The process's time to react, and the role and path its escalations take (ADR-0252 §2)."""

    role: str = Field(min_length=1)
    react_within: timedelta | None = None
    path: str = "channel"


class Lacking(Value):
    """One item a handover between two links of a chain lacked: the input it fills, the step of
    the sending process it comes from, and the clause of the chain that requires it."""

    input: str = Field(min_length=1)
    step: str = Field(min_length=1)
    clause: str = Field(min_length=1)


class HandoverHalted(Value):
    """A chain that halted at a boundary because the handover lacked a declared item (UC-15.4,
    ADR-0302), as the governance component reads it. Every field is the record's own."""

    chain: str = Field(min_length=1)
    chain_run: str = Field(min_length=1)
    sending: str = Field(min_length=1)
    """The process version of the link before the boundary."""
    sending_run: str = Field(min_length=1)
    receiving: str = Field(min_length=1)
    """The process version of the link after the boundary, which did not start."""
    lacking: tuple[Lacking, ...] = Field(min_length=1)
    handed: tuple[str, ...] = ()
    """The inputs the sending run did hold."""
    finished: tuple[str, ...] = ()
    """The process versions of the links that finished before the boundary, in order."""
    left: int = Field(default=0, ge=0)
    """How many outward effects the chain's runs recorded as having left the system."""
    after: tuple[str, ...] = ()
    """The process versions of the links after the boundary, which did not start."""
