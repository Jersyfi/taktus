"""A fixed set of configured models, resolved by purpose.

Configuration maps a purpose to a model; the ledger records the configuration's identifier and
never a product. The simplest such configuration: a list of (identifier, purposes, model,
version); the first that serves the purpose — or every purpose, `*` — wins.
"""

from __future__ import annotations

from collections.abc import Sequence

from taktus.ports.model import Model, ResolvedModel

EVERY_PURPOSE = "*"


class StaticModelPool:
    def __init__(self, models: Sequence[tuple[str, Sequence[str], Model, str | None]] = ()) -> None:
        self._models = [(a, tuple(p), m, v) for a, p, m, v in models]

    async def resolve(self, purpose: str) -> ResolvedModel | None:
        for adapter, purposes, model, version in self._models:
            if purpose in purposes or EVERY_PURPOSE in purposes:
                return ResolvedModel(adapter=adapter, model=model, version=version)
        return None

    def members(self) -> list[tuple[str, tuple[str, ...], str | None]]:
        """Every configured model with the purposes it serves and its pinned version — what
        the removal test reads to know what is configured, and records its verdict under."""
        return [(adapter, purposes, version) for adapter, purposes, _, version in self._models]

    def member(self, adapter: str) -> tuple[tuple[str, ...], Model, str | None] | None:
        """The purposes, the model and its pinned version under one identifier; None when no
        model has it."""
        for configured, purposes, model, version in self._models:
            if configured == adapter:
                return purposes, model, version
        return None

    def without(self, adapter: str) -> StaticModelPool:
        """The same configuration with one model withheld; the original is untouched."""
        return StaticModelPool([m for m in self._models if m[0] != adapter])
