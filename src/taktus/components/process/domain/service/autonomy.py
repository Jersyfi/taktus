"""What a raise of an autonomy level is, and when it is admitted (ADR-0026, ADR-0039).

A process's levels live in its autonomy statement: the process's own level and a level per
tool action (`Autonomy.actions`). A version whose statement lets any step run at a higher level
than the version it replaces *raises* a level. Three cases are raises:

- the process's level goes up;
- an action's level goes up;
- an action loses its own entry, and so runs at the process's level, which is higher.

A raise is admitted only with both of what governance.md §1 asks: an explicit approval by a
person, and a demonstrated quality history — as many runs in a row as the replaced version's
`history` names, the most recent ones, each ended without a failure or a result defect. The
number is the replaced version's, so that the version that raises cannot lower the bar it is
measured against. A version that names none admits no raise.

The quality history is read from the ledger, so that it is reproducible: the runs of the
process, rehearsals left out, in the order they began. A run counts once it ended: finished
without a step that failed, it extends the history; escalated, or with a step that failed on
the way, it ends it. A run that halted or waits counts neither way. Result defects are counted
from the runs a caller names; nothing records them yet (UC-4.10, `0.5.0`).

Pure: statements, ledger entries and the approval in, a verdict out.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any, Literal

from pydantic import Field

from taktus.shared.v1 import Autonomy, LedgerEntry, Step, Value

type Refusal = Literal["no_approval", "no_history_named", "history_short"]

CLEAN_STEP_OUTCOMES = frozenset({"succeeded", "rehearsed", "stopped"})
"""What a `step.finished` entry may say without the run counting as failed."""


def actions_used(steps: Sequence[Step], work: Mapping[str, Mapping[str, Any]]) -> set[str]:
    """The tool actions the steps use: the capabilities they require, and the connector
    operations their work calls or waits on, with each operation's capability."""
    used: set[str] = set()
    for step in steps:
        used.update(step.required_capabilities)
        step_work = work.get(step.id) or {}
        for operation in (step_work.get("operation"), _until(step_work).get("operation")):
            if isinstance(operation, str) and "." in operation:
                used.add(operation)
                used.add(operation.rsplit(".", 1)[0])
    return used


def _until(work: Mapping[str, Any]) -> Mapping[str, Any]:
    until = work.get("until")
    return until if isinstance(until, Mapping) else {}


def raises(current: Autonomy, new: Autonomy) -> list[str]:
    """Every level the new statement raises over the current one, in words; empty when none
    rises."""
    found: list[str] = []
    if new.level > current.level:
        found.append(f"the process from level {current.level} to {new.level}")
    for action in sorted(set(current.action_levels) | set(new.action_levels)):
        before, after = current.level_of(action), new.level_of(action)
        if after > before:
            found.append(f"the action {action} from level {before} to {after}")
    return found


class QualityHistory(Value):
    """The runs of a process that ended, as far as the history counts them."""

    process_id: str = Field(min_length=1)
    clean: int = Field(ge=0)
    """How many runs in a row, the most recent ones, ended without a failure or a result
    defect."""
    ended: int = Field(ge=0)
    """How many runs of the process ended at all."""
    last_failed: str | None = None
    """The most recent run that ended with a failure or a result defect, if any."""


def history(
    entries: Iterable[LedgerEntry],
    process_id: str,
    defects: frozenset[str] = frozenset(),
) -> QualityHistory:
    """The quality history of a process from the tenant's ledger. `defects` names the runs a
    result defect was found in."""
    order: list[str] = []
    failed: set[str] = set(defects)
    ended: dict[str, bool] = {}
    for entry in entries:
        run_id = entry.refs.run_id
        version = entry.refs.process_version
        if entry.rehearsal or run_id is None or version is None:
            continue
        if version.split("@", 1)[0] != process_id:
            continue
        if run_id not in order:
            order.append(run_id)
        if entry.kind == "step.finished" and (entry.outcome or "") not in CLEAN_STEP_OUTCOMES:
            failed.add(run_id)
        elif entry.kind == "run.escalated":
            failed.add(run_id)
            ended[run_id] = True
        elif entry.kind == "run.finished":
            ended[run_id] = True
    clean = 0
    last_failed = None
    for run_id in reversed([r for r in order if r in ended]):
        if run_id in failed:
            last_failed = run_id
            break
        clean += 1
    return QualityHistory(
        process_id=process_id, clean=clean, ended=len(ended), last_failed=last_failed
    )


class RaiseVerdict(Value):
    """Whether a raise is admitted, and why not where it is not."""

    admitted: bool
    refusal: Refusal | None = None
    findings: tuple[str, ...] = ()


def verdict(
    raised: Sequence[str],
    *,
    approved_by: str | None,
    required: int | None,
    quality: QualityHistory,
) -> RaiseVerdict:
    """A raise needs a person's approval and the quality history the replaced version names.
    Every missing half is a finding; the first decides the refusal's token."""
    findings: list[str] = []
    refusal: Refusal | None = None
    what = "; ".join(raised)
    if approved_by is None:
        refusal = "no_approval"
        findings.append(
            f"raising {what} needs an explicit approval by a person, and none was given; Taktus "
            "may propose a raise, never apply one (ADR-0026)"
        )
    if required is None:
        refusal = refusal or "no_history_named"
        findings.append(
            f"raising {what} needs a quality history, and the version it replaces names none "
            "(`autonomy.history`): no raise is admitted until a version names how many runs "
            "without a failure or a result defect it needs"
        )
    elif quality.clean < required:
        refusal = refusal or "history_short"
        since = (
            ""
            if quality.last_failed is None
            else f"; the last run that failed: {quality.last_failed}"
        )
        findings.append(
            f"raising {what} needs {required} runs in a row without a failure or a result "
            f"defect; {quality.clean} of {quality.ended} ended run(s) count{since}"
        )
    return RaiseVerdict(admitted=refusal is None, refusal=refusal, findings=tuple(findings))
