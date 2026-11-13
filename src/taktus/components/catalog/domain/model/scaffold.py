"""A method scaffold: a curated skill that declares the artifacts a project needs (ADR-0307).

The scaffold is a skill directory as ADR-0113 defines it. Its `SKILL.md` is the open format,
unchanged; beside it, `scaffold.yaml` declares the artifacts, and the other files are their
templates. What is kept here is that declaration parsed, and what a check of one project found.

A check names each artifact with one of four states (ADR-0307 §3). It reads whether the artifact
is there and when it last changed, never whether its content is right: that stays with the
person (UC-13.2 §3).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field, model_validator

from taktus.shared.v1 import Value

SCAFFOLD_YAML = "scaffold.yaml"
FORMAT = 1
"""The version of the `scaffold.yaml` format this code reads."""
ARTIFACT_ID = r"^[a-z0-9]+(-[a-z0-9]+)*$"


class InvalidScaffold(Exception):
    """A `scaffold.yaml` that does not hold to its format, with every finding."""

    def __init__(self, findings: tuple[str, ...]) -> None:
        super().__init__("; ".join(findings))
        self.findings = findings


class System(StrEnum):
    REPOSITORY = "repository"
    """The organisation's repository, through `repository.files` and `repository.branches`."""
    KNOWLEDGE = "knowledge"
    """The organisation's knowledge system, through `knowledge.pages`."""


class Shape(StrEnum):
    FILE = "file"
    DIRECTORY = "directory"


class ScaffoldArtifact(Value):
    """One thing a project needs: a file, a directory of files, or a page."""

    id: str = Field(min_length=1, max_length=64, pattern=ARTIFACT_ID)
    title: str = Field(min_length=1, max_length=200)
    why: str = Field(min_length=1, max_length=1000)
    system: System
    path: str | None = Field(default=None, min_length=1)
    """For the repository: relative, never leaving the tree."""
    shape: Shape | None = None
    """For the repository: a file or a directory."""
    page: str | None = Field(default=None, min_length=1, max_length=200)
    """For the knowledge system: the page's name in the project's place."""
    template: str = Field(min_length=1)
    """A file of the scaffold's own directory, by relative path."""
    maintained_days: int | None = Field(default=None, ge=1)
    """How long it may stay unchanged while the project moves on; None: presence only."""

    @model_validator(mode="after")
    def _addressed(self) -> ScaffoldArtifact:
        if self.system is System.REPOSITORY:
            if self.path is None or self.shape is None or self.page is not None:
                raise ValueError(f"{self.id}: a repository artifact has a path and a shape")
            if self.path.startswith("/") or ".." in self.path.split("/"):
                raise ValueError(f"{self.id}: the path is relative and never leaves the tree")
        elif self.page is None or self.path is not None or self.shape is not None:
            raise ValueError(f"{self.id}: a knowledge artifact has a page and no path")
        return self

    @property
    def created_at(self) -> str | None:
        """The path furnishing creates in the repository: the file itself, or the template's
        own name inside the directory. None for a page."""
        if self.system is not System.REPOSITORY or self.path is None:
            return None
        if self.shape is Shape.FILE:
            return self.path
        return f"{self.path.rstrip('/')}/{self.template.rsplit('/', 1)[-1]}"


class Scaffold(Value):
    """`scaffold.yaml`, parsed, with the texts of its templates."""

    name: str = Field(min_length=1)
    """The skill's name."""
    work: str = Field(min_length=1, max_length=64)
    """The kind of work, a word of the scaffold's own: development, analysis, …"""
    artifacts: tuple[ScaffoldArtifact, ...] = Field(min_length=1)
    templates: dict[str, str]
    """The text of every template an artifact names, by its relative path."""

    @model_validator(mode="after")
    def _unique(self) -> Scaffold:
        ids = [a.id for a in self.artifacts]
        if len(set(ids)) != len(ids):
            raise ValueError("every artifact of a scaffold has an identifier of its own")
        for artifact in self.artifacts:
            if artifact.template not in self.templates:
                raise ValueError(f"{artifact.id}: no template {artifact.template!r}")
        return self


class ArtifactState(StrEnum):
    PRESENT = "present"
    MISSING = "missing"
    UNMAINTAINED = "unmaintained"
    UNREAD = "unread"


class Observed(Value):
    """What one reading found of one artifact: whether it is there and when it last changed.
    `read` False: its system could not be read, and nothing else is known."""

    read: bool = True
    present: bool = False
    changed_at: datetime | None = None
    reason: str | None = None
    """Why it could not be read."""


class ArtifactFinding(Value):
    artifact: str
    title: str
    system: System
    state: ArtifactState
    changed_at: datetime | None = None
    stale_days: int | None = None
    """For an unmaintained artifact: by how many whole days the project moved on past it."""
    reason: str | None = None


class ProjectCheck(Value):
    """What a check of one project against its scaffold found (ADR-0307 §3)."""

    scaffold: str
    """The scaffold version checked against, `<name>@<version>`."""
    stage: str
    """Its stage in the lifecycle when it was read."""
    commit: str | None = None
    """The commit the repository was read at."""
    newest: datetime | None = None
    """The project's newest change: the latest of the commit's date and a page's change."""
    findings: tuple[ArtifactFinding, ...]

    def of(self, state: ArtifactState) -> tuple[ArtifactFinding, ...]:
        return tuple(f for f in self.findings if f.state is state)
