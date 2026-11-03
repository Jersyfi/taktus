"""The rules of the skill lifecycle (ADR-0162). Pure: every rule reads what it is given and
returns what follows, the same way every time, so that a person can recompute it.

- **The file.** `split` takes a `SKILL.md` apart into its front matter and its instructions;
  `parse` holds the parsed front matter to the open format (ADR-0113 §1).
- **The order.** `advanced` moves a version to the next stage or refuses with the reason.
- **Approval.** `approval` says who approves at a level, and at level 4 whether the rule does.
- **The fallback.** `falls_back` compares two measurements within the tenant's tolerance.
- **Recurrence.** `recurring` counts the distinct runs in which one step of a process was
  corrected; a step at the threshold becomes a draft (UC-4.4). It never reads who corrected.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from taktus.components.catalog.domain.model.skill import (
    ORDER,
    SKILL_NAME,
    InvalidSkill,
    Measurement,
    Round,
    RoundState,
    SkillError,
    SkillFile,
    SkillPolicy,
    SkillStage,
    SkillVersion,
    StageChange,
)

FILE = "SKILL.md"
RECURS = 3
"""In how many distinct runs one step must have been corrected before its way of working is
drafted as a skill (ADR-0162 §8)."""
NAME = re.compile(SKILL_NAME)


def split(text: str) -> tuple[str, str]:
    """The front matter's text and the instructions. The file opens with a line `---`, the front
    matter follows, and the next line `---` closes it."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise InvalidSkill((f"{FILE} opens with a line `---` and its front matter",))
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return "\n".join(lines[1:index]), "\n".join(lines[index + 1 :]).strip("\n")
    raise InvalidSkill((f"{FILE}: the front matter is not closed by a line `---`",))


def digest(files: Mapping[str, bytes]) -> str:
    """The digest of a skill directory: every file by its relative path, in order."""
    hashed = hashlib.sha256()
    for path in sorted(files):
        hashed.update(path.encode("utf-8") + b"\0")
        hashed.update(hashlib.sha256(files[path]).digest())
    return "sha256:" + hashed.hexdigest()


def parse(directory: str, front: Any, instructions: str, files: Mapping[str, bytes]) -> SkillFile:
    """The skill a directory holds, or InvalidSkill naming every finding. `front` is the parsed
    front matter, `files` the directory's every file by relative path, `SKILL.md` among them."""
    findings: list[str] = []
    if not isinstance(front, Mapping):
        raise InvalidSkill((f"{FILE}: the front matter is not a mapping",))
    name = front.get("name")
    description = front.get("description")
    if not isinstance(name, str) or not 1 <= len(name) <= 64 or not NAME.match(name):
        findings.append(
            f"`name` is 1 to 64 lowercase letters, digits and single hyphens inside, not {name!r}"
        )
    elif name != directory:
        findings.append(f"`name` is {name!r}; it equals the directory's name, {directory!r}")
    if not isinstance(description, str) or not 1 <= len(description.strip()) <= 1024:
        findings.append("`description` is 1 to 1,024 characters and says what the skill does")
    if findings or not isinstance(name, str) or not isinstance(description, str):
        raise InvalidSkill(tuple(findings))
    return SkillFile(
        name=name,
        description=description.strip(),
        instructions=instructions,
        fields={k: v for k, v in front.items() if k not in ("name", "description")},
        files=tuple(sorted(p for p in files if p != FILE)),
        digest=digest(files),
    )


