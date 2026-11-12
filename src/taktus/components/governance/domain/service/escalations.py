"""The situation package of a failure's escalation, and when a reaction is overdue (UC-4.5,
ADR-0252). Pure functions over the record; no I/O.

The package has five parts, as UC-4.5 names them: what happened, what was tried, what is
affected, the options with their risks, and the documentation and access needed. Each part is
written from what the record holds. A part the record cannot fill stays empty, and the package
says which it lacks (`SituationPackage.lacking`); nothing is invented to fill it.
"""

from __future__ import annotations

from datetime import datetime

from taktus.components.governance.domain.model.defects import SituationPackage
from taktus.components.governance.domain.model.escalation import Escalated, Target

COMPLETE = "complete"
"""The outcome of `escalation.delivered` for a package with every part."""


def package(escalated: Escalated) -> SituationPackage:
    """The five parts, from the record of the escalated run."""
    happened = ""
    if escalated.step_id is not None and escalated.cause is not None:
        happened = (
            f"Run {escalated.run_id} ({escalated.process_version}) stopped at the boundary of "
            f"step {escalated.step_id}, which failed with cause {escalated.cause}"
            + (f": {escalated.reason}" if escalated.reason else "")
            + ". No later step started."
        )
    tried_parts: list[str] = []
    if escalated.attempts:
        tried_parts.append(
            f"step {escalated.step_id} was started {escalated.attempts} "
            + ("time" if escalated.attempts == 1 else "times")
        )
    if escalated.healed:
        tried_parts.append("healed within the frame before: " + ", ".join(escalated.healed))
    if escalated.finished:
        tried_parts.append("completed before it: " + ", ".join(escalated.finished))
    tried = "; ".join(tried_parts) + "." if escalated.step_id is not None and tried_parts else ""
    affected = (
        ("systems reached: " + ", ".join(escalated.reached) if escalated.reached else "")
        + ("; " if escalated.reached else "")
        + (
            f"{escalated.left} effects of the run left the system"
            if escalated.left
            else "nothing of the run left the system"
        )
        + "."
    )
    options: list[str] = []
    needed: list[str] = []
    if escalated.step_id is not None:
        options.append(
            f"Remove the cause and resume the run: it continues at step {escalated.step_id} and "
            "repeats no completed step. Risk: the step fails again while its cause remains, "
            "and where its reason says a resume repeats the call, a call that acted acts again."
        )
    if escalated.by_hand is not None:
        hand = escalated.by_hand
        options.append(
            f"Do step {escalated.step_id} by hand in {hand.system}, report it done, and let the "
            "run go on. Risk: a step done by hand is recorded only as it is reported."
        )
        needed.append(f"How to do it by hand: {hand.do} Done when: {hand.done}")
        needed.append(f"Expertise: {hand.expertise}.")
        needed.extend(f"Access: the credential {c}." for c in hand.credentials)
        needed.append(f"Access to {hand.system}.")
    if options:
        options.append(
            "Leave the run stopped. Risk: what its remaining steps would do does not happen."
        )
    if escalated.instructions:
        needed.append(f"The process by hand: {escalated.instructions}")
    return SituationPackage(
        happened=happened,
        tried=tried,
        affected=affected,
        options=tuple(options),
        needed=tuple(needed),
    )


def outcome(situation: SituationPackage) -> str:
    """The token `escalation.delivered` records: complete, or the parts it lacks."""
    lacking = situation.lacking
    return COMPLETE if not lacking else "lacking_" + "_".join(lacking)


def overdue(target: Target, delivered_at: datetime, reacted: bool, now: datetime) -> bool:
    """Whether an escalation passed its time to react without a reaction. Without a time to
    react, none is ever overdue."""
    if reacted or target.react_within is None:
        return False
    return now - delivered_at > target.react_within
