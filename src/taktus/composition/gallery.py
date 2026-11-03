"""The gallery: blueprints in open files a person chooses a first process from (UC-10.4,
ADR-0136 §1 to §3).

- **A directory of open files.** Each directory below the gallery's directory that holds a
  `gallery.yaml` is one gallery blueprint; its processes are the bundles under its
  `processes/`. The directory is read on every request and nothing of it is kept, so a
  blueprint removed from it is gone at the next reading. No directory, or one that does not
  exist, is an empty gallery.
- **Held to rules.** A bundle is offered only where it passes the checks registration applies
  to a bundle on its own (`parse_bundle`, as `taktusctl bundle check`), and only at autonomy
  level 1 or 2. One that fails is listed with why, and cannot be chosen.
- **Choosing makes a proposal.** The person's choices — inputs a schedule trigger of the bundle
  gives — are written into those triggers, and the changed bundle becomes a proposal through
  `Proposals.propose`, held to every check a proposal is held to. Where the tenant registered
  versions of the process already, it names the next free one.

This is wiring: it reads files and acts on the process component, which only the composition
root may join (`composition/README.md`).
"""

from __future__ import annotations

import copy
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from taktus.components.process.application.service.proposals import (
    ProposalError,
    Proposals,
    Propose,
)
from taktus.components.process.application.service.register_version import parse_bundle
from taktus.components.process.domain.model import InvalidProcess, ProcessVersion, Proposal
from taktus.components.process.domain.service.bundle import next_version
from taktus.ports.persistence import Repository, Tenant, UnitOfWork

DESCRIPTION = "gallery.yaml"
PROCESSES = "processes"
SUFFIXES = (".yaml", ".yml")
NAME = re.compile(r"^[a-z0-9][a-z0-9-]*$")
HIGHEST_LEVEL = 2
"""The highest autonomy level a gallery process starts at (UC-10.3, UC-10.4)."""


@dataclass(frozen=True)
class Choice:
    """A value the person sets before the process is proposed: one of its declared inputs."""

    name: str
    label: str
    value: Any


@dataclass(frozen=True)
class OfferedStep:
    id: str
    method: str
    reason: str


@dataclass(frozen=True)
class Offered:
    """One process of a gallery blueprint, as the gallery shows it. `refused` says why it is
    not offered; such a process has no steps or choices to show."""

    id: str
    name: str
    reason: str
    level: int | None = None
    level_reason: str = ""
    steps: tuple[OfferedStep, ...] = ()
    choices: tuple[Choice, ...] = ()
    refused: tuple[str, ...] = ()

    def document(self) -> dict[str, Any]:
        found: dict[str, Any] = {"id": self.id, "name": self.name, "reason": self.reason}
        if self.refused:
            found["refused"] = list(self.refused)
            return found
        found["level"] = self.level
        found["level_reason"] = self.level_reason
        found["steps"] = [{"id": s.id, "method": s.method, "reason": s.reason} for s in self.steps]
        found["choices"] = [
            {"name": c.name, "label": c.label, "value": c.value} for c in self.choices
        ]
        return found


@dataclass(frozen=True)
class Blueprint:
    id: str
    title: str
    audience: str
    summary: str
    processes: tuple[Offered, ...]

    def document(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "for": self.audience,
            "summary": self.summary,
            "processes": [p.document() for p in self.processes],
        }


