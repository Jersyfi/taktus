from __future__ import annotations

from taktus.ports.platform import PlatformObservation


class FakePlatform:
    """The platform port answering what the test says, one observation after another; the
    last one repeats."""

    adapter = "platform.fake"

    def __init__(self, *observations: PlatformObservation) -> None:
        self.observations = list(observations)
        self.observed = 0

    async def observe(self) -> PlatformObservation:
        index = min(self.observed, len(self.observations) - 1)
        self.observed += 1
        return self.observations[index]


class FakeStateSize:
    """The persistence port's `StateSize`, answering a set figure."""

    def __init__(self, size: int | None) -> None:
        self.size = size

    async def state_bytes(self) -> int | None:
        return self.size
