"""Use case: a project is checked against its method scaffold and furnished in the organisation's
own systems (ADR-0307, UC-13.2).

**Check.** One reading of the repository at one commit — when each path last changed
(`repository.files.dates`), which files are there (`repository.files.read_many`), which
directories hold a file (`repository.files.list`) — and one of the knowledge system per page
(`knowledge.pages.list`). The rule `examine` names each artifact from that reading. A system
that cannot be read leaves its artifacts `unread`, never `present`.

**Furnish.** A fresh check, then every artifact it found missing created from its template, and
nothing else. Repository artifacts arrive as one branch with one commit and one pull request onto
the project's branch, which a person merges. Pages are written with `expected` null, so a page
that appeared in between is kept. Every write's key is derived from the caller's run identifier
and what it writes, so a repeat after a restart creates nothing twice.

Every outward act goes through a capability (ADR-0003): which repository and which knowledge
system serve it is configuration. Which scaffold version is read, and whether it may furnish, is
the caller's to hand in with the scaffold (`composition/scaffolds.py`): a check reads any version
that is neither retired nor private, furnishing only one in production.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from taktus.components.catalog.domain.model.scaffold import (
    ArtifactState,
    Observed,
    ProjectCheck,
    Scaffold,
    ScaffoldArtifact,
    Shape,
    System,
)
from taktus.components.catalog.domain.service.scaffolds import examine, newest_change, to_create
from taktus.ports.connector import (
    ActionConnector,
    CallContext,
    CallFailed,
    Cause,
    ConnectorError,
    idempotency_key,
)
from taktus.ports.worker import CredentialReference
from taktus.shared.v1 import Value

DATES = "repository.files.dates"
READ_MANY = "repository.files.read_many"
LIST_FILES = "repository.files.list"
CREATE_BRANCH = "repository.branches.create"
OPEN_PULL = "repository.pullrequests.open"
LIST_PAGES = "knowledge.pages.list"
WRITE_PAGE = "knowledge.pages.write"
MAX_PATHS = 100
"""The most paths one reading of dates takes (`repository.files.dates`)."""


@dataclass(frozen=True)
class Project:
    """Where a scaffold is applied: a branch of the repository and, where the organisation has
    a knowledge system, a place of two names in it, shelf and book."""

    branch: str
    place: tuple[str, str] | None = None


@dataclass(frozen=True)
class Acting:
    """Who acts, under which run identifier, with whose credentials by name."""

    tenant: str
    identity: str
    run_id: str
    credentials: tuple[CredentialReference, ...] = ()


class Furnished(Value):
    """What furnishing created, and the check it acted on."""

    check: ProjectCheck
    created: tuple[str, ...]
    """The artifacts created: files on the branch, and pages written."""
    kept: tuple[str, ...] = ()
    """Pages that appeared between the check and the write, kept as they are."""
    branch: str | None = None
    pull_request: int | None = None
    pull_request_url: str | None = None


class ScaffoldProjects:
    def __init__(
        self, repository: ActionConnector | None, knowledge: ActionConnector | None
    ) -> None:
        self._repository = repository
        self._knowledge = knowledge

    # --- check ------------------------------------------------------------------------------

    async def check(
        self,
        scaffold: Scaffold,
        version: str,
        stage: str,
        project: Project,
        acting: Acting,
    ) -> ProjectCheck:
        observed: dict[str, Observed] = {}
        commit, committed = await self._repository_reading(scaffold, project, acting, observed)
        pages = await self._knowledge_reading(scaffold, project, acting, observed)
        newest = newest_change(committed, *pages)
        return ProjectCheck(
            scaffold=f"{scaffold.name}@{version}",
            stage=stage,
            commit=commit,
            newest=newest,
            findings=examine(scaffold, observed, newest),
        )

    async def _repository_reading(
        self,
        scaffold: Scaffold,
        project: Project,
        acting: Acting,
        observed: dict[str, Observed],
    ) -> tuple[str | None, datetime | None]:
        artifacts = [a for a in scaffold.artifacts if a.system is System.REPOSITORY]
        if not artifacts:
            return None, None
        if self._repository is None:
            for a in artifacts:
                observed[a.id] = Observed(read=False, reason="no repository is configured")
            return None, None
        if len(artifacts) > MAX_PATHS:
            raise ValueError(f"a scaffold declares at most {MAX_PATHS} repository artifacts")
        paths = [str(a.path) for a in artifacts]
        try:
            dated = await self._call(
                self._repository,
                DATES,
                acting,
                "scaffold-dates",
                {"paths": paths, "ref": project.branch},
            )
            commit = str(dated["commit"])
            changed = {
                str(f["path"]): _moment(f.get("changed_at")) for f in dated.get("files") or ()
            }
            files = [a for a in artifacts if a.shape is Shape.FILE]
            present: set[str] = set()
            if files:
                read = await self._call(
                    self._repository,
                    READ_MANY,
                    acting,
                    "scaffold-files",
                    {"paths": [str(a.path) for a in files], "ref": commit},
                )
                present |= {
                    str(f["path"]) for f in read.get("files") or () if f.get("content") is not None
                }
            for a in artifacts:
                if a.shape is Shape.DIRECTORY and await self._holds_a_file(
                    self._repository, str(a.path), commit, acting
                ):
                    present.add(str(a.path))
        except (CallFailed, ConnectorError) as failed:
            reason = _reason(failed)
            for a in artifacts:
                observed[a.id] = Observed(read=False, reason=reason)
            return None, None
        for a in artifacts:
            observed[a.id] = Observed(
                present=a.path in present, changed_at=changed.get(str(a.path))
            )
        return commit, _moment(dated.get("committed_at"))

    async def _holds_a_file(
        self, repository: ActionConnector, path: str, commit: str, acting: Acting
    ) -> bool:
        try:
            listed = await self._call(
                repository,
                LIST_FILES,
                acting,
                f"scaffold-list-{_digest(path)}",
                {"path": path, "ref": commit},
            )
        except CallFailed as failed:
            if failed.error.cause in (Cause.NOT_FOUND, Cause.INVALID):
                return False
            raise
        return bool(listed.get("entries"))

    async def _knowledge_reading(
        self,
        scaffold: Scaffold,
        project: Project,
        acting: Acting,
        observed: dict[str, Observed],
    ) -> list[datetime | None]:
        artifacts = [a for a in scaffold.artifacts if a.system is System.KNOWLEDGE]
        if not artifacts:
            return []
        if self._knowledge is None or project.place is None:
            reason = (
                "no knowledge system is configured"
                if self._knowledge is None
                else "the project names no place in the knowledge system"
            )
            for a in artifacts:
                observed[a.id] = Observed(read=False, reason=reason)
            return []
        moments: list[datetime | None] = []
        for a in artifacts:
            place = [*project.place, str(a.page)]
            try:
                listed = await self._call(
                    self._knowledge,
                    LIST_PAGES,
                    acting,
                    f"scaffold-page-{_digest(a.id)}",
                    {"place": place},
                )
            except (CallFailed, ConnectorError) as failed:
                if isinstance(failed, CallFailed) and failed.error.cause is Cause.NOT_FOUND:
                    observed[a.id] = Observed(present=False)
                    continue
                observed[a.id] = Observed(read=False, reason=_reason(failed))
                continue
            entry = next(
                (p for p in listed.get("pages") or () if list(p.get("place") or ()) == place),
                None,
            )
            changed = None if entry is None else _moment(entry.get("changed_at"))
            observed[a.id] = Observed(present=entry is not None, changed_at=changed)
            moments.append(changed)
        return moments

    # --- furnish ----------------------------------------------------------------------------

    async def furnish(
        self,
        scaffold: Scaffold,
        version: str,
        stage: str,
        project: Project,
        acting: Acting,
    ) -> Furnished:
        """Create every artifact a fresh check finds missing. The caller hands in only a version
        in production (ADR-0307 §4)."""
        check = await self.check(scaffold, version, stage, project, acting)
        creating = to_create(scaffold, check)
        files = [a for a in creating if a.system is System.REPOSITORY]
        pages = [a for a in creating if a.system is System.KNOWLEDGE]
        created: list[str] = []
        kept: list[str] = []
        branch = pull = url = None
        if files and self._repository is not None:
            branch, pull, url = await self._propose(
                self._repository, scaffold, check, files, project, acting
            )
            created.extend(a.id for a in files)
        for a in pages:
            if self._knowledge is None or project.place is None:
                continue
            if await self._write_page(self._knowledge, project.place, scaffold, check, a, acting):
                created.append(a.id)
            else:
                kept.append(a.id)
        return Furnished(
            check=check,
            created=tuple(created),
            kept=tuple(kept),
            branch=branch,
            pull_request=pull,
            pull_request_url=url,
        )

    async def _propose(
        self,
        repository: ActionConnector,
        scaffold: Scaffold,
        check: ProjectCheck,
        files: Sequence[ScaffoldArtifact],
        project: Project,
        acting: Acting,
    ) -> tuple[str, int | None, str | None]:
        branch = f"taktus/scaffold-{_slug(scaffold.name)}-{_digest(acting.run_id)[:12]}"
        await self._call(
            repository,
            CREATE_BRANCH,
            acting,
            "scaffold-branch",
            {
                "name": branch,
                "base": check.commit or project.branch,
                "message": f"{scaffold.name}: the artifacts the project is missing",
                "files": [
                    {"path": str(a.created_at), "content": scaffold.templates[a.template]}
                    for a in files
                ],
            },
        )
        opened = await self._call(
            repository,
            OPEN_PULL,
            acting,
            "scaffold-pull",
            {
                "head": branch,
                "base": project.branch,
                "title": f"{scaffold.name}: the artifacts the project is missing",
                "body": _body(check, files),
            },
        )
        number = opened.get("number")
        return (
            branch,
            number if isinstance(number, int) else None,
            str(opened.get("url") or "") or None,
        )

    async def _write_page(
        self,
        knowledge: ActionConnector,
        place: tuple[str, str],
        scaffold: Scaffold,
        check: ProjectCheck,
        artifact: ScaffoldArtifact,
        acting: Acting,
    ) -> bool:
        try:
            await self._call(
                knowledge,
                WRITE_PAGE,
                acting,
                f"scaffold-write-{_digest(artifact.id)}",
                {
                    "place": [*place, str(artifact.page)],
                    "body": scaffold.templates[artifact.template],
                    "mark": f"scaffold:{check.scaffold}:{artifact.id}",
                    "expected": None,
                },
            )
        except CallFailed as failed:
            if failed.error.cause is Cause.CONFLICT:
                return False
            raise
        return True

    @staticmethod
    async def _call(
        connector: ActionConnector, operation: str, acting: Acting, step: str, input: dict[str, Any]
    ) -> Mapping[str, Any]:
        context = CallContext(
            tenant=acting.tenant,
            identity=acting.identity,
            run_id=acting.run_id,
            step_id=step,
            attempt=1,
            idempotency_key=idempotency_key(acting.run_id, step, 1),
            credentials=acting.credentials,
        )
        return (await connector.call(operation, context, input)).output


def summary(check: ProjectCheck) -> dict[str, Any]:
    """The check as a document, with the titles of what is missing and unmaintained."""
    return {
        **check.model_dump(mode="json"),
        "missing": [f.title for f in check.of(ArtifactState.MISSING)],
        "unmaintained": [f.title for f in check.of(ArtifactState.UNMAINTAINED)],
    }


def furnished(done: Furnished) -> dict[str, Any]:
    """What a furnishing created, as a document."""
    return {
        "scaffold": done.check.scaffold,
        "created": list(done.created),
        "kept": list(done.kept),
        "branch": done.branch,
        "pull_request": done.pull_request,
        "pull_request_url": done.pull_request_url,
        "check": summary(done.check),
    }


def _moment(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "-", name.lower()).strip("-")[:40]


def _reason(failed: Exception) -> str:
    if isinstance(failed, CallFailed):
        return f"{failed.error.cause.value}: {failed.error.detail}"
    return str(failed)


def _body(check: ProjectCheck, files: Sequence[ScaffoldArtifact]) -> str:
    lines = [
        f"The scaffold `{check.scaffold}` names artifacts this project does not have yet. "
        "This change adds each as a template: the structure is here, and its content is "
        "yours to write.",
        "",
    ]
    lines += [f"- `{a.created_at}` — {a.title}: {a.why}" for a in files]
    unmaintained = check.of(ArtifactState.UNMAINTAINED)
    if unmaintained:
        lines += ["", "Not changed here, and not maintained for a while:"]
        lines += [f"- {f.title}, {f.stale_days} days behind the project" for f in unmaintained]
    return "\n".join(lines)
