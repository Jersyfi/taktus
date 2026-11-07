"""Domain blueprints read from their files, admitted, instantiated and exported (ADR-0263,
UC-15.1).

- **Read from a directory.** A blueprint is a directory holding `blueprint.yaml`; the bundles
  it names with `bundle:` are files below that directory. Each bundle is held to the checks
  registration applies to a bundle on its own (`parse_bundle`), and every operation it names
  gives a capability: every segment of the operation but the last. The catalog component's rule
  admits the blueprint from what each bundle came to, or refuses it with every finding.
- **Instantiated through the catalog component.** `DomainInstances` keeps the dialogue. The
  ports it needs are answered here: a proposal through `Proposals.propose`, under a version the
  process has neither registered nor been proposed under; an identity the identity component
  knows; the adapters that declare a capability, from the release's list of connectors and the
  connectors the instance is configured with.
- **Exported as plain files.** The blueprint's file and the bundle files it names, copied.

This is wiring: it reads files and joins the catalog, process and identity components, which
only the composition root may do (`composition/README.md`).
"""

from __future__ import annotations

import hashlib
import shutil
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from taktus.components.catalog.application.service import DomainInstances
from taktus.components.catalog.domain.model.blueprint import (
    Admitted,
    BlueprintAdmission,
    BundleFacts,
    BundleFile,
    DomainFigures,
    DomainInstance,
)
from taktus.components.catalog.domain.service import blueprints as rules
from taktus.components.catalog.ports.domains import Refused
from taktus.components.identity.application.service import IdentityDirectory
from taktus.components.process.application.service.proposals import (
    ProposalError,
    Proposals,
    Propose,
)
from taktus.components.process.application.service.register_version import parse_bundle
from taktus.components.process.domain.model import InvalidProcess, ProcessVersion
from taktus.components.process.domain.service.bundle import next_version
from taktus.components.run.domain.model import Run
from taktus.composition.shipped import load
from taktus.ports.persistence import Repository, Tenant, UnitOfWork

BLUEPRINT = "blueprint.yaml"


@dataclass(frozen=True)
class Read:
    """A blueprint directory as read: the admission, and the admitted blueprint with its
    bundles where it was admitted."""

    directory: Path
    admission: BlueprintAdmission
    admitted: Admitted | None


def read(directory: Path) -> Read:
    """The blueprint in the directory, admitted or refused with every finding."""
    path = directory / BLUEPRINT
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        return Read(directory, BlueprintAdmission(findings=(f"{path}: {error}",)), None)
    files: dict[str, tuple[dict[str, Any], str]] = {}

    def facts_of(relative: str) -> BundleFacts:
        found, facts = _bundle(directory, relative)
        if found is not None:
            files[relative] = found
        return facts

    admission = rules.admit(document, facts_of)
    if not admission.admitted or admission.blueprint is None:
        return Read(directory, admission, None)
    bundles = {
        p.id: BundleFile(content=files[p.bundle][0], digest=files[p.bundle][1])
        for p in admission.blueprint.processes
        if p.bundle is not None
    }
    return Read(directory, admission, Admitted(blueprint=admission.blueprint, bundles=bundles))


def read_all(root: Path) -> list[Read]:
    """Every blueprint directory below the root, by name."""
    if not root.is_dir():
        return []
    return [read(p) for p in sorted(root.iterdir()) if (p / BLUEPRINT).is_file()]


def admitted(directory: Path) -> Admitted:
    """The admitted blueprint of the directory; ValueError with every finding otherwise."""
    found = read(directory)
    if found.admitted is None:
        raise ValueError(
            f"the blueprint in {directory} does not enter the catalogue: "
            + "; ".join(found.admission.findings)
        )
    return found.admitted


def export(directory: Path, target: Path) -> list[Path]:
    """The admitted blueprint's file and the bundles it names, copied below the target as plain
    files a person reads without Taktus. The written files, in order."""
    blueprint = admitted(directory).blueprint
    names = [BLUEPRINT, *(p.bundle for p in blueprint.processes if p.bundle is not None)]
    written: list[Path] = []
    for name in dict.fromkeys(names):
        destination = target / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(directory / name, destination)
        written.append(destination)
    return written


