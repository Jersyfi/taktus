"""How a process really runs: its variants, its waiting by cause, and proposals (ADR-0147 §4,
UC-9.7).

`VariantsProjection` folds, per run, the path of deviations from the designed path in the
order they happened — a fallback to a person, a retry, an anchor halt, a take-over — and how the
run ended (ADR-0105). It reads only the kinds it needs. `variants` draws the view from it, the
designed steps of the active version, the blocks of the process (ADR-0043) and how many identities
hold each role. A rehearsal is no run of the work, and is left out. No figure names a person; a
figure for a role is shown only where at least two identities hold it (ADR-0015).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from pydantic import Field

from taktus.shared.v1 import LedgerEntry, Value

FELL_BACK = "fell_back"
"""The outcome of `step.awaiting` for a step whose model was unsure and went to a person."""

DEVIATIONS: Mapping[str, str] = {
    "step.retried": "retried",
    "step.anchored": "anchored",
    "step.taken_over": "taken_over",
}
"""The ledger kinds that are a deviation of their own, and the name a variant gives them."""

ENDS: Mapping[str, str] = {
    "run.finished": "finished",
    "run.escalated": "escalated",
    "run.halted": "halted",
}

KINDS = frozenset({"step.awaiting", *DEVIATIONS, *ENDS})

FALLBACK_SHARE = 0.2
"""A step that fell back to a person in at least this share of runs is proposed for a method
change, once at least `FALLBACK_RUNS` runs ended."""
FALLBACK_RUNS = 10
PERSON_WAIT_SHARE = 0.4
"""A step whose waits on a person make up at least this share of the process's waiting is
proposed for a rule below a threshold."""
EXAMPLES = 5
TOO_FEW = 2
"""Fewer identities than this hold a role: its figure would be one person's (ADR-0015)."""

WORDS = {
    FELL_BACK: "fell back to a person at",
    "retried": "retried",
    "anchored": "halted at an anchor at",
    "taken_over": "taken over by a person at",
}


@dataclass
class Travelled:
    """Per run: its process version, its deviations in order, how it ended, and whether it
    was a rehearsal."""

    runs: dict[str, dict[str, Any]] = field(default_factory=dict)


def fold(state: Travelled, entry: LedgerEntry) -> Travelled:
    run_id, version = entry.refs.run_id, entry.refs.process_version
    if run_id is None or version is None:
        return state
    held = state.runs.setdefault(
        run_id, {"version": version, "path": [], "end": None, "rehearsal": False}
    )
    if entry.rehearsal:
        held["rehearsal"] = True
    step = entry.refs.step_id
    if entry.kind == "step.awaiting" and entry.outcome == FELL_BACK and step is not None:
        held["path"].append([FELL_BACK, step])
    elif entry.kind in DEVIATIONS and step is not None:
        held["path"].append([DEVIATIONS[entry.kind], step])
    elif entry.kind in ENDS:
        held["end"] = ENDS[entry.kind]
    return state


def travelled(entries: Iterable[LedgerEntry]) -> Travelled:
    """The full computation the projection must equal."""
    state = Travelled()
    for entry in entries:
        fold(state, entry)
    return state


class VariantsProjection:
    name = "reporting.variants.v1"
    kinds: frozenset[str] | None = KINDS

    def empty(self) -> Travelled:
        return Travelled()

    def fold(self, state: Travelled, entry: LedgerEntry) -> Travelled:
        return fold(state, entry)

    def dump(self, state: Travelled) -> dict[str, Any]:
        return {"runs": state.runs}

    def load(self, document: Mapping[str, Any]) -> Travelled:
        return Travelled(runs={k: dict(v) for k, v in document["runs"].items()})


VARIANTS = VariantsProjection()


# --- the view ------------------------------------------------------------------------------------


class Variant(Value):
    path: tuple[str, ...]
    """Each deviation as `<what>@<step>`, in the order it happened; empty on the designed path."""
    end: str
    runs: int
    share: float
    examples: tuple[str, ...]
    designed: bool
    text: str = Field(min_length=1)


class WaitFact(Value):
    """One block that ended, as the composition hands it over: no person, only its step, its
    account and cause, how long, and the role a wait on a person was addressed to."""

    step_id: str
    account: str
    cause: str
    seconds: float = Field(ge=0)
    role: str | None = None


class StepWaiting(Value):
    step_id: str
    seconds: float
    by_cause: dict[str, float]
    """Seconds per account (`wait.human`, `limit.provider`, …): the causes of UC-9.5."""
    share: float | None
    """This step's share of the process's waiting; None where nothing waited."""


class RoleWaiting(Value):
    role: str
    seconds: float | None
    """None where fewer than two identities hold the role: too few to show (ADR-0015)."""
    text: str


class VariantProposal(Value):
    kind: str
    """`method` — a step falls back to a person often; `rule` — waits on a person dominate."""
    step_id: str
    evidence: str
    text: str


class VariantsView(Value):
    process_id: str
    version: str | None
    designed: tuple[str, ...]
    runs: int
    in_flight: int
    on_designed_path: float | None
    variants: tuple[Variant, ...]
    waiting: tuple[StepWaiting, ...]
    roles: tuple[RoleWaiting, ...]
    proposals: tuple[VariantProposal, ...]
    summary: str = Field(min_length=1)


