"""CONTRACT 3, the client side: how the core asks a model for a completion.

The smallest shape an `llm` step needs: a prompt in, a completion out, with what it used — and,
before the call, what the adapter can say about it. `contracts/model/v1/Model.json` is the
schema; `tests/contract` holds the shapes here to it.

**Before the call.** Every adapter declares its `Calculability`: whether it can count a
prompt's input tokens exactly, as an upper bound, only as an estimate, or not at all; whether
the output limit a call sets is hard; which price kinds the provider reports; and how the
provider bills. `count` is the count itself. The run takes the step's estimate from it — input
counted, output bounded by the limit the step sets — and a step whose model cannot count is
refused, not admitted (ADR-0005). What budget a declaration permits is derived from it and
said when the budget is set, never discovered afterwards (principle 8).

**After the call.** A completion reports its tokens in total and, where the provider says so,
by price kind — uncached input, input read from a cache, input written to one, output — so
that money follows from a price table and the record (ADR-0010).

A model is reached by *purpose* — `reasoning`, `triage` — never by product: a process names the
purpose, configuration maps it to an endpoint and a model name (ADR-0003). Which model
answered is recorded in the provenance of every result (`Completion.model`), because a step
that is `sourced` or `tolerant` is only reproducible at a pinned version.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

from pydantic import Field, model_validator

from taktus.shared.v1 import ModelName, PriceKinds, Value

type InputCount = Literal["exact", "upper_bound", "estimate", "none"]
type OutputCap = Literal["hard", "soft", "none"]
type Billing = Literal["per_token", "per_window", "per_hardware_time"]
type ProviderLimit = Literal["hard", "alert", "none", "unknown"]
type PriceKindName = Literal["input", "output", "cache_read", "cache_write"]


class Calculability(Value):
    """Model.json#/$defs/Calculability: what an adapter can say before a call, and how its
    provider bills. An adapter declares no more than its provider permits."""

    contract: Literal["model/v1"] = "model/v1"
    input_count: InputCount
    output_cap: OutputCap
    usage_kinds: tuple[PriceKindName, ...] = Field(min_length=1)
    billing: Billing
    provider_limit: ProviderLimit | None = None
    evidence: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _kinds_are_unique(self) -> Calculability:
        if len(set(self.usage_kinds)) != len(self.usage_kinds):
            raise ValueError("usage_kinds names a kind twice")
        return self


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
    """Every input token, of any price kind."""
    tokens_out: int = Field(ge=0)
    by_kind: PriceKinds | None = None
    """The same tokens split by price kind, as far as the provider reports them; None when it
    reports totals only."""
    finish: Literal["stop", "length", "other"]
    """Why the model stopped: the end of its answer, the output limit, something else."""


class ModelError(Exception):
    """The model could not be used: unreachable, refused, an answer outside the contract. The
    message names the endpoint and the fault, never a credential."""


class Model(Protocol):
    def calculability(self) -> Calculability:
        """What this adapter can say before a call; constant for its configuration."""
        ...

    async def count(self, prompt: Prompt) -> int | None:
        """The prompt's input tokens as the declaration says it counts them — exactly, as an
        upper bound or as an estimate — or None when it declares `none`. An adapter whose
        provider counts for it asks here; one that bounds the count computes it."""
        ...

    async def complete(self, prompt: Prompt) -> Completion: ...


@dataclass(frozen=True)
class ResolvedModel:
    """A configured model, as the run receives it from its pool: the model, the identifier of
    its adapter configuration — what the ledger carries, never a product name — and the
    version it is configured as."""

    adapter: str
    model: Model
    version: str | None = None


# --- the price table (Model.json#/$defs/PriceTable) ----------------------------------------------


class PriceTable(Value):
    """One version of the prices money is computed with. A version never changes once used;
    the run's budget statement names it by the digest of its document, so that money stays
    recomputable from the ledger (ADR-0010). A price is per `unit_tokens` tokens of one kind of
    one model; a kind without a price is unpriced, never zero."""

    version: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
    valid_from: datetime
    currency: str = Field(pattern=r"^[a-z]{3}$")
    unit_tokens: int = Field(ge=1)
    source: str = Field(min_length=1)
    prices: dict[ModelName, dict[PriceKindName, float]] = Field(min_length=1)

    @model_validator(mode="after")
    def _prices_are_not_negative(self) -> PriceTable:
        for model, kinds in self.prices.items():
            if not kinds:
                raise ValueError(f"{model!r} names no price")
            for kind, price in kinds.items():
                if price < 0:
                    raise ValueError(f"{model!r} {kind} is priced below zero")
        return self


class Priced(Value):
    """Money for some tokens at one price table: the amount in the table's currency, and every
    (model, kind) that had tokens and no price — which the amount then leaves out and says so."""

    amount: float = Field(ge=0)
    currency: str
    table: str
    unpriced: tuple[str, ...] = ()

    @property
    def complete(self) -> bool:
        return not self.unpriced


def price(tokens: Mapping[str, PriceKinds], table: PriceTable) -> Priced:
    """The money these tokens cost at the table: every kind of every model at its price. A
    model or a kind the table does not price is named in `unpriced`, never counted as free."""
    amount = 0.0
    unpriced: list[str] = []
    for model, kinds in sorted(tokens.items()):
        prices = table.prices.get(model)
        for kind in ("input", "output", "cache_read", "cache_write"):
            count = getattr(kinds, kind)
            if not count:
                continue
            per_unit = None if prices is None else prices.get(kind)
            if per_unit is None:
                unpriced.append(f"{model} {kind}")
                continue
            amount += count * per_unit / table.unit_tokens
    return Priced(
        amount=round(amount, 9),
        currency=table.currency,
        table=table.version,
        unpriced=tuple(unpriced),
    )
