"""A process version leaves Taktus as one package of plain files (UC-8.9, ADR-0285), over the
memory stores.

The package is read here the way a person without Taktus would read it: as a ZIP archive, with
the standard library's JSON and XML readers, and a SHA-256 per file.
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from xml.etree import ElementTree

import pytest

from taktus.components.process.application.service.packages import (
    ProcessPackages,
    UnknownVersion,
)
from taktus.components.process.domain.model import ProcessVersion
from taktus.components.process.domain.service import package

from .test_evaluations import KIND, TENANT, WHO, World

SKILL = b"---\nname: tone\ndescription: How a reply sounds.\n---\n\nWrite warmly and briefly.\n"


async def packages(world: World) -> ProcessPackages:
    async def skills(tenant: str, version: ProcessVersion) -> dict[str, dict[str, bytes]]:
        return {"tone": {"SKILL.md": SKILL}}

    return ProcessPackages(
        world.processes, world.versions, ledger=world.ledger, work=world.persistence, skills=skills
    )


async def test_everything_that_defines_a_process_leaves_as_one_package_read_without_taktus() -> (
    None
):
    world = await World().setup()
    written = await (await packages(world)).export(TENANT, "replies", by=WHO)
    with zipfile.ZipFile(io.BytesIO(written)) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    assert set(files) == {
        "README.md",
        "configuration.json",
        "instructions.md",
        "manifest.json",
        "process.bpmn",
        "process.json",
        "prompts/draft.md",
    }
    # The definition, as JSON; the same version is read back from it.
    definition = json.loads(files["process.json"])
    assert definition["process_id"] == "replies" and definition["version"] == "1"
    assert ProcessVersion.model_validate(definition).ref == "replies@1"
    # The model, as BPMN 2.0 XML.
    root = ElementTree.fromstring(files["process.bpmn"])  # noqa: S314 — our own output
    assert root.tag.endswith("definitions")
    # The prompt, the instructions, what an instance provides.
    assert KIND in files["prompts/draft.md"].decode()
    assert "Model purpose: `drafting`" in files["prompts/draft.md"].decode()
    takeover = definition["takeover"]
    assert takeover["sequence"].strip() in files["instructions.md"].decode()
    configuration = json.loads(files["configuration.json"])
    assert configuration["model_purposes"] == ["drafting"]
    assert set(configuration["inputs"]) == {"message", "mailbox"}
    # Every file is named in the manifest with its digest.
    manifest = json.loads(files["manifest.json"])
    for name, content in files.items():
        if name != "manifest.json":
            assert manifest["files"][name] == "sha256:" + hashlib.sha256(content).hexdigest()
    # The same version gives the same bytes; the export is recorded with its digest.
    again = await (await packages(world)).export(TENANT, "replies", "1", by=WHO)
    assert again == written
    async with world.persistence.transaction(TENANT):
        entries = [e for e in await world.ledger.entries(TENANT) if e.kind == "process.exported"]
    assert len(entries) == 2
    assert entries[0].refs.actor == WHO and entries[0].refs.process_version == "replies@1"
    assert entries[0].content_digest == "sha256:" + hashlib.sha256(written).hexdigest()


async def test_a_skill_a_step_uses_travels_in_its_open_format_and_a_missing_one_is_named() -> None:
    world = await World().setup()
    async with world.persistence.transaction(TENANT):
        version = await world.versions.get(TENANT, "replies@1")
    assert version is not None
    work = {**version.work, "draft": {**version.work["draft"], "skills": ["tone", "legal"]}}
    used = version.model_copy(update={"work": work})
    files = package.files_of(used, {"tone": {"SKILL.md": SKILL}})
    assert files["skills/tone/SKILL.md"] == SKILL
    assert json.loads(files["manifest.json"])["missing_skills"] == ["legal"]
    assert "legal" in files["README.md"].decode()


async def test_an_unknown_process_or_version_is_refused() -> None:
    world = await World().setup()
    exports = await packages(world)
    with pytest.raises(UnknownVersion):
        await exports.export(TENANT, "absent", by=WHO)
    with pytest.raises(UnknownVersion):
        await exports.export(TENANT, "replies", "9", by=WHO)
