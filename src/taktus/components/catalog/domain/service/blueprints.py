"""The rules of domain blueprints (ADR-0263, UC-15.1): when a blueprint is admitted, which
questions an instance still has open, at which level a process of it starts, and what its runs
count to.

Every rule is a function of the data it is handed. None reads a file or calls anything: the
composition root reads the blueprint's files and hands over what each bundle came to under the
checks of registration (`BundleFacts`).
"""

from __future__ import annotations

import copy
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any

from taktus.components.catalog.domain.model.blueprint import (
    CAPABILITY,
    HIGHEST_START,
    NAME,
    BlueprintAdmission,
    BlueprintProcess,
    BundleFacts,
    DomainBlueprint,
    DomainFigures,
    DomainInstance,
    ProcessFigures,
    Question,
)

KIND = "Blueprint"
OWNER = "owner"
JURISDICTION = "jurisdiction"


def admit(document: Any, facts_of: Callable[[str], BundleFacts]) -> BlueprintAdmission:
    """The blueprint the document describes, or every reason it does not enter the catalogue.
    `facts_of` answers a bundle path the blueprint names with what the bundle came to."""
    if not isinstance(document, Mapping):
        return BlueprintAdmission(findings=("a blueprint is a mapping",))
    findings: list[str] = []
    if document.get("kind") != KIND:
        findings.append(f"its kind is {document.get('kind')!r}, not {KIND!r}")
    metadata = _mapping(document.get("metadata"))
    for key in ("id", "name", "domain", "version"):
        if not _text(metadata.get(key)):
            findings.append(f"its metadata names no {key}")
    blueprint_id = str(metadata.get("id") or "")
    if blueprint_id and re.fullmatch(NAME, blueprint_id) is None:
        findings.append(f"its id {blueprint_id!r} is not a lowercase name")

    requires = _mapping(document.get("requires"))
    connectors = _named(requires.get("connectors"), "capability")
    for capability in connectors:
        if re.fullmatch(CAPABILITY, capability) is None:
            findings.append(f"the capability {capability!r} is not named as area.object")
    workers = _named(requires.get("workers"), "capability")
    models = _named(requires.get("models"), "purpose")

    anchors = _mapping(document.get("anchors"))
    strategic = _texts(anchors.get("strategic"))
    legal = _texts(anchors.get("legal"))
    if not strategic and not legal:
        findings.append("it names no act that stays with a person: no strategic or legal anchor")

    criteria = _mapping(document.get("value_criteria"))
    cost, benefit = _texts(criteria.get("cost")), _texts(criteria.get("benefit"))
    if not cost:
        findings.append("its value criteria name no cost")
    if not benefit:
        findings.append("its value criteria name no benefit")

    processes: list[BlueprintProcess] = []
    raw = document.get("processes")
    if not isinstance(raw, list) or not raw:
        findings.append("it names no process")
        raw = []
    seen: set[str] = set()
    for index, entry in enumerate(raw):
        found, problems = _process(index, entry, facts_of, set(connectors))
        findings.extend(problems)
        if found is None:
            continue
        if found.id in seen:
            findings.append(f"the process {found.id} is named twice")
        seen.add(found.id)
        processes.append(found)
    if findings:
        return BlueprintAdmission(findings=tuple(findings))
    return BlueprintAdmission(
        blueprint=DomainBlueprint(
            id=blueprint_id,
            name=str(metadata["name"]),
            domain=str(metadata["domain"]),
            version=str(metadata["version"]),
            connectors=connectors,
            workers=workers,
            models=models,
            strategic=strategic,
            legal=legal,
            cost=cost,
            benefit=benefit,
            processes=tuple(processes),
        )
    )


def _process(
    index: int, entry: Any, facts_of: Callable[[str], BundleFacts], required: set[str]
) -> tuple[BlueprintProcess | None, list[str]]:
    if not isinstance(entry, Mapping):
        return None, [f"the process at {index} is not a mapping"]
    process_id = str(entry.get("id") or "")
    label = process_id or f"at {index}"
    problems: list[str] = []
    if not process_id:
        problems.append(f"the process {label} has no id")
    if not _text(entry.get("name")):
        problems.append(f"the process {label} has no name")
    autonomy = _mapping(entry.get("autonomy"))
    stated = autonomy.get("level")
    level: int | None = stated if isinstance(stated, int) and not isinstance(stated, bool) else None
    reason = " ".join(str(autonomy.get("reason") or "").split())
    bundle = entry.get("bundle")
    process: str | None = None
    capabilities: tuple[str, ...] = ()
    if bundle is not None:
        facts = facts_of(str(bundle))
        if facts.findings:
            problems.extend(f"the process {label}'s bundle {bundle}: {f}" for f in facts.findings)
        else:
            if level is not None and level != facts.level:
                problems.append(
                    f"the process {label} states level {level}, and its bundle {bundle} level "
                    f"{facts.level}"
                )
            level, reason = facts.level, facts.reason or reason
            process, capabilities = facts.process, facts.capabilities
            missing = sorted(set(capabilities) - required)
            if missing:
                problems.append(
                    f"the process {label}'s bundle calls {', '.join(missing)}, which "
                    "requires.connectors does not name"
                )
    if level is None or not 1 <= level <= 4:
        problems.append(f"the process {label} has no usual autonomy level from 1 to 4")
    if not reason:
        problems.append(f"the process {label} gives no reason for its autonomy level")
    if problems or level is None:
        return None, problems
    return (
        BlueprintProcess(
            id=process_id,
            name=str(entry["name"]),
            level=level,
            reason=reason,
            bundle=None if bundle is None else str(bundle),
            process=process,
            capabilities=capabilities,
        ),
        [],
    )


