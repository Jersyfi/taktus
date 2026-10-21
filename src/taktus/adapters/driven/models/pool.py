"""A fixed set of configured models, resolved by purpose.

Configuration maps a purpose to a model; the ledger records the configuration's identifier and
never a product. The simplest such configuration: a list of (identifier, purposes, model,
version), in order, each with where it processes and the exactness classes it may produce for.
The *chain* of a purpose is every member that serves it — or every purpose, `*` — in that order;
`resolve` is its first member (ADR-0116).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from taktus.ports.model import MODEL_CLASSES, Location, Model, ResolvedModel

EVERY_PURPOSE = "*"


@dataclass(frozen=True)
class Declared:
    """What a member's operator declares beyond its model: where it processes and the
    exactness classes it may produce a result for."""

    location: Location = "elsewhere"
    classes: tuple[str, ...] = MODEL_CLASSES


class StaticModelPool:
    def __init__(
        self,
        models: Sequence[tuple[str, Sequence[str], Model, str | None]] = (),
        declared: Mapping[str, Declared] | None = None,
    ) -> None:
        self._models = [(a, tuple(p), m, v) for a, p, m, v in models]
        self._declared = dict(declared or {})

    def _resolved(self, adapter: str, model: Model, version: str | None) -> ResolvedModel:
        declared = self._declared.get(adapter, Declared())
        return ResolvedModel(
            adapter=adapter,
            model=model,
            version=version,
            location=declared.location,
            classes=declared.classes,
        )

    async def resolve(self, purpose: str) -> ResolvedModel | None:
        chain = await self.chain(purpose)
        return chain[0] if chain else None

    async def chain(self, purpose: str) -> list[ResolvedModel]:
        """Every member that serves the purpose, in the order they are configured."""
        return [
            self._resolved(adapter, model, version)
            for adapter, purposes, model, version in self._models
            if purpose in purposes or EVERY_PURPOSE in purposes
        ]

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
        return StaticModelPool([m for m in self._models if m[0] != adapter], self._declared)

    def first(self, adapter: str) -> StaticModelPool:
        """The same configuration with one model moved to the front, for the removal test's
        baseline (ADR-0078); the original is untouched."""
        return StaticModelPool(
            sorted(self._models, key=lambda entry: entry[0] != adapter), self._declared
        )