def _bundle(
    directory: Path, relative: str
) -> tuple[tuple[dict[str, Any], str] | None, BundleFacts]:
    root = directory.resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        return None, BundleFacts(findings=("no such file below the blueprint's directory",))
    try:
        content = path.read_bytes()
        document = yaml.safe_load(content)
    except (OSError, yaml.YAMLError) as error:
        return None, BundleFacts(findings=(f"unreadable: {error}",))
    if not isinstance(document, dict):
        return None, BundleFacts(findings=("the bundle is not a mapping",))
    try:
        version = parse_bundle(document)
    except InvalidProcess as error:
        return None, BundleFacts(findings=error.findings)
    digest = "sha256:" + hashlib.sha256(content).hexdigest()
    return (document, digest), BundleFacts(
        process=version.process_id,
        version=version.version,
        level=version.autonomy_level,
        reason=" ".join(version.autonomy.reason.split()),
        capabilities=tuple(sorted({o.rsplit(".", 1)[0] for o in _operations(document)})),
    )


def _operations(value: Any) -> Iterator[str]:
    """Every operation the document names, wherever it names one: a step's work, a wait, a
    trigger's list."""
    if isinstance(value, Mapping):
        for key, inner in value.items():
            if key == "operation" and isinstance(inner, str) and "." in inner:
                yield inner
            else:
                yield from _operations(inner)
    elif isinstance(value, list):
        for inner in value:
            yield from _operations(inner)


class ProposalsOfProcesses:
    """`ProcessProposals` answered by the process component."""

    def __init__(
        self, proposals: Proposals, versions: Repository[ProcessVersion], work: UnitOfWork
    ) -> None:
        self._proposals = proposals
        self._versions = versions
        self._work = work

    async def propose(
        self, tenant: Tenant, process_id: str, bundle: Mapping[str, Any], by: str, request: str
    ) -> tuple[str, str]:
        async with self._work.transaction(tenant):
            registered = [
                v.version for v in await self._versions.list(tenant) if v.process_id == process_id
            ]
        proposed = [p.version for p in await self._proposals.of_process(tenant, process_id)]
        taken = [*registered, *proposed]
        chosen = dict(bundle)
        if str(chosen.get("version")) in taken:
            chosen["version"] = next_version(taken)
        try:
            proposal = await self._proposals.propose(
                Propose(tenant=tenant, process_id=process_id, bundle=chosen, by=by, request=request)
            )
        except InvalidProcess as error:
            raise Refused(error.findings) from error
        except ProposalError as error:
            raise Refused((str(error),)) from error
        return proposal.id, proposal.version


class KnownPeople:
    """`People` answered by the identity component."""

    def __init__(self, identities: IdentityDirectory) -> None:
        self._identities = identities

    async def known(self, tenant: Tenant, identity: str) -> bool:
        return await self._identities.identity(tenant, identity) is not None


class DeclaredAdapters:
    """`Adapters` answered from what declares each capability: the release's connectors, as
    `connector.<name>`, and any the caller adds by adapter identifier."""

    def __init__(self, declared: Mapping[str, tuple[str, ...]]) -> None:
        self._by: dict[str, list[str]] = {}
        for adapter, capabilities in declared.items():
            for capability in capabilities:
                self._by.setdefault(capability, []).append(adapter)

    @classmethod
    def shipped(cls, also: Mapping[str, tuple[str, ...]] | None = None) -> DeclaredAdapters:
        declared = {f"connector.{c.name}": tuple(c.capabilities) for c in load().connectors}
        return cls({**declared, **(also or {})})

    def declaring(self, capability: str) -> tuple[str, ...]:
        return tuple(sorted(self._by.get(capability, ())))


class DomainBlueprints:
    """What `taktusctl domain` acts through: the instances, and the runs counted per domain."""

    def __init__(self, instances: DomainInstances, runs: Repository[Run], work: UnitOfWork) -> None:
        self.instances = instances
        self._runs = runs
        self._work = work

    def read(self, directory: Path) -> Read:
        return read(directory)

    def admitted(self, directory: Path) -> Admitted:
        return admitted(directory)

    def export(self, directory: Path, target: Path) -> list[Path]:
        return export(directory, target)

    async def figures(self, tenant: Tenant, instance: DomainInstance) -> DomainFigures:
        async with self._work.transaction(tenant):
            runs = list(await self._runs.list(tenant))
        return rules.figures(
            instance,
            ((r.process_version.rpartition("@")[0], str(r.state), r.rehearsal) for r in runs),
        )
