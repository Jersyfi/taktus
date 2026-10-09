"""Filing an answer to a decision request where it belongs: in the decision component, which
reads it by its own rule, waits for the reading to be confirmed and writes the register
(ADR-0042). The composition root answers this port from that component, because components
never import each other.
"""

from __future__ import annotations

from typing import Protocol

from pydantic import Field

from taktus.ports.persistence import Tenant
from taktus.shared.v1 import Value


class DecisionRead(Value):
    """How the decision component read an answer: one option, or none."""

    option: str | None = Field(default=None, pattern=r"^[A-Z]$")
    """None: no single option could be read, and nothing changed."""
    kept: bool = False
    """The answer said more than the option; the rest is kept and not acted on."""


class DecisionRefused(Exception):
    """The decision component refused the act, and nothing changed. `closed`: the request is
    past taking it — its answer took effect. Otherwise the person may not act on it."""

    def __init__(self, detail: str, *, closed: bool = False) -> None:
        super().__init__(detail)
        self.closed = closed


class DecisionAnswers(Protocol):
    async def answer(
        self, tenant: Tenant, request_id: str, identity: str, text: str
    ) -> DecisionRead: ...

    async def confirm(
        self, tenant: Tenant, request_id: str, identity: str, confirmed: bool
    ) -> str | None:
        """The register entry when the reading was confirmed; None when it was rejected."""
        ...
