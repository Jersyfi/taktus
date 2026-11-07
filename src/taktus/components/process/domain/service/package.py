"""A process version as one package of plain files that a person reads without Taktus (UC-8.9,
ADR-0285). A pure function, no I/O.

The package holds everything that defines the process:

- `process.json` — the version as its document: steps, methods, work, triggers, inputs, limits,
  evaluation, autonomy, takeover instructions. It is what Taktus registers.
- `process.bpmn` — the same version as a BPMN 2.0 model (ADR-0168).
- `prompts/<step>.md` — the system text and prompt of every step on a language model.
- `instructions.md` — how a person runs the process without Taktus (ADR-0180).
- `configuration.json` — what an instance must provide: the model purposes, the capabilities and
  operations, the worker capabilities, and every credential by its parameter, never a value.
- `skills/<name>/...` — every skill a step uses, as its `SKILL.md` directory (ADR-0113).
- `README.md` — what each file is.
- `manifest.json` — every other file with its SHA-256, so that a reader can check the package.

The same version and the same skills give the same bytes.
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from collections.abc import Mapping
from typing import Any

from taktus.components.process.domain.model.process import ProcessVersion
from taktus.components.process.domain.service.interchange import export as bpmn_export

FIXED_TIME = (2026, 1, 1, 0, 0, 0)
"""Every entry of the archive carries this time, so that the bytes depend on the content only."""


def files_of(
    version: ProcessVersion, skills: Mapping[str, Mapping[str, bytes]]
) -> dict[str, bytes]:
    """Every file of the package, by its path. `skills` holds each used skill's directory, by
    the skill's name; a used skill missing there is named in the README and the manifest."""
    files: dict[str, bytes] = {
        "process.json": _json(version.document()),
        "process.bpmn": bpmn_export(version),
        "configuration.json": _json(configuration(version)),
        "instructions.md": instructions(version).encode("utf-8"),
    }
    for step_id, text in prompts(version).items():
        files[f"prompts/{step_id}.md"] = text.encode("utf-8")
    used = version.skills_used()
    missing = sorted(name for name in used if name not in skills)
    for name in sorted(used):
        for path, content in sorted(skills.get(name, {}).items()):
            files[f"skills/{name}/{path}"] = content
    files["README.md"] = readme(version, missing).encode("utf-8")
    files["manifest.json"] = _json(
        {
            "process": version.ref,
            "files": {path: _sha256(content) for path, content in sorted(files.items())},
            "missing_skills": missing,
        }
    )
    return files


def archive(files: Mapping[str, bytes]) -> bytes:
    """The files as one ZIP archive, in path order, each with the same fixed time."""
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as written:
        for path, content in sorted(files.items()):
            entry = zipfile.ZipInfo(path, date_time=FIXED_TIME)
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o644 << 16
            written.writestr(entry, content)
    return out.getvalue()


def prompts(version: ProcessVersion) -> dict[str, str]:
    """The system text and prompt of every step whose work names a prompt, by step."""
    found: dict[str, str] = {}
    for step in version.ordered():
        work = version.work.get(step.id) or {}
        prompt = work.get("prompt")
        if not isinstance(prompt, str):
            continue
        lines = [f"# Step `{step.id}`", ""]
        purpose = work.get("purpose")
        if isinstance(purpose, str):
            lines += [f"Model purpose: `{purpose}`", ""]
        system = work.get("system")
        if isinstance(system, str) and system.strip():
            lines += ["## System", "", system.strip(), ""]
        lines += ["## Prompt", "", prompt.strip(), ""]
        found[step.id] = "\n".join(lines)
    return found


def configuration(version: ProcessVersion) -> dict[str, Any]:
    """What an instance must provide to run the version, named by capability (ADR-0003)."""
    purposes: set[str] = set()
    operations: set[str] = set()
    requires: set[str] = set()
    credentials: set[str] = set()
    for step in version.steps:
        work = version.work.get(step.id) or {}
        if isinstance(work.get("purpose"), str):
            purposes.add(work["purpose"])
        if isinstance(work.get("operation"), str):
            operations.add(work["operation"])
        requires.update(str(c) for c in step.requires or ())
        for credential in work.get("credentials") or ():
            if isinstance(credential, Mapping) and isinstance(credential.get("name"), str):
                credentials.add(credential["name"])
    return {
        "model_purposes": sorted(purposes),
        "connector_operations": sorted(operations),
        "capabilities": sorted(requires),
        "credential_parameters": sorted(credentials),
        "inputs": {name: given.document() for name, given in sorted(version.inputs.items())},
        "limits": None if version.limits is None else dict(version.limits),
    }


def instructions(version: ProcessVersion) -> str:
    """The takeover instructions as a person reads them, in the order the steps run."""
    lines = [f"# How to run {version.name} without Taktus", ""]
    taken = version.takeover
    if taken is None:
        lines += ["This version was stored before takeover instructions were required.", ""]
        return "\n".join(lines)
    lines += [taken.sequence.strip(), ""]
    for step in version.ordered():
        entry = taken.steps.get(step.id)
        if entry is None:
            continue
        lines += [
            f"## Step `{step.id}`",
            "",
            f"- **Where:** {entry.system}",
            f"- **What to do:** {entry.do}",
            f"- **What it needs to know:** {entry.expertise}",
            f"- **Done when:** {entry.done}",
        ]
        lines += [f"- **Credential `{c.parameter}`:** {c.where}" for c in entry.credentials]
        lines.append("")
    return "\n".join(lines)


def readme(version: ProcessVersion, missing: list[str]) -> str:
    lines = [
        f"# {version.name} — `{version.ref}`",
        "",
        "Everything that defines this process, in open formats. Nothing here needs Taktus to be",
        "read.",
        "",
        "| File | What it is | Format |",
        "|---|---|---|",
        "| `process.json` | the version: steps, methods, work, triggers, inputs, limits, "
        "evaluation, autonomy | JSON |",
        "| `process.bpmn` | the same version as a process model | BPMN 2.0 XML |",
        "| `prompts/<step>.md` | the system text and prompt of each step on a language model "
        "| Markdown |",
        "| `instructions.md` | how a person runs the process without Taktus | Markdown |",
        "| `configuration.json` | the model purposes, capabilities, operations and credential "
        "parameters an instance provides | JSON |",
        "| `skills/<name>/` | each skill a step uses | SKILL.md directory |",
        "| `manifest.json` | the SHA-256 of every other file | JSON |",
        "",
        "Credentials are named by their parameter. No value is in this package.",
        "",
    ]
    if missing:
        lines += [
            "Skills a step uses that are not in this package, because no version of them is in "
            f"production: {', '.join(missing)}.",
            "",
        ]
    return "\n".join(lines)


def _json(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _sha256(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()
