"""What may leave an instance for the product (ADR-0112 §4): the one rule a finding and a report
by hand are both checked by.

A text that leaves for the product has two kinds of part. Some parts are the product's own:
its fixed sentences. The others came from the instance: what was lacking, the operator's form,
or everything a person wrote by hand. The rule checks every part that came from the instance.
A part fails when it carries either of two things.

- **A value of the tenant.** The composition root reads the tenant's values: what its runs were
  given and what their work states (`ports/findings.py`, `TenantContent`). A value of at least
  `SHORTEST` characters is matched as a whole, after both texts are folded to lower case with
  every run of punctuation made one space. So `Erika Mustermann` is found in
  `crm.erika-mustermann`. A value is also matched by each of its parts between commas,
  semicolons and line breaks.
- **A shape of a personal or a business datum.** An e-mail address, a telephone number, an IBAN,
  a card number, an amount with its currency, a street with its number, a postcode with its
  town. These are matched whether or not the tenant holds them.

A part that fails is not sent. Each match names its kind and the excerpt it found, for the
person on the instance alone: an excerpt never leaves and is never logged.

Pure and deterministic: a rule, never a probabilistic method (UC-6.12 §2).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

type MatchKind = Literal[
    "tenant_value",
    "email",
    "phone",
    "iban",
    "card",
    "amount",
    "street",
    "postcode",
    "secret",
    "empty",
]
"""What a match is. `secret` and `empty` are found by the service, not by `check`: a secret
value the instance holds, and a report without a title or a text."""

SHORTEST = 5
"""A tenant's value shorter than this, folded, is not matched: it would match ordinary words."""

_PARTS = re.compile(r"[,;\n]+")
_FOLD = re.compile(r"[\W_]+", re.UNICODE)

_CURRENCY = r"(?:€|\$|£|EUR|USD|GBP|CHF)"
_SHAPES: tuple[tuple[MatchKind, re.Pattern[str]], ...] = (
    ("email", re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")),
    ("iban", re.compile(r"\b[A-Z]{2}[0-9]{2}(?: ?[A-Z0-9]){11,30}\b")),
    ("card", re.compile(r"\b(?:[0-9][ -]?){12,18}[0-9]\b")),
    ("phone", re.compile(r"(?<![\w.:-])(?:\+|00)[0-9][0-9 ()/-]{6,}[0-9]")),
    (
        "amount",
        re.compile(
            rf"{_CURRENCY}\s?[0-9][0-9.,' ]*[0-9]|\b[0-9][0-9.,']*[0-9]?\s?{_CURRENCY}(?![A-Za-z])",
            re.IGNORECASE,
        ),
    ),
    (
        "street",
        re.compile(
            r"\b[\w.-]*(?:stra(?:ß|ss)e|str\.|weg|gasse|platz|allee|street|road|avenue|lane)"
            r"\s+[0-9]{1,4}[a-z]?\b",
            re.IGNORECASE,
        ),
    ),
    ("postcode", re.compile(r"\b[0-9]{5}\s+[A-ZÄÖÜ][a-zäöüß]{2,}")),
)


@dataclass(frozen=True)
class Match:
    """One thing a part carries that may not leave: its kind, and what was found, for the eyes
    of the person on the instance alone."""

    kind: MatchKind
    excerpt: str


def fold(text: str) -> str:
    """Lower case, every run of punctuation and space one space, trimmed."""
    return _FOLD.sub(" ", text.casefold()).strip()


def values(raw: Iterable[str]) -> frozenset[str]:
    """The tenant's values as the rule matches them: each value, and each of its parts, folded,
    those shorter than `SHORTEST` left out."""
    found: set[str] = set()
    for value in raw:
        for each in (value, *_PARTS.split(value)):
            folded = fold(each)
            if len(folded) >= SHORTEST:
                found.add(folded)
    return frozenset(found)


def check(parts: Iterable[str], tenant: frozenset[str]) -> tuple[Match, ...]:
    """Everything the parts carry that may not leave; empty when they may leave. `tenant` is
    the tenant's values, as `values` folds them."""
    matches: list[Match] = []
    for part in parts:
        folded = f" {fold(part)} "
        for value in sorted(tenant):
            if f" {value} " in folded:
                matches.append(Match(kind="tenant_value", excerpt=value))
        for kind, pattern in _SHAPES:
            for found in pattern.finditer(part):
                matches.append(Match(kind=kind, excerpt=found.group(0).strip()))
    return tuple(dict.fromkeys(matches))
