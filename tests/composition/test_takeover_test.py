"""The automated takeover test of `0.5.0` (ADR-0180 §5, UC-6.3, UC-4.19).

A process at level 3 is registered with its takeover instructions and runs on a worker. A
person takes over its worker step while it runs (ADR-0128): the step stops at its boundary,
and the person receives its state together with the step's entry of the version's
instructions. The test then does what the instructions say, and nothing else: it runs the
command they name in a shell. It hands the output back; the step is the person's, the rule
after it checks the value as it would the worker's, and the run finishes. The person records
the trial, and the version is no longer untried.

What a person does is held to what the instructions say: the command run is the one their
`do` names, read from them, not from the bundle's work.
"""

from __future__ import annotations

import asyncio
import re
import subprocess
from typing import Any

from components.run.test_runner import BUDGET, TENANT, World, until
from fakes import FakeWorker, InnerStep

from taktus.adapters.driven.memory import MemoryRepository
from taktus.components.process.application.service.register_version import (
    RegisterProcessVersion,
    RegisterProcessVersionHandler,
)
from taktus.components.process.application.service.takeover import (
    TRIAL,
    RecordTrial,
    TakeoverTrials,
)
from taktus.components.process.domain.model import Process, ProcessVersion, TakeoverTrial
from taktus.components.run.application.service import HandBack, StartRun, TakeOver
from taktus.components.run.domain.model import RunState, StepState
from taktus.shared.v1 import Commissioned, Method, Plan, PlanResult, PlanStatus

PERSON = "idn_person"

BUNDLE: dict[str, Any] = {
    "id": "answer",
    "version": "1",
    "name": "The answer",
    "autonomy": {"level": 3, "reason": "a rule checks every result", "toward_next": "a year"},
    "tolerances": {"compute": 0.25},
    "steps": [
        {
            "id": "compute",
            "method": "worker",
            "reason": "a command needs a shell",
            "rejected": [{"method": "rule", "why": "the core runs no shell"}],
            "exactness": "tolerant",
            "fallback": {"when": "it fails", "to": "human", "role": "owner"},
            "requires": ["shell.script"],
            "work": {"task": {"goal": "run expr 6 '*' 7", "acceptance": ["it ran"]}},
        },
        {
            "id": "check",
            "method": "rule",
            "reason": "the value that counts is checked by a rule",
            "rejected": [{"method": "worker", "why": "a worker's word is a proposal"}],
            "exactness": "exact",
            "checks": [{"kind": "recomputation", "subject": "that the answer is 42"}],
            "depends_on": ["compute"],
            "work": {
                "rule": "check",
                "conditions": [{"value": {"$from": "compute"}, "matches": "^42$"}],
            },
        },
    ],
    "takeover": {
        "sequence": "a person runs the command, then checks that its output is 42",
        "steps": {
            "compute": {
                "system": "a shell on any computer with a POSIX shell",
                "do": "run the command `expr 6 '*' 7` and keep what it prints",
                "expertise": "running a command in a shell",
                "credentials": [],
                "done": "the command ran and its output is kept",
            },
            "check": {
                "system": "the kept output",
                "do": "compare the output with 42",
                "expertise": "none",
                "credentials": [],
                "done": "the output is exactly 42",
            },
        },
    },
}


def by_hand(instructions: dict[str, Any]) -> str:
    """What a person does from the step's instructions alone: the command their `do` names,
    run in a shell, and what it prints."""
    command = re.search(r"`([^`]+)`", instructions["do"])
    assert command is not None, "the instructions name the command to run"
    done = subprocess.run(  # noqa: S603 — the command the test's own instructions name
        ["/bin/sh", "-c", command.group(1)], capture_output=True, text=True, check=True
    )
    return done.stdout.strip()


async def test_a_person_takes_over_the_worker_step_does_it_from_the_instructions_and_tries_it() -> (
    None
):
    world = World(
        worker=FakeWorker(
            script=(InnerStep("one"), InnerStep("two"), InnerStep("three")), inner_seconds=0.15
        )
    )
    processes = MemoryRepository(world.persistence, Process)
    versions = MemoryRepository(world.persistence, ProcessVersion)
    trials = TakeoverTrials(
        processes,
        versions,
        MemoryRepository(world.persistence, TakeoverTrial),
        ledger=world.ledger,
        work=world.persistence,
        clock=world.clock,
        identifiers=world.ids,
    )
    version = await RegisterProcessVersionHandler(
        versions, world.persistence, processes, ledger=world.ledger, clock=world.clock
    ).execute(RegisterProcessVersion(BUNDLE, tenant=TENANT, by="idn_t"))
    assert await trials.untried(TENANT, version), "level 3, and nobody ran it by hand yet"

    run = await world.engine.submit(
        StartRun(
            plan=Plan(
                id=world.ids.new("pln"),
                command_id="cmd_1",
                goal=version.name,
                autonomy_level=version.autonomy.level,
                steps=version.steps,
                results_in=PlanResult.RUN,
                status=PlanStatus.COMMISSIONED,
                commissioned=Commissioned(by="idn_t", at=world.clock.now()),
            ),
            work=dict(version.work),
            budget=BUDGET,
            process_version=version.ref,
            actor="idn_t",
            tenant=TENANT,
        )
    )
    runner = world.runner("r1")
    async with asyncio.timeout(5.0):
        while (await world.stored(run.id)).step_run("compute").state is not StepState.RUNNING:  # noqa: ASYNC110
            await asyncio.sleep(0.01)
    takeover = await world.engine.take_over(
        TakeOver(run_id=run.id, step_id="compute", actor=PERSON, tenant=TENANT)
    )
    await until(lambda: len(runner.outcomes) == 1)
    await world.stop(runner)

    state = await world.engine.takeover_state(TENANT, run.id, takeover)
    instructions = await trials.of_step(TENANT, state["process_version"], state["step_id"])
    assert instructions is not None and instructions["step"] == "compute"
    assert instructions["system"].startswith("a shell"), "where to act"

    output = by_hand(instructions)
    assert output == "42"
    handed = await world.engine.hand_back(
        HandBack(run_id=run.id, takeover=takeover, result=output, actor=PERSON, tenant=TENANT)
    )
    assert handed.step_run("compute").method is Method.HUMAN

    again = world.runner("r2")
    await until(lambda: len(again.outcomes) == 1)
    await world.stop(again)
    finished = await world.stored(run.id)
    assert finished.state is RunState.FINISHED, "the rule checked the person's value"
    assert finished.step_run("check").state is StepState.SUCCEEDED

    await trials.record(
        RecordTrial(TENANT, "answer", role="owner", passed=True, missing=(), by=PERSON)
    )
    assert not await trials.untried(TENANT, version)
    async with world.persistence.transaction(TENANT):
        recorded = [e for e in await world.ledger.entries(TENANT, None) if e.kind == TRIAL]
    assert [(e.outcome, e.refs.process_version) for e in recorded] == [("passed", "answer@1")]
