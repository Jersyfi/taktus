"""An open model price list becomes one version of the price table (#327, DEC-0190).

The list is the shape LiteLLM publishes: one entry per model, each price in money per token
(`input_cost_per_token`, `output_cost_per_token`, `cache_read_input_token_cost`,
`cache_creation_input_token_cost`). The table prices per `unit_tokens` tokens, so every price is
multiplied up. A kind the list does not give stays absent, which the table reads as unpriced,
never as zero. An entry that cannot be mapped is named with its reason, never dropped silently.
Tiered prices (`*_above_200k_tokens` and the like) are not read: the base price is imported
and the tiers are left out.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from taktus.ports.model import PriceKindName, PriceTable
from taktus.shared.v1 import Value
from taktus.shared.v1.consumption import MODEL_NAME_PATTERN

UNIT_TOKENS = 1_000_000

FIELDS: dict[PriceKindName, str] = {
    "input": "input_cost_per_token",
    "output": "output_cost_per_token",
    "cache_read": "cache_read_input_token_cost",
    "cache_write": "cache_creation_input_token_cost",
}
"""The price kind of the table and the field of the list that holds it."""

_NAME = re.compile(MODEL_NAME_PATTERN)


class Imported(Value):
    table: PriceTable
    unmapped: tuple[str, ...] = ()
    """Every entry of the list that is not in the table, and why."""


def import_prices(
    document: object, *, version: str, valid_from: datetime, currency: str, source: str
) -> Imported:
    """The table the list makes, and what could not be mapped. Raises ValueError where the
    document is no list of models, or none of its entries maps."""
    if not isinstance(document, Mapping):
        raise ValueError("a price list is a JSON object with one entry per model")
    prices: dict[str, dict[PriceKindName, float]] = {}
    unmapped: list[str] = []
    for name, entry in document.items():
        if name == "sample_spec":
            continue
        reason = _map(name, entry, prices)
        if reason is not None:
            unmapped.append(f"{name}: {reason}")
    if not prices:
        raise ValueError("no entry of the list maps to a price")
    table = PriceTable(
        version=version,
        valid_from=valid_from,
        currency=currency,
        unit_tokens=UNIT_TOKENS,
        source=source,
        prices=prices,
    )
    return Imported(table=table, unmapped=tuple(unmapped))


def _map(name: str, entry: Any, prices: dict[str, dict[PriceKindName, float]]) -> str | None:
    if not _NAME.match(name):
        return "not a model name the ledger can record"
    if not isinstance(entry, Mapping):
        return "not an object"
    found: dict[PriceKindName, float] = {}
    for kind, field in FIELDS.items():
        value = entry.get(field)
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, int | float) or value < 0:
            return f"{field} is not a price"
        found[kind] = round(value * UNIT_TOKENS, 9)
    if not found:
        return "no price per token"
    prices[name] = found
    return None
