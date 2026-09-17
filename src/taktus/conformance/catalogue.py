"""What the suite knows about every check of every contract: its title, what the contract
requires, and where the README states the rule.

One catalogue per contract. A check identifier is unique across contracts — `W-` for the worker
contract, `C-` for the connector contract — so that a result can name its catalogue by its
identifier alone. The report and the findings work on identifiers and look the rest up here.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class Check:
    """One check: `requirement` is what the contract demands, `section` where the README states
    it — the reader of a failure looks it up there."""

    id: str
    title: str
    requirement: str
    section: str


@dataclass(frozen=True)
class Catalogue:
    """Every check of one contract, in order, with the README that states the rules."""

    contract: str
    readme: str
    checks: Mapping[str, Check]
    unrunnable: frozenset[str]
    """Checks outside what a suite against one endpoint can prove; reported as pending."""

    def __iter__(self) -> Iterator[str]:
        return iter(self.checks)

    def __contains__(self, check: object) -> bool:
        return check in self.checks

    @property
    def runnable(self) -> list[str]:
        return [check for check in self.checks if check not in self.unrunnable]

    def where(self, check: str) -> str:
        return f"{self.readme} {self.checks[check].section}"

    @classmethod
    def build(
        cls,
        contract: str,
        readme: str,
        titles: Mapping[str, str],
        requirements: Mapping[str, str],
        sections: Mapping[str, str],
        unrunnable: frozenset[str],
    ) -> Catalogue:
        missing = set(titles) ^ set(requirements) | set(titles) ^ set(sections)
        if missing:
            raise ValueError(f"{contract}: checks without title, requirement or section: {missing}")
        return cls(
            contract,
            readme,
            {c: Check(c, titles[c], requirements[c], sections[c]) for c in titles},
            unrunnable,
        )


def catalogue_of(check: str) -> Catalogue:
    """The catalogue a check identifier belongs to."""
    from taktus.conformance.connector.rules import CATALOGUE as connector
    from taktus.conformance.rules import CATALOGUE as worker

    for catalogue in (worker, connector):
        if check in catalogue:
            return catalogue
    raise KeyError(check)
