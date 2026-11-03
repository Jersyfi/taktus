"""The export of a run's recording, and the replay of what it wrote (ADR-0108, issue #393).

A run of a small process — a read, a model's completion, a worker's change, a wait on the
outside and a write — runs for real against the fakes of the ports, in a database. The tool
writes its recording; the replay of that recording comes where the run came, step for step.
The tool keeps its own copy of the request digests, because it runs in an instance's image
that may predate the replay's module: here the two are held to each other. And the tool
refuses what it must refuse: a rehearsal, a run that has not ended, a known secret.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest
from fakes import VERIFIED, FakeConnector, FakeModel, FakeWorker
from fakes.connector import READ, WRITE

from taktus.adapters.driven.clock import SystemIdentifiers
from taktus.adapters.driven.connectors.pool import StaticConnectorPool
from taktus.adapters.driven.memory import MemoryObjectStore
from taktus.adapters.driven.models import StaticModelPool
from taktus.adapters.driven.replay import requests
from taktus.adapters.driven.telemetry import NoTelemetry
from taktus.adapters.driven.workers.pool import StaticWorkerPool
from taktus.components.command.application.service import CommissionPlan, CommissionPlanHandler
from taktus.components.identity.application.service import TenantRegistry
from taktus.components.ledger.application.service import ChainedLedger
from taktus.components.process.application.service.register_version import (
    RegisterProcessVersion,
    RegisterProcessVersionHandler,
)
from taktus.components.process.domain.model import Process, ProcessVersion
from taktus.components.run.application.service import RunEngine, StartRun
from taktus.components.run.domain.model import Run, RunState
from taktus.composition.local import Stores
from taktus.composition.replay import ReplayClock, replay, stores
from taktus.ports.model import Prompt
from taktus.ports.worker import Limits, Task
from taktus.shared.v1 import Command, Intent, Plan, ReplyTo

TOOLS = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS))

import record_rehearsal  # noqa: E402 — a script under tools/, found through the line above

BUNDLE: dict[str, Any] = {
    "id": "recorded",
    "version": "1",
    "name": "Recorded",
    "autonomy": {"level": 3, "reason": "a test", "toward_next": "nothing"},
    "limits": {"quota": {"units": 40}, "compute": {"seconds": 600, "resource_class": "cpu.small"}},
    "inputs": {"record": {"description": "the record to read", "example": "7"}},
    "steps": [
        {
            "id": "read",
            "method": "rule",
            "reason": "a read",
            "rejected": [],
            "exactness": "sourced",
            "work": {"rule": "connector", "operation": READ, "input": {"id": {"$input": "record"}}},
        },
        {
            "id": "think",
            "method": "llm",
            "reason": "words",
            "rejected": [],
            "exactness": "tolerant",
            "fallback": {"when": "always", "to": "human"},
            "depends_on": ["read"],
            "work": {
                "purpose": "reasoning",
                "prompt": "Say something about ${title}",
                "values": {"title": {"$from": "read", "$select": "output.title"}},
            },
        },
        {
            "id": "change",
            "method": "worker",
            "reason": "tools",
            "rejected": [],
            "exactness": "tolerant",
            "fallback": {"when": "always", "to": "human"},
            "requires": ["shell.script"],
            "depends_on": ["think"],
            "work": {
                "task": {
                    "goal": "change it",
                    "acceptance": ["it is changed"],
                    "inputs": {"said": {"$from": "think", "$select": "text"}},
                },
                "max_steps": 3,
            },
        },
        {
            "id": "settle",
            "method": "wait",
            "reason": "the outside settles",
            "rejected": [],
            "depends_on": ["change"],
            "work": {
                "until": {
                    "operation": READ,
                    "input": {"id": {"$input": "record"}},
                    "select": "found",
                    "expect": [True],
                    "poll_seconds": 1,
                    "timeout_seconds": 5,
                }
            },
        },
        {
            "id": "write",
            "method": "rule",
            "reason": "a write",
            "rejected": [],
            "exactness": "sourced",
            "depends_on": ["settle"],
            "work": {
                "rule": "connector",
                "operation": WRITE,
                "input": {"body": {"$from": "think", "$select": "text"}},
            },
        },
    ],
}


async def real_run(store: Stores, objects: Path) -> tuple[str, str]:
    """The process run once for real against the fakes; its tenant and its run."""
    clock = ReplayClock()
    ids = SystemIdentifiers()  # unique across the tests that share the database
    ledger = ChainedLedger(store.ledger_store, clock, store.projection_store)
    tenant = (
        await TenantRegistry(
            store=store.tenants, work=store.work, ledger=ledger, clock=clock, ids=ids
        ).create("recorded")
    ).id
    version = await RegisterProcessVersionHandler(
        store.of(ProcessVersion), store.work, store.of(Process), ledger=ledger
    ).execute(RegisterProcessVersion(BUNDLE, tenant=tenant, by="idn_ada"))
    connector = FakeConnector(reads={"7": {"id": "7", "found": True, "title": "the seventh"}})
    engine = RunEngine(
        runs=store.of(Run),
        work=store.work,
        objects=MemoryObjectStore(objects),
        ledger=ledger,
        provenance=store.provenance_store,
        workers=StaticWorkerPool([("worker.fake", FakeWorker())]),
        connectors=StaticConnectorPool([("connector.fake", connector)]),
        models=StaticModelPool([("model.fake", ["reasoning"], FakeModel(), "fake-model@1")]),
        clock=clock,
        ids=ids,
        telemetry=NoTelemetry(),
        maturities=VERIFIED,
    )
    command = Command(
        id=ids.new("cmd"),
        channel="channel.cli",
        identity="idn_ada",
        org_path=(tenant,),
        intent=Intent(raw="run", recognised="process.run"),
        reply_to=ReplyTo(channel="channel.cli", address="ledger"),
        received_at=clock.now(),
    )
    plan = await CommissionPlanHandler(
        store.of(Command), store.of(Plan), store.work, clock, ids
    ).execute(
        CommissionPlan(
            command=command,
            tenant=tenant,
            goal="run it",
            autonomy_level=version.autonomy_level,
            steps=version.ordered(),
        )
    )
    run = await engine.start(
        StartRun(
            plan=plan,
            work=version.work,
            budget=Limits.model_validate(BUNDLE["limits"]),
            process_version=version.ref,
            actor="idn_ada",
            tenant=tenant,
            inputs={"record": "7"},
            actions=version.autonomy.action_levels,
        )
    )
    assert run.state is RunState.FINISHED, run.reason
    return tenant, run.id


async def test_a_recorded_run_replays_step_for_step(postgres_url: str, tmp_path: Path) -> None:
    async with stores(postgres_url) as store:
        tenant, run_id = await real_run(store, tmp_path / "objects")
    document, files = await record_rehearsal.export(
        postgres_url, tenant, run_id, tmp_path / "objects", "local", {}
    )
    record_rehearsal.check_secrets(files, ["tok-not-in-there"])
    record_rehearsal.write(tmp_path / "recording", document, files)
    kinds = {s["id"]: s.get("answer", {}).get("kind") for s in document["steps"]}
    assert kinds == {
        "read": "connector",
        "think": "model",
        "change": "worker",
        "settle": "wait",
        "write": "connector",
    }
    assert "idn_ada" not in json.dumps(document), "the recording names no person"
    async with stores(postgres_url) as store:
        done = await replay(BUNDLE, tmp_path / "recording", store)
    assert done.held, done.differences
    assert done.run.id == run_id and done.run.rehearsal


async def test_the_tool_refuses_a_rehearsal_and_a_known_secret(
    postgres_url: str, tmp_path: Path
) -> None:
    async with stores(postgres_url) as store:
        tenant, run_id = await real_run(store, tmp_path / "objects")
    document, files = await record_rehearsal.export(
        postgres_url, tenant, run_id, tmp_path / "objects", "local", {}
    )
    with pytest.raises(record_rehearsal.Refused, match="holds the value of a secret"):
        record_rehearsal.check_secrets(files, ["the seventh"])
    record_rehearsal.write(tmp_path / "recording", document, files)
    async with stores(postgres_url) as store:
        done = await replay(BUNDLE, tmp_path / "recording", store)
    with pytest.raises(record_rehearsal.Refused, match="is a rehearsal"):
        await record_rehearsal.export(
            postgres_url, done.run.tenant, done.run.id, tmp_path / "objects", "local", {}
        )
    with pytest.raises(record_rehearsal.Refused, match="no run"):
        await record_rehearsal.export(
            postgres_url, tenant, "run_nothing", tmp_path / "objects", "local", {}
        )


async def test_a_process_named_takes_its_newest_real_run_never_a_rehearsal(
    postgres_url: str, tmp_path: Path
) -> None:
    """`--process` spares the person who records on the instance the run's identifier: the run
    of the process that ended outside a rehearsal is taken, and a replay of it is not."""
    async with stores(postgres_url) as store:
        tenant, run_id = await real_run(store, tmp_path / "objects")
    document, files = await record_rehearsal.export(
        postgres_url, tenant, run_id, tmp_path / "objects", "local", {}
    )
    record_rehearsal.write(tmp_path / "recording", document, files)
    async with stores(postgres_url) as store:
        await replay(BUNDLE, tmp_path / "recording", store)
    assert await record_rehearsal.latest(postgres_url, tenant, "recorded") == run_id
    with pytest.raises(record_rehearsal.Refused, match="no run of elsewhere"):
        await record_rehearsal.latest(postgres_url, tenant, "elsewhere")


def test_a_version_reference_is_read_as_its_number() -> None:
    assert record_rehearsal.version_of("p03-implementation@20") == 20
    assert record_rehearsal.version_of("unversioned") == 0


def test_an_output_directory_that_is_not_empty_is_refused(tmp_path: Path) -> None:
    (tmp_path / "kept").write_text("an earlier recording", encoding="utf-8")
    environment = {"TAKTUS_DATABASE_URL": "postgresql://nobody@127.0.0.1:1/none"}
    with pytest.MonkeyPatch.context() as patch:
        for name, value in environment.items():
            patch.setenv(name, value)
        code = record_rehearsal.main(["--tenant", "t", "--run", "r", "--out", str(tmp_path)])
    assert code == 2
    assert [p.name for p in tmp_path.iterdir()] == ["kept"]


@pytest.mark.parametrize(
    "document",
    [
        {"operation": "repository.issues.read", "input": {"number": 7, "labels": ("a", "b")}},
        {"operation": "x.y.z", "input": {}},
    ],
)
def test_the_tool_digests_a_request_as_the_replay_does(document: dict[str, Any]) -> None:
    built = requests.connector(document["operation"], document["input"])
    assert built == record_rehearsal.connector_request(document["operation"], document["input"])
    assert requests.request(built).document() == record_rehearsal.request(built)
    prompt = Prompt(system="s", user="u", max_output_tokens=5)
    assert requests.request(requests.model(prompt)).document() == record_rehearsal.request(
        prompt.document()
    )
    task = Task(goal="g", acceptance=("a",), inputs={"k": [1, 2]})
    assert requests.request(requests.worker(task)).document() == record_rehearsal.request(
        task.document()
    )


def test_the_known_secrets_are_every_file_the_environment_points_at(tmp_path: Path) -> None:
    secret = tmp_path / "token"
    secret.write_text("a-long-enough-secret\n", encoding="utf-8")
    found = record_rehearsal.known_secrets(
        {"TAKTUS_CREDENTIAL_X_FILE": str(secret), "TAKTUS_SHORT_FILE": str(tmp_path / "none")}
    )
    assert found == ["a-long-enough-secret"]


def test_a_recording_names_no_person() -> None:
    """ADR-0108: an issue's author, as a connector answers it, leaves only its kind behind."""
    answered = {
        "output": {
            "number": 7,
            "author": {"kind": "person", "account": "64214261", "login": "someone"},
            "comments": [{"author": {"kind": "person", "account": "1"}, "body": "b"}],
            "assignee": {"kind": "bot", "account": "taktus"},
        }
    }
    kept = record_rehearsal.without_persons(answered)
    assert kept["output"]["author"] == {
        "kind": "person",
        "account": record_rehearsal.PERSON,
        "login": record_rehearsal.PERSON,
    }
    assert kept["output"]["comments"][0]["author"]["account"] == record_rehearsal.PERSON
    assert kept["output"]["comments"][0]["body"] == "b"
    assert kept["output"]["assignee"] == {"kind": "bot", "account": "taktus"}
    assert "64214261" not in json.dumps(kept)
