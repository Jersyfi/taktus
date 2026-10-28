"""A result defect: its impact analysed, the rule's decision, and the remediation plan (UC-4.11,
UC-4.12, ADR-0022, ADR-0023, ADR-0153). Pure functions over provenance records and ledger
entries; they read the records and change nothing.

**Since when.** The records of the defective result's step, in its process, ordered by their
ledger entry, are its series. Walking back from the defective result, the first record whose
way of producing differs from the one before it — another process version, method, model,
prompt, adapter or adapter version — is the cause: the window starts at the result after it.
Where no change is found, the window starts at the earliest result recorded, and is
**unbounded** when that result is the first the chain holds: it may reach before the record.
The window ends at the newest result of the series.

**What is affected.** Every result of the series inside the window, and everything derived from
one of them: the provenance chain read forward, across runs and processes (ADR-0022 §4).

**What has left.** For each affected result, the egress entry that names it or anything derived
from it (`egress.left_the_system`).

**The rule.** Every rule of the tenant whose conditions all hold fires; the verdict is the
strictest of those that fired, `continue` when none did. The same facts give the same decision.

**The plan.** For every affected result in order, a step that produces it again from corrected
inputs inside the system; for every one that has left, an outward correction after it, which
waits for a person. Each step names the system, the record, the value before and after, and how
to tell it is done.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence

from taktus.components.governance.domain.model.defects import (
    SEVERITY,
    Affected,
    Analysis,
    Change,
    Decision,
    Facts,
    Found,
    Kind,
    Plan,
    PlanStep,
    Position,
    Rule,
    Verdict,
)
from taktus.components.governance.domain.model.egress import ResultRef
from taktus.components.governance.domain.service import egress
from taktus.shared.v1 import LedgerEntry, Provenance

SIGNATURE = ("process_version", "method", "model", "prompt", "adapter", "adapter_version")


class NotRecorded(Exception):
    """The defective result has no provenance record: nothing that was not recorded is
    reconstructed (UC-4.11 §2)."""


def process_of(version: str) -> str:
    return version.rsplit("@", 1)[0]


def analyse(
    defect: ResultRef,
    found: Found,
    records: Sequence[Provenance],
    entries: Sequence[LedgerEntry],
) -> Analysis:
    """The impact analysis of a result reported wrong. `NotRecorded` when no record produced it."""
    produced = [r for r in records if r.run_id == defect.run_id and r.step_id == defect.step_id]
    if not produced:
        raise NotRecorded(
            f"step {defect.step_id} of run {defect.run_id} has no provenance record: a result "
            "older than the chain cannot be bounded, and nothing unrecorded is reconstructed"
        )
    origin = max(produced, key=lambda r: r.ledger_seq)
    process = process_of(origin.process_version)
    series = sorted(
        (
            r
            for r in records
            if r.step_id == defect.step_id and process_of(r.process_version) == process
        ),
        key=lambda r: r.ledger_seq,
    )
    at = series.index(origin)
    cause: Change | None = None
    start = 0
    for index in range(at, 0, -1):
        changed = _changed(series[index - 1], series[index])
        if changed is not None:
            cause = changed
            start = index
            break
    window = series[start:]
    unbounded = cause is None and start == 0
    affected: list[Affected] = []
    seen: set[tuple[str, str, str | None, str | None]] = set()
    by_run_step = {(r.run_id, r.step_id): r for r in records}
    for position, record in enumerate(window):
        where = (
            Position.FIRST
            if position == 0
            else Position.LAST
            if position == len(window) - 1
            else Position.INSIDE
        )
        for ref in _results(record):
            for member in egress.closure(ref, records):
                key = (member.run_id, member.step_id, member.artifact_id, member.digest)
                if key in seen:
                    continue
                seen.add(key)
                source = by_run_step.get((member.run_id, member.step_id))
                if source is None:
                    continue
                affected.append(
                    Affected(
                        result=member,
                        process_version=source.process_version,
                        exactness=source.exactness,
                        position=where if member == ref else Position.DERIVED,
                        produced_at=source.recorded_at,
                        readers=_readers(member, records),
                        left=egress.left_the_system(member, records, entries),
                    )
                )
    return Analysis(
        defect=defect,
        found=found,
        process_version=origin.process_version,
        cause=cause,
        unbounded=unbounded,
        window_start=window[0].recorded_at,
        window_end=window[-1].recorded_at,
        window_runs=len({r.run_id for r in window}),
        affected=tuple(affected),
    )


def facts_of(analysis: Analysis, *, legal_downstream: bool, relevance: int | None = None) -> Facts:
    return Facts(
        strictest=analysis.strictest,
        left=bool(analysis.left),
        legal_downstream=legal_downstream,
        window_runs=analysis.window_runs,
        window=analysis.window_end - analysis.window_start,
        relevance=relevance,
    )


def decide(facts: Facts, rules: Sequence[Rule]) -> Decision:
    """The rule's decision over the facts: the strictest verdict of every rule that fired."""
    fired = [rule for rule in rules if _holds(rule, facts)]
    verdict = max((r.then for r in fired), key=SEVERITY.__getitem__, default=Verdict.CONTINUE)
    return Decision(
        verdict=verdict,
        fired=tuple(r.id for r in fired),
        facts=facts,
        thresholds={r.id: _thresholds(r) for r in fired},
    )


