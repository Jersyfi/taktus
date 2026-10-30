"""The relay of the worker contract's outbound binding, as every instance shares it (ADR-0156).

A worker that connects outbound fetches the contract's requests from a *host* and posts its
answers back (contracts/worker/v1 §8). The runner that makes a request and the host the worker
is connected to are, in general, on different instances, and either may restart. So a request
in flight lives here, not in a process: the runner *puts* it, a host *takes* it for the worker
that polls, the worker's answer is *begun* with its status, its body *appended* chunk by chunk
and *ended*, and the runner reads the answer and its chunks as they arrive. A request a runner
stopped reading is *done*: what is left of it is removed, and a host still appending learns so
and stops.

The relay belongs to the instance, not to a tenant: a worker serves every tenant of its
instance, and the worker port carries no tenant. Each call is a transaction of its own.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Literal, Protocol

from pydantic import Field

from taktus.ports.worker import RelayRequest
from taktus.shared.v1 import Value

type Begun = Literal["begun", "unknown", "answered"]
"""What became of an answer begun: taken, for a request of no such worker or none (`404`), or
for one answered already (`409`)."""


class RelayAnswer(Value):
    """The head of an answer: its status and type."""

    status: int = Field(ge=100, le=599)
    content_type: str | None = None


class RelayChunks(Value):
    """The chunks of an answer's body after a sequence number, and whether the body ended."""

    chunks: tuple[tuple[int, bytes], ...] = ()
    ended: bool = False
    gone: bool = False
    """The request is no longer in the relay: done, or purged."""


class RelayCount(Value):
    """What a request received, for the conformance suite's W-21: how many answers were posted
    for it, and the status of the first."""

    request_id: str
    answers: int = Field(ge=0)
    status: int | None = None


class Relay(Protocol):
    async def put(self, worker: str, request: RelayRequest) -> None:
        """A request for `worker`, the adapter identifier of a connected worker."""
        ...

    async def take(self, worker: str) -> RelayRequest | None:
        """The oldest request for `worker` no host has taken yet, now taken; two takes never
        receive the same one. None when there is none."""
        ...

    async def begin(
        self, worker: str, request_id: str, status: int, content_type: str | None
    ) -> Begun:
        """The head of the answer to a request `worker` took. Every call counts as an answer
        posted, whatever it returns."""
        ...

    async def append(self, request_id: str, seq: int, chunk: bytes) -> bool:
        """One chunk of the answer's body, in order. False when the request is gone: nobody
        reads the answer any more, and the rest of the body is not wanted."""
        ...

    async def end(self, request_id: str) -> None:
        """The answer's body is complete."""
        ...

    async def answer(self, request_id: str) -> RelayAnswer | None:
        """The head of the answer, once it was begun."""
        ...

    async def chunks(self, request_id: str, after: int) -> RelayChunks:
        """The chunks whose sequence number is above `after`."""
        ...

    async def done(self, request_id: str) -> None:
        """The runner read what it wanted of the answer: the request and its chunks are
        removed."""
        ...

    async def counts(self, request_ids: Sequence[str]) -> Sequence[RelayCount]:
        """What each request received, for those still in the relay."""
        ...

    async def purge(self, before: datetime) -> int:
        """Remove every request written before `before`; how many."""
        ...
