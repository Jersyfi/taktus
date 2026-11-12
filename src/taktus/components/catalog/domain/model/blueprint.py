"""A domain blueprint, and a domain an organisation instantiated from it (ADR-0263, UC-15.1).

A **blueprint** is one department of a business as files: its processes, the connector
capabilities they need, the usual autonomy level of each with its reason, the criteria its value
balance keeps, and the acts that stay with a person. It is admitted only complete
(`domain/service/blueprints.py`); `DomainBlueprint` is what an admitted one says.

A **domain instance** is the record of the dialogue in which an organisation instantiated a
blueprint: the answers to its questions, the processes left out, the named owner, and the
proposals it made. It is the organisation's own: a later version of the blueprint is offered to
it, never applied.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from taktus.shared.v1 import Value

NAME = r"^[a-z0-9][a-z0-9-]*$"
CAPABILITY = r"^[a-z][a-z0-9]*(\.[a-z][a-z0-9_]*)+$"
"""A capability as the adapter obligation names it: `area.object`, never a product."""
HIGHEST_START = 2
"""The highest autonomy level a process of an instance starts at (UC-15.1 §2)."""


class BundleFacts(Value):
    """What one bundle file came to under the checks registration applies to a bundle on its
    own, as the composition root hands it to the admission. `findings` empty: it passed."""

    process: str | None = None
    """The process the bundle is a version of; None where it could not be read."""
    version: str | None = None
    level: int | None = None
    reason: str = ""
    capabilities: tuple[str, ...] = ()
    """Every connector capability an operation of the bundle calls."""
    findings: tuple[str, ...] = ()


class BlueprintProcess(Value):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    level: int = Field(ge=1, le=4)
    """The usual autonomy level (ADR-0026)."""
    reason: str = Field(min_length=1)
    bundle: str | None = None
    """The bundle file, relative to the blueprint's directory; None: described, not built."""
    process: str | None = None
    """The bundle's process identifier, where it names a bundle."""
    capabilities: tuple[str, ...] = ()


class DomainBlueprint(Value):
    id: str = Field(pattern=NAME)
    name: str = Field(min_length=1)
    domain: str = Field(min_length=1)
    version: str = Field(min_length=1)
    connectors: tuple[str, ...] = ()
    """The connector capabilities the domain needs."""
    workers: tuple[str, ...] = ()
    models: tuple[str, ...] = ()
    """The purposes of the models it asks for."""
    strategic: tuple[str, ...] = ()
    legal: tuple[str, ...] = ()
    cost: tuple[str, ...] = Field(min_length=1)
    benefit: tuple[str, ...] = Field(min_length=1)
    processes: tuple[BlueprintProcess, ...] = Field(min_length=1)

    def process(self, process_id: str) -> BlueprintProcess | None:
        return next((p for p in self.processes if p.id == process_id), None)

    def alternatives(self) -> tuple[tuple[str, ...], ...]:
        """The sets of processes whose bundles are versions of the same process."""
        by: dict[str, list[str]] = {}
        for p in self.processes:
            if p.process is not None:
                by.setdefault(p.process, []).append(p.id)
        return tuple(tuple(ids) for ids in by.values() if len(ids) > 1)


class BundleFile(Value):
    """One bundle of an admitted blueprint, as read: its document and the digest of its bytes."""

    content: Mapping[str, Any]
    """The bundle's document, as its file holds it."""
    digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class Admitted(Value):
    """An admitted blueprint with the bundles it names, by the blueprint's process id."""

    blueprint: DomainBlueprint
    bundles: Mapping[str, BundleFile] = Field(default_factory=dict)


class BlueprintAdmission(Value):
    """What the admission of one blueprint came to: the blueprint, or every reason it is not."""

    blueprint: DomainBlueprint | None = None
    findings: tuple[str, ...] = ()

    @property
    def admitted(self) -> bool:
        return self.blueprint is not None and not self.findings


class Binding(Value):
    """The answer to one capability's question: the adapter that serves it, or none."""

    capability: str = Field(pattern=CAPABILITY)
    adapter: str | None = Field(default=None, min_length=1)
    """None: the organisation has no such tool; the steps that need it fall back as declared."""
    by: str = Field(min_length=1)
    at: datetime


class ProposedProcess(Value):
    process: str = Field(min_length=1)
    """The blueprint's process identifier."""
    process_id: str = Field(min_length=1)
    """The bundle's process identifier, as the tenant registers it."""
    version: str = Field(min_length=1)
    proposal: str = Field(min_length=1)
    level: int = Field(ge=1, le=HIGHEST_START)
    digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    """The digest of the bundle file the proposal was made from."""
    blueprint_version: str = Field(min_length=1)


JURISDICTION = r"^[A-Z]{2}(-[A-Z0-9]{1,3})?$"
"""An ISO 3166 code, a country or a region, as the governance domain takes it (ADR-0259)."""


class Question(Value):
    """One open question of an instance's dialogue."""

    kind: Literal["capability", "choice", "owner", "jurisdiction"]
    subject: str
    """The capability; the alternatives, comma-separated; `owner`; or `jurisdiction`."""
    asks: str
    options: tuple[str, ...] = ()


class DomainInstance(Value):
    """One domain a tenant instantiated from a blueprint, stored under its own identifier."""

    id: str = Field(min_length=1)
    tenant: str = Field(min_length=1)
    created_at: datetime
    blueprint: str = Field(pattern=NAME)
    blueprint_version: str = Field(min_length=1)
    """The version it was instantiated from; a later one is offered, never applied."""
    domain: str = Field(min_length=1)
    started_by: str = Field(min_length=1)
    bindings: tuple[Binding, ...] = ()
    left_out: tuple[str, ...] = ()
    owner: str | None = Field(default=None, min_length=1)
    jurisdiction: str | None = Field(default=None, pattern=JURISDICTION)
    """The country or region whose law the domain's binding acts fall under, as ISO 3166: what
    the governance domain needs (ADR-0259, ADR-0289)."""
    proposed: tuple[ProposedProcess, ...] = ()
    plan: str | None = Field(default=None, min_length=1)
    """The plan draft the instance is worked out in (ADR-0289); None for one made before."""
    domain_record: str | None = Field(default=None, min_length=1)
    """The governance domain its commissioning instantiated or joined; None until then."""

    def binding(self, capability: str) -> Binding | None:
        return next((b for b in self.bindings if b.capability == capability), None)

    def proposal_of(self, process: str) -> ProposedProcess | None:
        """The latest proposal made for a blueprint process."""
        found = [p for p in self.proposed if p.process == process]
        return found[-1] if found else None


class Offer(Value):
    """What a later version of a blueprint came to for an instance: proposals, never changes."""

    instance: str
    blueprint_version: str
    proposed: tuple[ProposedProcess, ...] = ()
    new: tuple[str, ...] = ()
    """Processes new in the later version: named, not proposed."""


class ProcessFigures(Value):
    process_id: str
    runs: int = 0
    by_state: Mapping[str, int] = Field(default_factory=dict)


class DomainFigures(Value):
    """The runs of an instance's processes, counted per domain (UC-15.1 §2)."""

    instance: str
    domain: str
    runs: int = 0
    processes: tuple[ProcessFigures, ...] = ()
