"""The egress container publishes the unit's port on a host port the engine chooses. The engine
chooses from its own record, which does not see a port another program holds, and then fails
the start with `address already in use`. Without an engine: the start is repeated on exactly
that answer, and on no other."""

from __future__ import annotations

import pytest

from taktus.adapters.driven.execution.container.adapter import (
    PUBLISH_ATTEMPTS,
    start_publishing,
)
from taktus.adapters.driven.execution.container.engine import EngineError

# The engine's answer on a CI runner on 2026-10-16, with the ids shortened.
TAKEN = (
    "POST /containers/954b/start answered 500: failed to set up container networking: driver "
    "failed programming external connectivity on endpoint taktus-egress-asg-wall-d320ba "
    "(0adc): failed to listen on TCP socket: address already in use"
)


class _Engine:
    """An engine that refuses the first starts with the given answers, then starts."""

    def __init__(self, *refusals: str) -> None:
        self.refusals = list(refusals)
        self.starts = 0

    async def start(self, container: str) -> None:
        self.starts += 1
        if self.refusals:
            raise EngineError(self.refusals.pop(0))


async def test_a_taken_host_port_makes_the_engine_choose_again() -> None:
    engine = _Engine(TAKEN, TAKEN)
    await start_publishing(engine, "egress")  # type: ignore[arg-type]
    assert engine.starts == 3


async def test_any_other_refusal_is_raised_at_once() -> None:
    engine = _Engine("POST /containers/954b/start answered 500: no such image")
    with pytest.raises(EngineError, match="no such image"):
        await start_publishing(engine, "egress")  # type: ignore[arg-type]
    assert engine.starts == 1


async def test_a_port_taken_every_time_is_raised_after_the_last_attempt() -> None:
    engine = _Engine(*[TAKEN] * PUBLISH_ATTEMPTS)
    with pytest.raises(EngineError, match="address already in use"):
        await start_publishing(engine, "egress")  # type: ignore[arg-type]
    assert engine.starts == PUBLISH_ATTEMPTS
