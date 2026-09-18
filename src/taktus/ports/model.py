"""CONTRACT 3, the client side: how the core asks a model for a completion.

The smallest shape an `llm` step needs: a prompt in, a completion out, with what it used. The
contract itself (`contracts/model/v1`, the chat-completions dialect) is not yet written as a
schema; this port is the core's side of it and will be held to the schema when it exists, the
way the worker and connector ports are held to theirs.

A model is reached by *purpose* — `reasoning`, `triage` — never by product: a process names the
purpose, configuration maps it to an endpoint and a model name (ADR-0003). Which model
answered is recorded in the provenance of every result (`Completion.model`), because a step
that is `sourced` or `tolerant` is only reproducible at a pinned version.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from pydantic import Field

from taktus.shared.v1 import Value


class Prompt(Value):
    system: str | None = None
    user: str = Field(min_length=1)
    max_output_tokens: int = Field(default=2048, ge=1)


class Completion(Value):
    text: str
    model: str = Field(min_length=1)
    """The model that answered, as the endpoint names it — a version, where the endpoint
    gives one."""
    tokens_in: int = Field(ge=0)
    tokens_out: int = Field(ge=0)
    finish: Literal["stop", "length", "other"]
    """Why the model stopped: the end of its answer, the output limit, something else."""


class ModelError(Exception):
    """The model could not be used: unreachable, refused, an answer outside the contract. The
    message names the endpoint and the fault, never a credential."""


class Model(Protocol):
    async def complete(self, prompt: Prompt) -> Completion: ...


@dataclass(frozen=True)
class ResolvedModel:
    """A configured model, as the run receives it from its pool: the model, the identifier of
    its adapter configuration — what the ledger carries, never a product name — and the
    version it is configured as."""

    adapter: str
    model: Model
    version: str | None = None
