"""A chain of processes across domains, and what passes at each of its boundaries (UC-15.4,
ADR-0274).

A chain links process versions in order. At every boundary between two links it declares the
handover: each item the receiving process is given, as one of its inputs, the step of the
sending process whose result it is, the part of that result, and the clause of the chain that
requires it. Each link stays a process with its own version, owner and autonomy level.
"""

from __future__ import annotations

from pydantic import Field, model_validator

from taktus.shared.v1 import StepId, Value


class Item(Value):
    """One thing handed over at a boundary."""

    input: str = Field(min_length=1)
    """The input of the receiving process it fills."""
    step: StepId
    """The step of the sending process whose result it is."""
    select: str | None = Field(default=None, min_length=1)
    """The dotted path to the part of the result; None hands over the whole result."""
    clause: str = Field(min_length=1)
    """Why the chain requires it, in words: what the record of the handover names."""


class Link(Value):
    process_version: str = Field(pattern=r"^[a-z][a-z0-9-]*@[A-Za-z0-9][A-Za-z0-9._-]*$")
    handover: tuple[Item, ...] = ()
    """What passes from the link before to this one; empty for the first link."""


class Chain(Value):
    id: str = Field(pattern=r"^[a-z][a-z0-9-]*$")
    name: str = Field(min_length=1)
    links: tuple[Link, ...] = Field(min_length=2)

    @model_validator(mode="after")
    def _linked_once(self) -> Chain:
        refs = [link.process_version for link in self.links]
        if len(set(refs)) != len(refs):
            raise ValueError("a chain links each process version once")
        if self.links[0].handover:
            raise ValueError("the first link of a chain is handed nothing")
        if any(not link.handover for link in self.links[1:]):
            raise ValueError("every link after the first declares what is handed over to it")
        return self