class Gallery:
    def __init__(
        self,
        directory: Path | None,
        proposals: Proposals,
        versions: Repository[ProcessVersion],
        work: UnitOfWork,
    ) -> None:
        """`directory` is `TAKTUS_GALLERY_DIRECTORY`; None: the gallery is empty."""
        self._directory = directory
        self._proposals = proposals
        self._versions = versions
        self._work = work

    def listed(self) -> list[dict[str, Any]]:
        """Every gallery blueprint as the HTTP surface answers it."""
        return [b.document() for b in self.blueprints()]

    def blueprints(self) -> list[Blueprint]:
        """Every gallery blueprint, by its directory's name."""
        root = self._directory
        if root is None or not root.is_dir():
            return []
        found = []
        for folder in sorted(p for p in root.iterdir() if p.is_dir()):
            described = _description(folder)
            if described is None:
                continue
            found.append(
                Blueprint(
                    id=folder.name,
                    title=str(described.get("title") or folder.name),
                    audience=str(described.get("for") or ""),
                    summary=" ".join(str(described.get("summary") or "").split()),
                    processes=tuple(_offered(path) for path in _bundles(folder)),
                )
            )
        return found

    def blueprint(self, blueprint_id: str) -> Blueprint:
        for found in self.blueprints():
            if found.id == blueprint_id:
                return found
        raise ProposalError("unknown", f"the gallery holds no blueprint {blueprint_id!r}")

    async def propose(
        self,
        tenant: Tenant,
        blueprint_id: str,
        process_id: str,
        choices: Mapping[str, Any],
        by: str,
    ) -> Proposal:
        """The chosen process, with the person's choices, as a proposal (ADR-0136 §3).
        ProposalError `unknown` for a blueprint or process the gallery does not hold;
        InvalidProcess with every finding for one it does not offer, a choice it does not offer,
        or a bundle the proposal refuses."""
        blueprint = self.blueprint(blueprint_id)
        offered = next((p for p in blueprint.processes if p.id == process_id), None)
        if offered is None:
            raise ProposalError(
                "unknown", f"the blueprint {blueprint_id!r} offers no process {process_id!r}"
            )
        if offered.refused:
            raise InvalidProcess(offered.refused)
        path = next(p for p in _bundles(self._folder(blueprint_id)) if _id_of(p) == process_id)
        document = _load(path)
        offers = {c.name for c in offered.choices}
        unknown = sorted(set(choices) - offers)
        if unknown:
            raise InvalidProcess(
                tuple(
                    f"{process_id} offers no choice {name!r}; it offers {sorted(offers)}"
                    for name in unknown
                )
            )
        chosen = _with_choices(document, choices)
        async with self._work.transaction(tenant):
            registered = [
                v.version for v in await self._versions.list(tenant) if v.process_id == process_id
            ]
        if registered:
            chosen["version"] = next_version(registered)
        return await self._proposals.propose(
            Propose(
                tenant=tenant,
                process_id=process_id,
                bundle=chosen,
                by=by,
                request=f"from the gallery: {blueprint.title}",
            )
        )

    def _folder(self, blueprint_id: str) -> Path:
        # A blueprint was found, so the directory is named.
        return (self._directory or Path()) / blueprint_id


def _description(folder: Path) -> dict[str, Any] | None:
    path = folder / DESCRIPTION
    if not NAME.match(folder.name) or not path.is_file():
        return None
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return None
    return document if isinstance(document, dict) else None


def _bundles(folder: Path) -> list[Path]:
    processes = folder / PROCESSES
    if not processes.is_dir():
        return []
    return sorted(p for p in processes.iterdir() if p.is_file() and p.suffix in SUFFIXES)


def _load(path: Path) -> dict[str, Any]:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError("the bundle is not a mapping")
    return document


def _id_of(path: Path) -> str:
    try:
        document = _load(path)
    except (OSError, yaml.YAMLError, ValueError):
        return path.stem
    return str(document.get("id") or path.stem)


def _offered(path: Path) -> Offered:
    try:
        document = _load(path)
    except (OSError, yaml.YAMLError, ValueError) as error:
        return Offered(id=path.stem, name=path.stem, reason="", refused=(f"unreadable: {error}",))
    process_id = str(document.get("id") or path.stem)
    name = str(document.get("name") or process_id)
    reason = " ".join(str(document.get("reason") or "").split())
    try:
        version = parse_bundle(document)
    except InvalidProcess as error:
        return Offered(id=process_id, name=name, reason=reason, refused=error.findings)
    if version.autonomy_level > HIGHEST_LEVEL:
        return Offered(
            id=process_id,
            name=name,
            reason=reason,
            refused=(
                f"it starts at autonomy level {version.autonomy_level}; a gallery process "
                f"starts at level {HIGHEST_LEVEL} or below",
            ),
        )
    return Offered(
        id=process_id,
        name=name,
        reason=reason,
        level=version.autonomy_level,
        level_reason=" ".join(version.autonomy.reason.split()),
        steps=tuple(
            OfferedStep(id=s.id, method=str(s.method), reason=" ".join(s.reason.split()))
            for s in version.ordered()
        ),
        choices=_choices(version),
    )


def _choices(version: ProcessVersion) -> tuple[Choice, ...]:
    """Each declared input a schedule trigger gives, with the value the first such gives."""
    given: dict[str, Any] = {}
    for trigger in version.triggers:
        if trigger.schedule is None or not trigger.inputs:
            continue
        for name, value in trigger.inputs.items():
            if name in version.inputs and name not in given:
                given[name] = value
    return tuple(
        Choice(name=name, label=" ".join(version.inputs[name].description.split()), value=value)
        for name, value in given.items()
    )


def _with_choices(document: Mapping[str, Any], choices: Mapping[str, Any]) -> dict[str, Any]:
    """The bundle with each choice written into every schedule trigger that gives it."""
    changed = copy.deepcopy(dict(document))
    for trigger in changed.get("triggers") or ():
        if not isinstance(trigger, dict) or "schedule" not in trigger:
            continue
        inputs = trigger.get("inputs")
        if not isinstance(inputs, dict):
            continue
        for name, value in choices.items():
            if name in inputs:
                inputs[name] = value
    return changed
