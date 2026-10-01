"""The rules of the removal test: what the removal of an integration does to a step, to a
process, and what two runs — one with the integration, one without — show.

Every rule here is a function of data the caller observed: which steps the integration served,
which other adapter would serve them, what the step's declared fallback is, and where each run
ended. No rule calls anything. That is what makes the verdict reproducible from the ledger and
the bundle, and what makes the test admissible as `exact` (ADR-0014): the verdict is a check
over values, never a judgement.

The four verdicts (`Verdict`): *broke* — a step loses its only adapter and nobody takes it
over; *changed* — another adapter serves the step, or a person does, and the process still
reaches its point at a different quality or cost; *untested* — no registered process uses the
integration, so nothing was exercised and nothing learned; *exception* — the integration
cannot be removed by design, and the reason is recorded instead of a failure.

A process is exercised by rehearsing it (ADR-0030): its outward connector operations answer
with recorded responses of earlier real calls, so running it twice leaves nothing outside.
`safe_to_run` says when that is impossible.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from taktus.components.catalog.domain.model import (
    ProcessFinding,
    RunSummary,
    StepFinding,
    Verdict,
)
from taktus.shared.v1 import Method, Step, StepId

EXCEPTIONS: Mapping[str, str] = {
    "persistence.database": (
        "the database is the one mandatory dependency (ADR-0002): it carries the state, the "
        "queue, the ledger and the provenance chain, and an instance without it has nothing to "
        "run a process against. Its removal test is the restore drill (ADR-0013 C), not this "
        "process."
    ),
}
"""The integrations that cannot be removed by design, with the reason the result records."""


def step_finding(step: Step, served: str, alternative: str | None) -> StepFinding:
    """What happens to one step when the integration that served it is withheld."""
    if alternative is not None:
        return StepFinding(
            step=step.id,
            served=served,
            alternative=alternative,
            fallback=None if step.fallback is None else step.fallback.to,
            verdict=Verdict.CHANGED,
            reason=f"{alternative} serves {served} instead; quality and cost are that adapter's",
        )
    if step.fallback is not None and step.fallback.to is Method.HUMAN:
        return StepFinding(
            step=step.id,
            served=served,
            alternative=None,
            fallback=Method.HUMAN,
            verdict=Verdict.CHANGED,
            reason=(
                f"no other adapter serves {served}; the step falls back to a person "
                f"({step.fallback.when}) — the cost is a person's time, the quality theirs"
            ),
        )
    if step.fallback is not None:
        return StepFinding(
            step=step.id,
            served=served,
            alternative=None,
            fallback=step.fallback.to,
            verdict=Verdict.BROKE,
            reason=(
                f"no other adapter serves {served}; the declared fallback is {step.fallback.to}, "
                "which the run cannot switch to in this version — only a fallback to a person "
                "keeps the process running"
            ),
        )
    return StepFinding(
        step=step.id,
        served=served,
        alternative=None,
        fallback=None,
        verdict=Verdict.BROKE,
        reason=f"no other adapter serves {served} and the step names no fallback",
    )


def process_verdict(findings: Sequence[StepFinding]) -> Verdict:
    """A process breaks if any of its steps does."""
    if any(finding.verdict is Verdict.BROKE for finding in findings):
        return Verdict.BROKE
    return Verdict.CHANGED


def compare(
    findings: Sequence[StepFinding], baseline: RunSummary, withheld: RunSummary
) -> tuple[Verdict, str]:
    """What two runs of one process show: with the integration (baseline) and without it.

    The process *changed* when the run without the integration reaches the point the baseline
    reached — the same end state at the same step, or finished — or when it stops at a step
    that resolution said a person takes over, and the baseline got past that step. Anything
    else *broke*: the run without the integration ended earlier, for a reason nobody takes
    over."""
    if withheld.state == "finished" or (
        withheld.state == baseline.state and withheld.at_step == baseline.at_step
    ):
        return Verdict.CHANGED, (
            f"reaches the same point as with the integration ({withheld.state}"
            f"{'' if withheld.at_step is None else ' at ' + withheld.at_step}); "
            + _delta(baseline, withheld)
        )
    by_step = {finding.step: finding for finding in findings}
    stopped_at = by_step.get(withheld.at_step or "")
    if (
        stopped_at is not None
        and stopped_at.verdict is Verdict.CHANGED
        and stopped_at.fallback is Method.HUMAN
    ):
        return Verdict.CHANGED, (
            f"stops at {withheld.at_step} ({withheld.state}), where a person takes over: "
            f"{stopped_at.reason}"
        )
    return Verdict.BROKE, (
        f"ends {withheld.state}{'' if withheld.at_step is None else ' at ' + withheld.at_step}"
        f" where the run with the integration reached {baseline.state}"
        f"{'' if baseline.at_step is None else ' at ' + baseline.at_step}"
        f"{'' if withheld.cause is None else ' — ' + withheld.cause}"
    )


def resolved_only(
    process: str, findings: Sequence[StepFinding], why_not_run: str
) -> ProcessFinding:
    """A process that was not safe to run: the verdict rests on resolution alone."""
    return ProcessFinding(
        process=process,
        exercised="resolved",
        verdict=process_verdict(findings),
        steps=tuple(findings),
        baseline=None,
        withheld=None,
        note=why_not_run,
    )


def exercised(
    process: str,
    findings: Sequence[StepFinding],
    baseline: RunSummary,
    withheld: RunSummary,
) -> ProcessFinding:
    """A process that ran twice; the verdict is what the runs showed, and the resolution
    findings say why."""
    verdict, words = compare(findings, baseline, withheld)
    return ProcessFinding(
        process=process,
        exercised="run",
        verdict=verdict,
        steps=tuple(findings),
        baseline=baseline,
        withheld=withheld,
        note=words,
    )


UNUSED = "no registered process uses this integration"


def overall(processes: Sequence[ProcessFinding]) -> Verdict:
    """The integration's verdict: broke if any process broke; untested when no process uses
    the integration — nothing was exercised, and "removing it changes nothing" is not a
    finding; changed otherwise."""
    if not processes:
        return Verdict.UNTESTED
    if any(process.verdict is Verdict.BROKE for process in processes):
        return Verdict.BROKE
    return Verdict.CHANGED


def safe_to_run(
    hosts: Sequence[StepId],
    unrecorded: Sequence[str],
    missing_inputs: Sequence[str],
) -> str | None:
    """Why a process cannot be rehearsed, or None when it can: a worker step whose frame
    allows hosts (a rehearsal cannot answer for what a worker sends), an outward connector
    operation with no recorded response, or an input the bundle gives no example for."""
    reasons: list[str] = []
    if hosts:
        reasons.append(
            "step(s) "
            + ", ".join(hosts)
            + " would leave the system — a worker whose frame allows hosts is not rehearsed"
        )
    for operation in dict.fromkeys(unrecorded):
        reasons.append(
            f"no recorded response for {operation} — it has never been called for real on "
            "this instance"
        )
    if missing_inputs:
        reasons.append("no example for input(s) " + ", ".join(missing_inputs))
    return "not run: " + "; ".join(reasons) if reasons else None


def _delta(baseline: RunSummary, withheld: RunSummary) -> str:
    before = baseline.consumption.quantities() if baseline.consumption else {}
    after = withheld.consumption.quantities() if withheld.consumption else {}
    keys = sorted(set(before) | set(after))
    if not keys:
        return "nothing measured on either run"
    parts = [f"{key} {before.get(key, 0)} → {after.get(key, 0)}" for key in keys]
    return "consumption " + ", ".join(parts)
