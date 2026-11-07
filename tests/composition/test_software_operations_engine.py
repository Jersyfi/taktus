"""The software business's processes that needed a product change of the engine area, run
against fakes of the systems behind their capabilities (UC-03, ADR-0215).

The world is `test_software_operations.py`'s, with the governance component's levels wired to
the run as the composition root wires them (`composition/decisions.py`).
"""

from __future__ import annotations

from typing import Any

from fakes.owner_channel import OWNER, TENANT

from taktus.components.process.application.service.register_version import (
    RegisterProcessVersion,
)
from taktus.components.process.domain.model import ProcessVersion
from taktus.components.run.domain.model import RunState, StepState
from taktus.composition.decisions import decision_wiring

from .test_software_operations import Outside, World, bundle, outside, replying, states

__all__ = ["outside"]

CLASSIFY_MESSAGE = "You name the class"


def with_levels(w: World) -> World:
    """The run asks the governance component for its lowered levels and its classes."""
    wiring = decision_wiring(w.of, w.persistence, w.ledger, w.clock, w.given.identity.directory)
    w.engine._levels = wiring.levels
    return w


def released(document: dict[str, Any], name: str) -> dict[str, Any]:
    """B-3.02 as a tenant's version that released one class for sending on its own: the
    process at level 3, the default and every other class at 2, the class named at 3."""
    autonomy = dict(document["autonomy"])
    classes = dict(autonomy["classes"])
    levels = dict(classes["levels"])
    levels[name] = {"level": 3, "reason": "approved", "toward_next": "four more weeks"}
    autonomy.update(level=3, classes={**classes, "levels": levels})
    return {**document, "autonomy": autonomy}


async def test_b_3_03_a_released_class_is_sent_on_its_own_and_every_other_waits(
    outside: Outside,
) -> None:
    w = with_levels(await World(outside).ready())
    version: ProcessVersion = await w.register.execute(
        RegisterProcessVersion(
            released(bundle("B-3.02-draft-reply.yaml"), "how_to"), tenant=TENANT, by=OWNER
        )
    )
    assert (
        version.autonomy.classes is not None
        and version.autonomy.classes.limits.raise_decisions == 20
    )

    replying(w, "You can export the report under Settings, then Export.")
    w.model.answers[CLASSIFY_MESSAGE] = "how_to"
    before = outside.submitted()
    run = await w.start(version, message="<seed-1@mail.example>")
    assert run.state is RunState.FINISHED, [(s.step_id, s.reason) for s in run.step_runs]
    assert run.case_class == "how_to" and outside.submitted() != before

    w.model.answers[CLASSIFY_MESSAGE] = "bug"
    sent = outside.submitted()
    run = await w.start(version, message="<seed-1@mail.example>")
    assert states(run)["send"] is StepState.WAITING_HUMAN, "the class bug stays at level 2"
    assert states(run)["draft"] is StepState.SUCCEEDED, "drafted and checked unattended"
    assert outside.submitted() == sent


async def test_b_3_03_every_reply_of_the_shipped_version_is_released_and_counted_by_class(
    outside: Outside,
) -> None:
    w = with_levels(await World(outside).ready())
    version = await w.registered("B-3.02-draft-reply.yaml")
    replying(w, "You can export the report under Settings, then Export.")
    w.model.answers[CLASSIFY_MESSAGE] = "How_to."
    run = await w.confirmed(await w.start(version, message="<seed-1@mail.example>"))
    assert run.state is RunState.FINISHED
    async with w.persistence.transaction(TENANT):
        entries = await w.ledger.entries(TENANT, run.id)
    sent = [e for e in entries if e.kind == "proposal.decided" and e.refs.step_id == "send"]
    assert [e.refs.case_class for e in sent] == ["how_to"]
