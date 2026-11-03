"""What a person may ask Taktus for: the processes they may start (UC-1.13, ADR-0159 §1).

A **catalogue entry** is one process with an active version that the reader may see, in plain
words: what it is for, what it needs from the person, the level it runs at, the roles a person
acts in along it, and how to start it on each channel. Every way of starting it issues the one
command of `command/domain/service/start.py`; the entry shows that command, so that a reader can
check that the web app, the chat and their own agent ask for the same thing.

The catalogue is a projection of the registered versions. It keeps no request, no queue and no
promised time: a start is a run, and the run's own view tracks it (principle 1).

Pure: the facts in, the catalogue out. Nothing is stored.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from taktus.shared.v1 import Value

RECOGNISED = "process.run"
"""What the command of every start is recognised as (`command/domain/service/start.py`)."""

AGENT_TOOL = "start_process"
AGENT_RIGHT = "agent.start"

NOTHING_FITS = (
    "If nothing here fits, describe what you need as a change in dialogue, or choose a first "
    "process from the gallery."
)


class CatalogueInput(Value):
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    required: bool
    example: Any = None


class CatalogueFacts(Value):
    """One process with an active version, as the process component holds it."""

    process: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str | None = None
    version: str = Field(min_length=1)
    """`<process>@<version>`: the active one."""
    level: int = Field(ge=1, le=4)
    inputs: tuple[CatalogueInput, ...] = ()
    roles: tuple[str, ...] = ()
    """The roles a person acts in at a step of the version, in the order of the steps."""


class StartCommand(Value):
    intent: str = Field(min_length=1)
    recognised: str = Field(min_length=1)


class StartWays(Value):
    """How the entry is started on each channel; each issues `command`."""

    web: str = Field(min_length=1)
    """The route the web app posts to, below the prefix."""
    agent: dict[str, Any]
    """The tool a person's own agent calls, its arguments, the right it needs and whether a
    role the reader holds grants it (ADR-0131 §3)."""
    chat: str | None = None
    """What the person writes in the owner's conversation; None where the chat reads no start,
    or the process needs an input a reply cannot give."""


class CatalogueEntry(Value):
    process: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str | None = None
    version: str = Field(min_length=1)
    level: int
    needs: tuple[CatalogueInput, ...]
    roles: tuple[str, ...]
    command: StartCommand
    start: StartWays
    text: str = Field(min_length=1)
    """The text equivalent of the entry."""


class Catalogue(Value):
    entries: tuple[CatalogueEntry, ...]
    summary: str = Field(min_length=1)
    nothing_fits: str = Field(min_length=1)


def _text(facts: CatalogueFacts) -> str:
    what = (facts.description or facts.name).rstrip(".")
    needed = [i.name for i in facts.inputs if i.required]
    text = f"{facts.name} ({facts.process}): {what}. Runs at level {facts.level}."
    text += f" Needs {', '.join(needed)}." if needed else " Needs nothing from you to start."
    if facts.roles:
        text += f" A person acts in the role {', '.join(dict.fromkeys(facts.roles))}."
    return text


def catalogue(
    processes: list[CatalogueFacts],
    *,
    agent_may_start: bool,
    chat_word: str | None,
) -> Catalogue:
    """The entries the reader may start, by name. `processes` are those the reader may see;
    `agent_may_start` whether a role they hold grants `agent.start`; `chat_word` the first word
    the tenant's chat reads a start by, or None where it reads none."""
    entries: list[CatalogueEntry] = []
    for facts in sorted(processes, key=lambda p: (p.name.casefold(), p.process)):
        needs_input = any(i.required for i in facts.inputs)
        entries.append(
            CatalogueEntry(
                process=facts.process,
                name=facts.name,
                description=facts.description,
                version=facts.version,
                level=facts.level,
                needs=facts.inputs,
                roles=tuple(dict.fromkeys(facts.roles)),
                command=StartCommand(intent=f"run {facts.version}", recognised=RECOGNISED),
                start=StartWays(
                    web=f"/catalogue/{facts.process}/start",
                    agent={
                        "tool": AGENT_TOOL,
                        "arguments": {"process": facts.process},
                        "right": AGENT_RIGHT,
                        "held": agent_may_start,
                    },
                    chat=None
                    if chat_word is None or needs_input
                    else f"{chat_word} {facts.process}",
                ),
                text=_text(facts),
            )
        )
    count = len(entries)
    summary = (
        "There is no process you may start yet."
        if not count
        else f"You may start {count} {'process' if count == 1 else 'processes'}."
    )
    return Catalogue(entries=tuple(entries), summary=summary, nothing_fits=NOTHING_FITS)