def _percent(share: float) -> str:
    return f"{round(share * 100)} %"


def _words(path: Sequence[str], end: str) -> str:
    if not path and end == "finished":
        return "The designed path"
    parts = []
    for item in path:
        what, _, step = item.partition("@")
        parts.append(f"{WORDS.get(what, what)} {step}")
    if end != "finished":
        parts.append(f"ended {end}")
    text = "; ".join(parts)
    return text[0].upper() + text[1:]


def variants(
    process_id: str,
    version: str | None,
    designed: Sequence[str],
    travelled: Travelled,
    waits: Sequence[WaitFact],
    holders: Mapping[str, int],
    performers: Mapping[str, str],
) -> VariantsView:
    """`designed` are the active version's steps in order; `performers` the role a person acts
    in at each step (ADR-0146); `holders` how many identities hold each role."""
    prefix = f"{process_id}@"
    mine = [
        r for r in travelled.runs.values() if r["version"].startswith(prefix) and not r["rehearsal"]
    ]
    ended = [r for r in mine if r["end"] is not None]
    run_ids = {id(r): k for k, r in travelled.runs.items()}
    grouped: dict[tuple[tuple[str, ...], str], list[str]] = {}
    for r in ended:
        key = (tuple(f"{what}@{step}" for what, step in r["path"]), r["end"])
        grouped.setdefault(key, []).append(run_ids[id(r)])
    total = len(ended)
    found = sorted(
        (
            Variant(
                path=path,
                end=end,
                runs=len(ids),
                share=len(ids) / total,
                examples=tuple(sorted(ids)[:EXAMPLES]),
                designed=not path and end == "finished",
                text=f"{_words(path, end)}: {len(ids)} of {total} runs "
                f"({_percent(len(ids) / total)}).",
            )
            for (path, end), ids in grouped.items()
        ),
        key=lambda v: (-v.runs, v.path, v.end),
    )
    on_path = next((v.share for v in found if v.designed), 0.0) if total else None

    total_wait = sum(w.seconds for w in waits)
    per_step: dict[str, dict[str, float]] = {}
    for w in waits:
        causes = per_step.setdefault(w.step_id, {})
        causes[w.account] = causes.get(w.account, 0.0) + w.seconds
    waiting = tuple(
        StepWaiting(
            step_id=step,
            seconds=round(sum(causes.values()), 3),
            by_cause={k: round(v, 3) for k, v in sorted(causes.items())},
            share=None if not total_wait else sum(causes.values()) / total_wait,
        )
        for step, causes in sorted(per_step.items(), key=lambda kv: -sum(kv[1].values()))
    )

    by_role: dict[str, float] = {}
    for w in waits:
        role = w.role or performers.get(w.step_id)
        if w.account == "wait.human" and role is not None:
            by_role[role] = by_role.get(role, 0.0) + w.seconds
    roles = tuple(
        RoleWaiting(
            role=role,
            seconds=round(seconds, 3) if holders.get(role, 0) >= TOO_FEW else None,
            text=(
                f"Waits on the role {role}: {round(seconds / 3600, 1)} h."
                if holders.get(role, 0) >= TOO_FEW
                else f"Waits on the role {role}: too few hold it to show."
            ),
        )
        for role, seconds in sorted(by_role.items())
    )

    proposals: list[VariantProposal] = []
    if total >= FALLBACK_RUNS:
        fell: dict[str, int] = {}
        for r in ended:
            for step in {s for what, s in r["path"] if what == FELL_BACK}:
                fell[step] = fell.get(step, 0) + 1
        for step, n in sorted(fell.items()):
            if n / total >= FALLBACK_SHARE:
                proposals.append(
                    VariantProposal(
                        kind="method",
                        step_id=step,
                        evidence=f"{n} of {total} runs fell back to a person at {step}",
                        text=f"{step} fell back to a person in {_percent(n / total)} of runs: "
                        "propose a method that is sure more often (ADR-0084), and decide it in "
                        "a change in dialogue.",
                    )
                )
    for s in waiting:
        human = s.by_cause.get("wait.human", 0.0)
        if total_wait and human / total_wait >= PERSON_WAIT_SHARE:
            proposals.append(
                VariantProposal(
                    kind="rule",
                    step_id=s.step_id,
                    evidence=f"waits on a person at {s.step_id} are "
                    f"{_percent(human / total_wait)} of the process's waiting",
                    text=f"Waits on a person at {s.step_id} make up "
                    f"{_percent(human / total_wait)} of the waiting: consider a threshold "
                    "below which a rule decides, in a change in dialogue.",
                )
            )

    if not mine:
        summary = "No run of this process has been recorded yet."
    elif not total:
        summary = f"{len(mine)} runs are in flight; none has ended yet."
    else:
        summary = (
            f"{total} runs ended in {len(found)} "
            f"{'variant' if len(found) == 1 else 'variants'}; "
            f"{_percent(on_path or 0.0)} took the designed path."
        )
    return VariantsView(
        process_id=process_id,
        version=version,
        designed=tuple(designed),
        runs=total,
        in_flight=len(mine) - total,
        on_designed_path=on_path,
        variants=tuple(found),
        waiting=waiting,
        roles=roles,
        proposals=tuple(proposals),
        summary=summary,
    )