def advanced(version: SkillVersion, to: SkillStage, at: datetime, reason: str) -> SkillVersion:
    """The version at the next stage, or SkillError: a stage is reached from the one before it
    only; `retired` from any; production again only by a fallback (ADR-0162 §2)."""
    if version.private and to is not SkillStage.RETIRED:
        raise SkillError(
            "private", f"{version.id} is its owner's own and private until its owner shares it"
        )
    current = version.stage
    if to is SkillStage.RETIRED:
        if current is SkillStage.RETIRED:
            raise SkillError("order", f"{version.id} is retired already")
    elif to is SkillStage.PRODUCTION and current is SkillStage.RETIRED:
        if reason != "fallback":
            raise SkillError("order", f"{version.id} returns to production only by a fallback")
    elif current not in ORDER or ORDER.index(to) != ORDER.index(current) + 1:
        raise SkillError(
            "order", f"{version.id} is {current.value}; it cannot become {to.value} from there"
        )
    if to is SkillStage.EVALUATED and passed_round(version) is None:
        raise SkillError(
            "unevaluated",
            f"{version.id} has no passed round with a completed dry run; a draft without an "
            "evaluation is never approved",
        )
    return version.model_copy(
        update={
            "stage": to,
            "history": (*version.history, StageChange(stage=to, at=at, reason=reason)),
        }
    )


def passed_round(version: SkillVersion) -> Round | None:
    """The first round that passed and whose dry run completed."""
    for found in version.rounds:
        if found.state is RoundState.PASSED and found.dry_run:
            return found
    return None


def passes_in_a_row(version: SkillVersion) -> int:
    """How many of the most recent scored rounds passed, counted back to the last that did
    not."""
    count = 0
    for found in reversed([r for r in version.rounds if r.state is not RoundState.RUNNING]):
        if found.state is not RoundState.PASSED:
            break
        count += 1
    return count


@dataclass(frozen=True)
class Approval:
    by_rule: bool
    """True: the rule approves (level 4) once `required` rounds passed in a row."""
    required: int
    passed: int

    @property
    def due(self) -> bool:
        return self.by_rule and self.passed >= self.required


def approval(version: SkillVersion, level: int, policy: SkillPolicy, *, exact: bool) -> Approval:
    """Who approves the version at the lowest level among the processes using it: a person at
    levels 1 to 3, the rule at level 4 after n passed rounds in a row (ADR-0162 §4)."""
    return Approval(
        by_rule=level >= 4,
        required=policy.required(exact=exact),
        passed=passes_in_a_row(version),
    )


def latest(version: SkillVersion) -> Measurement | None:
    return max(version.measurements, key=lambda m: m.at) if version.measurements else None


def falls_back(current: SkillVersion, predecessor: SkillVersion | None, tolerance: float) -> bool:
    """Whether the version in production is worse than its predecessor beyond the tolerance:
    its newest measurement is lower than the predecessor's newest by more than it."""
    if predecessor is None:
        return False
    now, before = latest(current), latest(predecessor)
    if now is None or before is None:
        return False
    return before.score - now.score > tolerance


@dataclass(frozen=True)
class Recurrence:
    process: str
    step: str
    runs: tuple[str, ...]


def recurring(corrections: Iterable[tuple[str, str, str]]) -> list[Recurrence]:
    """Every step of a process corrected in at least `RECURS` distinct runs. A correction is
    `(process, step, run)`; nothing of who corrected is read."""
    seen: dict[tuple[str, str], set[str]] = {}
    for process, step, run in corrections:
        seen.setdefault((process, step), set()).add(run)
    return [
        Recurrence(process=process, step=step, runs=tuple(sorted(runs)))
        for (process, step), runs in sorted(seen.items())
        if len(runs) >= RECURS
    ]


def drafted_name(process: str, step: str) -> str:
    """The name of a draft drawn from one step of a process, in the open format's alphabet."""
    raw = re.sub(r"[^a-z0-9]+", "-", f"{process}-{step}".lower()).strip("-")
    return re.sub(r"-{2,}", "-", raw)[:64].strip("-")


def drafted_instructions(recurrence: Recurrence) -> str:
    """What a draft from corrections says before a person or a worker writes it out."""
    return (
        f"# {recurrence.process} / {recurrence.step}\n\n"
        f"The result of the step `{recurrence.step}` of the process `{recurrence.process}` was "
        f"corrected in {len(recurrence.runs)} runs: {', '.join(recurrence.runs)}.\n\n"
        "Read the corrected results of those runs and write here, as a new version of this "
        "skill, how the step is done so that the correction is no longer needed. This draft is "
        "never handed to a step: only a version that passed its evaluations is."
    )
