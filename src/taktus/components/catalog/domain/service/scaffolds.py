"""The rules of method scaffolds (ADR-0307). Pure: every rule reads what it is given and returns
what follows, the same way every time, so that a person can recompute it.

- **The file.** `parse_scaffold` holds the parsed `scaffold.yaml` of a skill to its format, with
  the texts of the templates its artifacts name.
- **The check.** `examine` names each artifact `present`, `missing`, `unmaintained` or `unread`
  from what one reading observed and the project's newest change. An artifact is measured
  against the project, never against the calendar (NTC-0279).
- **Furnishing.** `to_create` is every artifact a check found missing, and nothing else: an
  artifact that is there is never overwritten (UC-13.2 §3).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from pydantic import ValidationError

from taktus.components.catalog.domain.model.scaffold import (
    FORMAT,
    SCAFFOLD_YAML,
    ArtifactFinding,
    ArtifactState,
    InvalidScaffold,
    Observed,
    ProjectCheck,
    Scaffold,
    ScaffoldArtifact,
)

FIELDS = {"scaffold", "work", "artifacts"}


def is_scaffold(texts: Mapping[str, str]) -> bool:
    """Whether a skill directory, by the texts it kept, is a scaffold."""
    return SCAFFOLD_YAML in texts


def parse_scaffold(name: str, declared: Any, texts: Mapping[str, str]) -> Scaffold:
    """The scaffold a skill directory declares, or InvalidScaffold naming every finding.
    `declared` is the parsed `scaffold.yaml`; `texts` every text file of the directory by its
    relative path, the templates among them."""
    if not isinstance(declared, Mapping):
        raise InvalidScaffold((f"{SCAFFOLD_YAML} is a mapping",))
    findings: list[str] = []
    unknown = sorted(str(k) for k in declared if k not in FIELDS)
    if unknown:
        findings.append(f"{SCAFFOLD_YAML} knows no field {', '.join(unknown)}")
    if declared.get("scaffold") != FORMAT:
        findings.append(f"`scaffold` is the format's version, {FORMAT}")
    work = declared.get("work")
    if not isinstance(work, str) or not work.strip():
        findings.append("`work` names the kind of work the scaffold is for")
    raw = declared.get("artifacts")
    if not isinstance(raw, list) or not raw:
        findings.append("`artifacts` lists at least one artifact")
        raw = []
    artifacts: list[ScaffoldArtifact] = []
    for index, entry in enumerate(raw, start=1):
        try:
            artifacts.append(ScaffoldArtifact.model_validate(entry))
        except ValidationError as error:
            where = entry.get("id") if isinstance(entry, Mapping) else None
            for problem in error.errors():
                at = ".".join(str(p) for p in problem["loc"]) or "artifact"
                findings.append(f"artifact {where or index}: {at}: {problem['msg']}")
    for artifact in artifacts:
        if artifact.template not in texts:
            findings.append(
                f"artifact {artifact.id}: the template {artifact.template!r} is no text file of "
                "the scaffold's directory"
            )
    ids = [a.id for a in artifacts]
    if len(set(ids)) != len(ids):
        findings.append("every artifact has an identifier of its own")
    if findings:
        raise InvalidScaffold(tuple(findings))
    return Scaffold(
        name=name,
        work=str(work).strip(),
        artifacts=tuple(artifacts),
        templates={a.template: texts[a.template] for a in artifacts},
    )


def newest_change(*moments: datetime | None) -> datetime | None:
    """The project's newest change: the latest of the moments that are known."""
    known = [m for m in moments if m is not None]
    return max(known) if known else None


def examine(
    scaffold: Scaffold, observed: Mapping[str, Observed], newest: datetime | None
) -> tuple[ArtifactFinding, ...]:
    """Every artifact of the scaffold, in its order, with its state (ADR-0307 §3). An artifact
    nothing was observed of is `unread`: a check never assumes it is there."""
    findings: list[ArtifactFinding] = []
    for artifact in scaffold.artifacts:
        seen = observed.get(artifact.id)
        state = ArtifactState.PRESENT
        stale: int | None = None
        reason: str | None = None
        if seen is None or not seen.read:
            state = ArtifactState.UNREAD
            reason = "nothing was read" if seen is None else seen.reason
        elif not seen.present:
            state = ArtifactState.MISSING
        else:
            stale = _stale_days(artifact, seen.changed_at, newest)
            if stale is not None:
                state = ArtifactState.UNMAINTAINED
        findings.append(
            ArtifactFinding(
                artifact=artifact.id,
                title=artifact.title,
                system=artifact.system,
                state=state,
                changed_at=seen.changed_at if seen is not None and seen.present else None,
                stale_days=stale,
                reason=reason,
            )
        )
    return tuple(findings)


def _stale_days(
    artifact: ScaffoldArtifact, changed_at: datetime | None, newest: datetime | None
) -> int | None:
    """By how many whole days the project moved on past the artifact, where that is more than
    its window; None where it is maintained, or nothing says otherwise."""
    if artifact.maintained_days is None or changed_at is None or newest is None:
        return None
    days = (newest - changed_at).days
    return days if days > artifact.maintained_days else None


def to_create(scaffold: Scaffold, check: ProjectCheck) -> tuple[ScaffoldArtifact, ...]:
    """The artifacts furnishing creates: exactly those the check found missing."""
    missing = {f.artifact for f in check.of(ArtifactState.MISSING)}
    return tuple(a for a in scaffold.artifacts if a.id in missing)