def plan(analysis: Analysis, systems: Mapping[int, str] | None = None) -> Plan:
    """The remediation plan: inside first, in the order the results were produced; every
    outward correction after the step that produces its result again. `systems` names, per
    egress entry's sequence number, the system it went to — the connector or the channel —
    where the ledger knows it."""
    systems = systems or {}
    ordered = sorted(analysis.affected, key=lambda a: a.produced_at)
    steps: list[PlanStep] = []
    for affected in ordered:
        produce = len(steps) + 1
        record = _record(affected.result)
        steps.append(
            PlanStep(
                order=produce,
                kind=Kind.INSIDE,
                system="Taktus",
                record=f"{record} of step {affected.result.step_id} in run "
                f"{affected.result.run_id} ({affected.process_version})",
                before=_value(affected.result),
                after=f"the result step {affected.result.step_id} produces again from the "
                "corrected inputs; the wrong result and its provenance record stay as they are",
                done_when=f"a new provenance record of step {affected.result.step_id} names the "
                "corrected inputs, and the incident links it to the wrong one",
                after_steps=_earlier(steps, affected),
            )
        )
        if affected.left is not None:
            went = systems.get(
                affected.left.seq, f"the receiver of ledger entry {affected.left.seq}"
            )
            steps.append(
                PlanStep(
                    order=len(steps) + 1,
                    kind=Kind.OUTWARD,
                    system=went,
                    record=f"what ledger entry {affected.left.seq} ({affected.left.kind}) sent: "
                    f"{_record(affected.left.through)} of step {affected.left.through.step_id} in "
                    f"run {affected.left.through.run_id}",
                    before=f"{went} holds {_value(affected.left.through)}",
                    after=f"{went} holds the result of plan step {produce}",
                    done_when=f"{went} shows the result of plan step {produce}, and whoever made "
                    "the correction has recorded it in the incident, with the role that did it",
                    after_steps=(produce,),
                    atomic=affected.left.kind != "egress.delivery",
                    note=None
                    if affected.left.kind != "egress.delivery"
                    else "A delivered message or file cannot be taken back: the receiver keeps "
                    "the old one while the correction is sent, and holds two until it reads it.",
                )
            )
    return Plan(
        defect=analysis.defect, process_version=analysis.process_version, steps=tuple(steps)
    )


def render(plan: Plan) -> str:
    """The plan as a person carries it out without Taktus: one numbered step per line group,
    with the system, the record, before, after and how to tell it is done."""
    out = [
        f"# Remediation plan — step {plan.defect.step_id} of run {plan.defect.run_id}",
        "",
        f"Process version: {plan.process_version}. Carry out the steps in order. A step marked "
        "*outward* corrects something outside Taktus and is decided by the person of the "
        "correction anchor before it is made, by Taktus or by hand.",
        "",
    ]
    for step in plan.steps:
        waits = (
            f" After step {', '.join(str(n) for n in step.after_steps)}."
            if step.after_steps
            else ""
        )
        out += [
            f"## {step.order}. {'Outward' if step.kind is Kind.OUTWARD else 'Inside'}: "
            f"{step.system}{waits}".rstrip(),
            "",
            f"- System: {step.system}",
            f"- Record: {step.record}",
            f"- Before: {step.before}",
            f"- After: {step.after}",
            f"- Done when: {step.done_when}",
        ]
        if not step.atomic:
            out.append(f"- Not at once: {step.note}")
        out.append("")
    return "\n".join(out)


def _changed(before: Provenance, after: Provenance) -> Change | None:
    for name in SIGNATURE:
        old, new = getattr(before, name), getattr(after, name)
        if old != new:
            return Change(
                field=name,  # type: ignore[arg-type]
                before=None if old is None else str(old),
                after=None if new is None else str(new),
                at_run=after.run_id,
            )
    return None


def _results(record: Provenance) -> list[ResultRef]:
    found = [
        ResultRef(run_id=record.run_id, step_id=record.step_id, artifact_id=a)
        for a in record.outputs
        if a != "result"
    ]
    if record.result_digest is not None:
        found.append(
            ResultRef(run_id=record.run_id, step_id=record.step_id, digest=record.result_digest)
        )
    return found


def _readers(ref: ResultRef, records: Iterable[Provenance]) -> tuple[str, ...]:
    readers: list[str] = []
    for record in records:
        for given in record.inputs:
            if (given.run_id, given.step_id) != (ref.run_id, ref.step_id):
                continue
            if (ref.artifact_id is not None and given.artifact_id == ref.artifact_id) or (
                ref.artifact_id is None and given.digest == ref.digest
            ):
                name = f"{record.process_version}/{record.step_id}"
                if name not in readers:
                    readers.append(name)
    return tuple(readers)


def _holds(rule: Rule, facts: Facts) -> bool:
    when = rule.when
    if when.classes and facts.strictest not in when.classes:
        return False
    if when.left is not None and facts.left is not when.left:
        return False
    if when.legal_downstream is not None and facts.legal_downstream is not when.legal_downstream:
        return False
    if when.window_runs_over is not None and facts.window_runs <= when.window_runs_over:
        return False
    if when.window_over is not None and facts.window <= when.window_over:
        return False
    return when.relevance_at_least is None or (
        facts.relevance is not None and facts.relevance >= when.relevance_at_least
    )


def _thresholds(rule: Rule) -> str:
    given = rule.when.model_dump(exclude_defaults=True, mode="json")
    return ", ".join(f"{k} {v}" for k, v in sorted(given.items()))


def _record(ref: ResultRef) -> str:
    return f"the artifact {ref.artifact_id}" if ref.artifact_id else "the result"


def _value(ref: ResultRef) -> str:
    if ref.artifact_id:
        return f"the artifact {ref.artifact_id} as the run stores it"
    return f"the value of digest {ref.digest}" if ref.digest else "the value the run stores"


def _earlier(steps: Sequence[PlanStep], affected: Affected) -> tuple[int, ...]:
    """The inside steps that produce what this result was derived from: every earlier inside
    step, for a derived result; none for a result of the step itself."""
    if affected.position is not Position.DERIVED:
        return ()
    return tuple(s.order for s in steps if s.kind is Kind.INSIDE)
