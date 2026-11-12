"""Bringing a process nobody wrote down to light (UC-9.4, ADR-0245 §2).

**The interview.** Five questions, the same in the guided and the expert mode: what is done,
when and how often, with which tools, who is responsible, and how one can tell it is done. The
guided mode gives an example with each question; the expert mode asks them bare. Both write the
same documented process from the same answers (UC-13.1).

**A pattern in the requests made of Taktus.** A rule: the same request, by its words made
lower case and stripped of numbers, made by one identity in at least three different ISO weeks.
It is found for that person and shown to them first (UC-9.4 §2); it names the request as a
procedure, never how the person works.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime

from taktus.shared.v1 import Value

QUESTIONS: tuple[tuple[str, str, str], ...] = (
    ("what", "What is done?", "for example: the open invoices are checked against the bank"),
    ("when", "When, and how often?", "for example: every Friday afternoon"),
    ("tools", "With which tools or systems?", "for example: the accounting system and e-mail"),
    ("owner_role", "Which role is responsible for it?", "for example: accounting"),
    ("done", "How can one tell it is done?", "for example: every invoice is marked paid or chased"),
)
MODES = frozenset({"guided", "expert"})
WEEKS = 3
"""In at least this many different weeks a request recurs before it is a pattern."""


class Interviewed(Value):
    description: str
    owner_role: str


def questions(mode: str) -> list[dict[str, str]]:
    if mode not in MODES:
        raise ValueError(f"mode is guided or expert, not {mode!r}")
    return [
        {"key": key, "question": text, **({"example": example} if mode == "guided" else {})}
        for key, text, example in QUESTIONS
    ]


def documented(answers: Mapping[str, str]) -> Interviewed:
    """The documented process from the answers, whatever mode asked for them."""
    missing = [key for key, _, _ in QUESTIONS if not (answers.get(key) or "").strip()]
    if missing:
        raise ValueError(f"unanswered: {', '.join(missing)}")
    a = {key: answers[key].strip() for key, _, _ in QUESTIONS}
    return Interviewed(
        description=(
            f"What: {a['what']}\nWhen: {a['when']}\nTools: {a['tools']}\n"
            f"Responsible role: {a['owner_role']}\nDone when: {a['done']}"
        ),
        owner_role=a["owner_role"].lower().replace(" ", "-"),
    )


@dataclass(frozen=True)
class Request:
    """A request made of Taktus: its words, when, and by which identity."""

    words: str
    at: datetime
    identity: str


@dataclass(frozen=True)
class Pattern:
    reader: str
    request: str
    weeks: int


def _normal(words: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[0-9]+", "", words.lower())).strip(" .,!?")


def patterns(requests: Iterable[Request]) -> list[Pattern]:
    weeks: dict[tuple[str, str], set[tuple[int, int]]] = {}
    for r in requests:
        words = _normal(r.words)
        if words:
            iso = r.at.isocalendar()
            weeks.setdefault((r.identity, words), set()).add((iso.year, iso.week))
    return [
        Pattern(reader=identity, request=words, weeks=len(found))
        for (identity, words), found in sorted(weeks.items())
        if len(found) >= WEEKS
    ]
