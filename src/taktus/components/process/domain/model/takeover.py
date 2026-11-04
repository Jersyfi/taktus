"""A process version's takeover instructions and the trials of them (UC-6.3, ADR-0180).

The instructions say how a person runs the process without Taktus: the sequence as a whole, and
for every step the system to act in, what to do there, the expertise it needs, each credential
by its parameter and where an authorised person finds it, and how to tell that the step is
done. The skills a step uses are not written here: they are derived from the step's
`work.skills` when the instructions are read (ADR-0180 §1).

A **trial** is the record that a person ran the process by hand from the instructions alone:
the role that ran it, when, whether they could, and what was missing. It names the version that
was active, and a role, never a person (principle 14).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from pydantic import Field

from taktus.shared.v1 import StepId, Value

PARAMETER = r"^[A-Z][A-Z0-9_]*$"
"""A credential's parameter, as the credential register names it: `REPOSITORY_TOKEN`."""
ROLE = r"^[a-z][a-z0-9-]*$"
"""A role of the tenant's structure, the shape a step's role has."""


class CredentialPointer(Value):
    """A credential by its parameter and where an authorised person finds it; never its value."""

    parameter: str = Field(pattern=PARAMETER)
    where: str = Field(min_length=1)


class StepInstructions(Value):
    """How a person does one step by hand."""

    system: str = Field(min_length=1)
    """The system to act in."""
    do: str = Field(min_length=1)
    """What to do there."""
    expertise: str = Field(min_length=1)
    """What the person needs to know; the instructions assume it and do not teach it."""
    credentials: tuple[CredentialPointer, ...]
    """Each credential the step needs, by parameter; none is an empty list, never left out."""
    done: str = Field(min_length=1)
    """How to tell that the step is done."""


class TakeoverInstructions(Value):
    """The instructions of one version: the whole, and every step by its identifier."""

    sequence: str = Field(min_length=1)
    """When the process runs, in what order, and who starts it, in a person's words."""
    steps: Mapping[StepId, StepInstructions]


class TakeoverTrial(Value):
    """A person ran the process by hand from the instructions of `process_version`."""

    id: str = Field(min_length=1)
    process_id: str = Field(pattern=r"^[a-z][a-z0-9-]*$")
    process_version: str = Field(min_length=1)
    """The version that was active, as the ledger names it: `<process>@<version>`."""
    role: str = Field(pattern=ROLE)
    """The role that ran it, never a person."""
    passed: bool
    """Whether the person could run the process from the instructions alone."""
    missing: tuple[str, ...] = ()
    """What the instructions lacked, in the person's words."""
    at: datetime
