"""What an anchored step asks, and what a decision does to it (ADR-0042). Pure.

An anchor keeps an act with a person whatever the autonomy level (ADR-0008, ADR-0022). Before
anything of a step starts — before its level is applied, before it is estimated — the run asks
which anchors name the step's act. For each, it raises one decision request with two options:

- **A — perform the act as proposed** (recommended): the step continues at its level, and the
  run with it;
- **B — do not perform it**: the step is not run, and the run halts at the boundary.

Option A is recommended because the registered process proposes the act at this point, and the
anchor keeps the decision with the person rather than casting doubt on the proposal; the reason
travels with the recommendation. A request's identifier is derived from the run, the step, the
anchor and the round, so that raising it again after a crash meets the one raised before.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from datetime import date

from taktus.components.run.domain.model.run import DECLINE, PROCEED, Run, Verdict
from taktus.components.run.domain.service.autonomy import Held
from taktus.components.run.ports.anchors import Draft, DraftOption
from taktus.shared.v1 import Anchor, Step

PERFORM = "A"
DO_NOT_PERFORM = "B"
RECOMMENDATION = (
    "The registered process version proposes this act at this point, and every step it "
    "depends on has succeeded. The anchor keeps the decision with you; nothing at this "
    "boundary speaks against the proposal."
)


def request_id(run_id: str, step_id: str, anchor_id: str, round: int) -> str:
    seed = f"{run_id}\n{step_id}\n{anchor_id}\n{round}"
    return "dr_" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24]


def process_of(run: Run) -> str:
    """The process a run executes: its version names it as `process@version`."""
    return run.process_version.rsplit("@", 1)[0]


def draft(run: Run, step: Step, held: Held, anchor: Anchor, *, round: int, due: date) -> Draft:
    return Draft(
        id=request_id(run.id, step.id, anchor.id, round),
        run=run.id,
        step=step.id,
        class_=str(anchor.class_),
        situation=(
            f"Run {run.id} of {run.process_version} has reached step {step.id} "
            f"({step.method}, {held.describe()}). The step's act is anchored: {anchor.act} "
            f"({anchor.class_} anchor {anchor.id}). Nothing of the step has started."
        ),
        question=(
            f"Does Taktus go ahead with step {step.id} of run {run.id}, whose act is: {anchor.act}?"
        ),
        options=(
            DraftOption(
                id=PERFORM,
                proposal=f"Go ahead with step {step.id} as the process proposes it.",
                consequence=(
                    f"The step continues at {held.describe()}, and the run with it, from this "
                    "boundary."
                ),
                recommended=True,
                reason=RECOMMENDATION,
            ),
            DraftOption(
                id=DO_NOT_PERFORM,
                proposal=f"Do not perform the act of step {step.id}.",
                consequence=(
                    "The step is not run. The run halts at this boundary; resuming it asks again."
                ),
                recommended=False,
            ),
        ),
        blocking=(run.id, f"{run.id}/{step.id}"),
        due=due,
        decider=anchor.decider.role,
        anchor=anchor.id,
    )


def verdict_of(options: Sequence[str]) -> Verdict:
    """What the applied options of a step's requests decide: proceed only when every one of
    them said to perform the act."""
    return PROCEED if all(o == PERFORM for o in options) else DECLINE
