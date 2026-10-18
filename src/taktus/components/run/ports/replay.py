"""A replay of a recorded run, seen from the run (ADR-0108).

A replay answers every step of a rehearsal that would leave the engine — a connector call of
any effect, a wait on a connector, a model call, a worker step — from the recorded result of the
same step in a real run of the same process. It offers that as the three pools the engine
resolves from in any run, so that the engine's own handling of a step runs unchanged between the
step and the recorded answer: estimate, admission, the hand-over, the stream, the artifacts.

An engine given a replay resolves every rehearsal it executes from the replay, never from its
configured pools: an outward operation in such a run is sent to the replay, which acts on
nothing. The composition root builds the replay from a recording; the run never sees how a
recording is kept.
"""

from __future__ import annotations

from typing import Protocol

from taktus.components.run.ports.connectors import ConnectorPool
from taktus.components.run.ports.models import ModelPool
from taktus.components.run.ports.workers import WorkerPool


class Replay(Protocol):
    @property
    def workers(self) -> WorkerPool:
        """Workers that answer each worker step with its recorded estimate, events and
        artifacts."""
        ...

    @property
    def connectors(self) -> ConnectorPool:
        """Connectors that answer each connector call and each wait with the recorded result
        of the step that makes it."""
        ...

    @property
    def models(self) -> ModelPool:
        """Models that answer each model call with the recorded completion of its step."""
        ...