def questions(
    blueprint: DomainBlueprint,
    instance: DomainInstance,
    options: Mapping[str, Sequence[str]],
) -> tuple[Question, ...]:
    """The questions the instance still has open. `options` are the adapters that declare each
    capability."""
    found: list[Question] = []
    for capability in blueprint.connectors:
        if instance.binding(capability) is None:
            found.append(
                Question(
                    kind="capability",
                    subject=capability,
                    asks=f"Which of your tools serves {capability}? Answer `none` if none does.",
                    options=tuple(options.get(capability, ())),
                )
            )
    for alternatives in blueprint.alternatives():
        kept = [p for p in alternatives if p not in instance.left_out]
        if len(kept) > 1:
            found.append(
                Question(
                    kind="choice",
                    subject=",".join(kept),
                    asks=f"Keep one of {', '.join(kept)}: they are versions of the same process.",
                    options=tuple(kept),
                )
            )
    if instance.owner is None:
        found.append(
            Question(
                kind="owner",
                subject=OWNER,
                asks="Who owns this domain? Name one identity of the tenant.",
            )
        )
    if instance.jurisdiction is None:
        found.append(
            Question(
                kind="jurisdiction",
                subject=JURISDICTION,
                asks="Under which country's law are the domain's binding acts? Name its "
                "ISO 3166 code, as DE or DE-BY.",
            )
        )
    return tuple(found)


def answer_refusal(
    blueprint: DomainBlueprint, capability: str, adapter: str | None, declared: Iterable[str]
) -> str | None:
    """Why the answer cannot be taken; None where it can. `declared` are the adapters that
    declare the capability."""
    if capability not in blueprint.connectors:
        return f"the blueprint {blueprint.id} asks for no capability {capability!r}"
    if adapter is not None and adapter not in set(declared):
        return f"{adapter} declares no capability {capability}"
    return None


def leave_out_refusal(blueprint: DomainBlueprint, processes: Iterable[str]) -> str | None:
    unknown = sorted(p for p in processes if blueprint.process(p) is None)
    if unknown:
        return f"the blueprint {blueprint.id} has no process {', '.join(unknown)}"
    return None


def start_level(usual: int) -> int:
    """The level a process of an instance starts at: its usual one, at most 2."""
    return min(usual, HIGHEST_START)


def starting(
    document: Mapping[str, Any], process: BlueprintProcess, blueprint: DomainBlueprint
) -> dict[str, Any]:
    """The bundle as the instance proposes it: at its starting level, its reason naming the
    usual level, so that the way up stays visible."""
    changed = copy.deepcopy(dict(document))
    level = start_level(process.level)
    if level == process.level:
        return changed
    autonomy = dict(changed.get("autonomy") or {})
    autonomy["level"] = level
    autonomy["reason"] = (
        f"an instance of the blueprint {blueprint.id} starts it at level {level} (UC-15.1); its "
        f"usual level is {process.level}: {process.reason}"
    )
    if not autonomy.get("toward_next"):
        autonomy["toward_next"] = (
            f"its usual level {process.level}, proposed with its history and approved by a "
            "person (UC-7.1)"
        )
    changed["autonomy"] = autonomy
    return changed


def figures(instance: DomainInstance, runs: Iterable[tuple[str, str, bool]]) -> DomainFigures:
    """The runs of the instance's processes, per process and state. `runs` are (process id,
    state, rehearsal) of the tenant's runs; a rehearsal is not counted."""
    ours = sorted({p.process_id for p in instance.proposed})
    counts: dict[str, dict[str, int]] = {p: {} for p in ours}
    for process_id, state, rehearsal in runs:
        if rehearsal or process_id not in counts:
            continue
        counts[process_id][state] = counts[process_id].get(state, 0) + 1
    per = tuple(
        ProcessFigures(process_id=p, runs=sum(c.values()), by_state=dict(sorted(c.items())))
        for p, c in counts.items()
    )
    return DomainFigures(
        instance=instance.id,
        domain=instance.domain,
        runs=sum(p.runs for p in per),
        processes=per,
    )


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _text(value: Any) -> bool:
    return isinstance(value, (str, int)) and not isinstance(value, bool) and bool(str(value))


def _texts(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(v) for v in value if _text(v))


def _named(value: Any, key: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(v[key]) for v in value if isinstance(v, Mapping) and _text(v.get(key)))
