"""A fake of the run's maturity port: every adapter verified, except the ones it is told."""

from __future__ import annotations

from collections.abc import Mapping

from taktus.components.run.ports import Standing


class FakeMaturities:
    """Answers *verified* for every adapter but those in `below`, which it answers
    *experimental* with what they lack. Records what it was asked."""

    def __init__(self, below: Mapping[str, tuple[str, ...]] | None = None) -> None:
        self.below = dict(below or {})
        self.asked: list[str] = []

    async def standing(self, tenant: str, adapter: str) -> Standing:
        self.asked.append(adapter)
        if adapter in self.below:
            return Standing(adapter=adapter, maturity="experimental", missing=self.below[adapter])
        return Standing(adapter=adapter, maturity="verified")


VERIFIED = FakeMaturities()
"""For tests of the engine's mechanics at level 3: no adapter is held back by its maturity."""
