"""Money in one currency counted against a budget in another (ADR-0335). A pure rule, no I/O.

A budget names amounts by currency. A worker, a provider or a price table may report money in
another: a coding agent reports US dollars, a tenant budgets in euros. Without a conversion that
money counts against nothing.

An **exchange-rate table** is a configured, dated document: its version, the moment it is valid
from, its source, and for each currency the rate into each other currency. It is never a model's
number. `converted` adds to a quantity the money of every currency the budget does not limit,
converted at the table into the first currency the budget limits that the table has a rate for.
The money in its own currency stays where it was, so the record is unchanged and the conversion
is recomputable from it and the table's version. The same inputs give the same amounts.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import datetime

from pydantic import Field, model_validator

from taktus.shared.v1 import ConsumptionQuantities, Value

CODE = re.compile(r"[a-z]{3}")


class ExchangeRates(Value):
    """One version of the rates money is converted at. `rates[from][into]` is how many units of
    `into` one unit of `from` is worth."""

    version: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
    valid_from: datetime
    source: str = Field(min_length=1)
    """Where the rates were taken from: a central bank's reference rates of a day, a contract."""
    rates: dict[str, dict[str, float]] = Field(min_length=1)

    @model_validator(mode="after")
    def _sound(self) -> ExchangeRates:

        for source, into in self.rates.items():
            if CODE.fullmatch(source) is None:
                raise ValueError(f"{source!r} is not a currency code in lowercase")
            for target, rate in into.items():
                if CODE.fullmatch(target) is None:
                    raise ValueError(f"{target!r} is not a currency code in lowercase")
                if target == source:
                    raise ValueError(f"{source} is converted into itself")
                if not rate > 0:
                    raise ValueError(f"{source} into {target} is not a positive rate")
        return self

    def rate(self, source: str, target: str) -> float | None:
        return self.rates.get(source, {}).get(target)


def converted(
    quantities: ConsumptionQuantities, limited: Sequence[str], table: ExchangeRates | None
) -> ConsumptionQuantities:
    """`quantities` with the money of each currency `limited` does not name added, at the
    table, to the first currency of `limited` the table converts it into. Money no rate
    reaches is left as it was, and so counts against nothing, as without a table."""
    money = quantities.currency
    if table is None or not money or not limited:
        return quantities
    total = dict(money)
    for source, amount in money.items():
        if source in limited or amount == 0:
            continue
        for target in limited:
            rate = table.rate(source, target)
            if rate is not None:
                total[target] = total.get(target, 0.0) + amount * rate
                break
    if total == money:
        return quantities
    return quantities.model_copy(update={"currency": total})


def ceiling_in(
    currency: Mapping[str, float] | None, table: ExchangeRates | None
) -> dict[str, float] | None:
    """A ceiling in the budget's currencies, also stated in every currency the table converts
    into one of them (ADR-0335 §3): a worker that measures its money in that currency halts at
    the same line during the step. The first of the budget's currencies the table reaches
    gives the amount, as in `converted`."""
    if currency is None or table is None:
        return None if currency is None else dict(currency)
    stated = dict(currency)
    limited = sorted(currency)
    for source in sorted(table.rates):
        if source in stated:
            continue
        for target in limited:
            rate = table.rate(source, target)
            if rate is not None:
                stated[source] = currency[target] / rate
                break
    return stated
