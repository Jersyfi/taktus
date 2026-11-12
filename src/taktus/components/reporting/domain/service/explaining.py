"""Taktus explains a step, from its records (UC-6.5, ADR-0243). Pure.

The facts come from the process version, the run, the provenance record and accounting's spend,
as the composition gathers them; no fact names a person. The text is composed from them by the
template of the reader's language, which the composition hands in. A short explanation says
what was done, by which method, why, how it ended and what it cost; a full one adds the
alternatives rejected, the fallback, the inputs and the result. Every line of the short one is
in the full one.

`grounded` holds the text to the records: every number in it must be a number of the facts. An
explanation is answered only when it passes, so a phrasing — a template's or a model's — never
carries a figure the records do not.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

from pydantic import Field

from taktus.shared.v1 import Value

NUMBER = re.compile(r"\d+(?:\.\d+)?")


class Input(Value):
    kind: str
    ref: str
    read_at: str | None = None


class Alternative(Value):
    method: str
    why: str


class StepFacts(Value):
    run_id: str
    process_version: str
    step_id: str
    method: str
    reason: str
    rejected: tuple[Alternative, ...] = ()
    fallback: str | None = None
    exactness: str | None = None
    state: str
    outcome: str | None = None
    money: float | None = None
    currency: str | None = None
    takte: float | None = None
    inputs: tuple[Input, ...] = ()
    result: str | None = None


class Explanation(Value):
    depth: str
    language: str
    lines: tuple[str, ...]
    facts: StepFacts
    grounded: bool = Field(default=True)


KEYS = ("did", "why", "ended", "cost", "takt", "class", "rejected", "fallback", "input", "result")
"""The sentences a template of a language gives: configuration, never a component's text
(the core names no language). The composition ships them per language."""


def _short(f: StepFacts, t: Mapping[str, str]) -> list[str]:
    lines = [
        t["did"].format(**f.document()),
        t["why"].format(reason=f.reason),
        t["ended"].format(state=f.state, outcome="" if f.outcome is None else f" ({f.outcome})"),
    ]
    if f.money is not None and f.currency is not None:
        takt = "" if f.takte is None else f", {f.takte:g} Takt"
        lines.append(t["cost"].format(money=f"{f.money:g}", currency=f.currency, takte=takt))
    elif f.takte is not None:
        lines.append(t["takt"].format(takte=f"{f.takte:g}"))
    return lines


def explain(facts: StepFacts, depth: str, template: Mapping[str, str]) -> Explanation:
    t = dict(template)
    language = t.get("language", "en")
    lines = _short(facts, t)
    if depth == "full":
        if facts.exactness is not None:
            lines.append(t["class"].format(exactness=facts.exactness))
        lines += [t["rejected"].format(method=r.method, why=r.why) for r in facts.rejected]
        if facts.fallback is not None:
            lines.append(t["fallback"].format(fallback=facts.fallback))
        lines += [
            t["input"].format(
                kind=i.kind, ref=i.ref, read_at="" if i.read_at is None else f" ({i.read_at})"
            )
            for i in facts.inputs
        ]
        if facts.result is not None:
            lines.append(t["result"].format(result=facts.result))
    return Explanation(
        depth=depth,
        language=language,
        lines=tuple(lines),
        facts=facts,
        grounded=not ungrounded(lines, facts),
    )


def _strings(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        for v in value.values():
            yield from _strings(v)
    elif isinstance(value, list | tuple):
        for v in value:
            yield from _strings(v)
    elif isinstance(value, float):
        yield f"{value:g}"
        yield str(value)
    elif value is not None:
        yield str(value)


def ungrounded(lines: Iterable[str], facts: StepFacts) -> list[str]:
    """The numbers of `lines` that no fact holds: empty for a grounded text."""
    known = {n for s in _strings(facts.document()) for n in NUMBER.findall(s)}
    return [n for line in lines for n in NUMBER.findall(line) if n not in known]
