"""Write the recording of one run, from an instance's database, for the replay of the
self-development bundles (ADR-0108).

    python3 record_rehearsal.py --tenant TENANT (--run RUN_ID | --process PROCESS) --out DIRECTORY
        [--objects DIRECTORY] [--taken instance|local]

`--process` names the process instead of the run: the tool takes the run of its highest version
that ended and is not a rehearsal, the newest of them, and says which it took.

It reads the run from the database the instance is configured with — `TAKTUS_DATABASE_URL_FILE`,
or `TAKTUS_DATABASE_URL` on a developer's machine, the way every Taktus command reads it; a
URL holds a password, so it is never an argument — and the results and artifacts the run kept
from the object store under `--objects`, by default `$TAKTUS_STATE_DIR/objects`. The price
table and the margin of a worker without history are read as the instance reads them
(`TAKTUS_PRICE_TABLE`, `TAKTUS_BUDGET_UNCALIBRATED_MARGIN`). It writes the directory a replay
reads (`src/taktus/adapters/driven/replay/recording.py`): `recording.json`, the result of every
connector and model step under `results/`, the artifacts of every worker step under
`artifacts/`. It writes nothing anywhere else and changes nothing in the database.

What each step sent is reconstructed from what the run kept — the step's work, the run's
inputs, the results of the steps before it — the way the engine builds it, and recorded as
digests only. What each step received is kept as the run kept it.

It refuses, and writes nothing: a run that is a rehearsal, or still running; a directory that is
not empty; and a recording in which it finds the value of a secret the environment points at
(every `TAKTUS_…_FILE`, the database URL among them).

A recording names no person (ADR-0108, principle 14). A connector names an actor as an object
with `"kind": "person"`, such as an issue's author; every other field of such an object is
replaced by `PERSON` as a result is read, before anything is reconstructed from it, so what a
later step sent is recorded as the replay will send it.

It must run where the instance runs — in its runner image, with the `taktus` package and Python
and nothing else — so it imports only what every recent release of the package has, and keeps
the recording's format and digests here, beside the replay's own definition of them, which
`tests/tools/test_record_rehearsal.py` holds it to.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from taktus.adapters.driven.configuration import EnvironmentConfiguration
from taktus.adapters.driven.memory import MemoryObjectStore
from taktus.adapters.driven.postgres import PostgresPersistence, PostgresRepository
from taktus.components.run.domain.model import (
    ConnectorRule,
    LlmWork,
    MlWork,
    Run,
    RunState,
    StepRun,
    StepState,
    TemplateRule,
    WaitWork,
    WorkerWork,
    parse_work,
    resolve,
)
from taktus.components.run.domain.service import rules
from taktus.composition.settings import load_budget
from taktus.ports.model import Prompt
from taktus.ports.worker import Task

FORMAT = "taktus.recording/v1"
RECORDING = "recording.json"
ENDED = (RunState.FINISHED, RunState.ESCALATED, RunState.HALTED, RunState.WAITING_HUMAN)
"""A run that ended, or waits for a person: what a replay can be held to."""
SHORTEST_SECRET = 8
"""A known secret shorter than this is not searched for: it would match by chance."""

PERSON = "a person"
"""What stands for every identifier of a person a connector answered (ADR-0108)."""


class Refused(Exception):
    """The recording is not written; the message says why."""


# --- requests: the same documents and digests as src/taktus/adapters/driven/replay/requests.py


def canonical(document: Any) -> bytes:
    return json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def digest(document: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical(document)).hexdigest()


def request(document: Mapping[str, Any]) -> dict[str, Any]:
    parts: dict[str, str] = {}
    for key, value in document.items():
        if isinstance(value, Mapping) and value:
            for inner, part in value.items():
                parts[f"{key}.{inner}"] = digest(part)
        else:
            parts[key] = digest(value)
    return {"digest": digest(dict(document)), "parts": parts}


def connector_request(operation: str, input: Mapping[str, Any]) -> dict[str, Any]:
    return {"operation": operation, "input": json.loads(canonical(dict(input)))}


# --- the run --------------------------------------------------------------------------------


def without_persons(document: Any) -> Any:
    """The document with every field of an object of kind `person` but its kind replaced."""
    if isinstance(document, Mapping):
        if document.get("kind") == "person":
            return {key: ("person" if key == "kind" else PERSON) for key in document}
        return {key: without_persons(value) for key, value in document.items()}
    if isinstance(document, list):
        return [without_persons(value) for value in document]
    return document


def _json_file(document: Any) -> bytes:
    return (json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


class Export:
    """One run, as a recording."""

    def __init__(self, run: Run, objects: MemoryObjectStore) -> None:
        self.run = run
        self.objects = objects
        self.files: dict[str, bytes] = {}

    async def content(self, step_run: StepRun, what: str, at: str) -> bytes:
        found = await self.objects.get(at)
        if found is None:
            raise Refused(
                f"step {step_run.step_id}: {what} {at} is not in the object store; is "
                "--objects the instance's?"
            )
        return found

    async def results(self) -> tuple[dict[str, Any], dict[str, Any]]:
        """What every step that is done produced, as `$from` reads it, and the content of every
        artifact, as `$artifact` reads it."""
        results: dict[str, Any] = {}
        artifacts: dict[str, Any] = {}
        for step_run in self.run.step_runs:
            if not step_run.done:
                continue
            checkpoint = step_run.checkpoint
            if checkpoint is not None and checkpoint.result_digest is not None:
                content = await self.content(step_run, "the result", checkpoint.result_digest)
                results[step_run.step_id] = json.loads(content)
            else:
                results[step_run.step_id] = {
                    "artifacts": [a.document() for a in step_run.artifacts]
                }
            for artifact in step_run.artifacts:
                content = await self.content(step_run, "the artifact", artifact.digest)
                text = content.decode("utf-8", errors="replace")
                if (artifact.media_type or "").startswith("application/json"):
                    try:
                        artifacts[f"{step_run.step_id}/{artifact.id}"] = json.loads(text)
                        continue
                    except ValueError:
                        pass
                artifacts[f"{step_run.step_id}/{artifact.id}"] = text
        return results, artifacts

    async def recording(self, taken: str, held: Mapping[str, Any]) -> dict[str, Any]:
        run = self.run
        results, artifacts = await self.results()
        record = run.record()
        operations: dict[str, dict[str, Any]] = {}
        steps: list[dict[str, Any]] = []
        for step in run.steps:
            step_run = run.step_run(step.id)
            work = parse_work(step, run.work.get(step.id), run.inputs)
            entry: dict[str, Any] = {
                "id": step.id,
                "method": str(step.method),
                "state": str(step_run.state),
                "met_a_person": step_run.anchoring is not None or step_run.confirmed_by is not None,
            }
            answer = await self.answer(step_run, work, results, artifacts, record, operations)
            if answer is not None:
                entry["answer"] = answer
            steps.append(entry)
        document: dict[str, Any] = {
            "format": FORMAT,
            "taken": taken,
            "process": run.process_version.split("@", 1)[0],
            "process_version": run.process_version,
            "run_id": run.id,
            "state": str(run.state),
            "inputs": dict(run.inputs),
            "budget": run.budget.document(),
            "margin": run.margin,
            "operations": [operations[name] for name in sorted(operations)],
            "steps": steps,
            **{key: value for key, value in held.items() if value is not None},
        }
        if run.cause is not None:
            document["cause"] = str(run.cause)
        return document

    async def answer(
        self,
        step_run: StepRun,
        work: Any,
        results: dict[str, Any],
        artifacts: dict[str, Any],
        record: dict[str, Any],
        operations: dict[str, dict[str, Any]],
    ) -> dict[str, Any] | None:
        """How the outside answered the step; None for a step that did not reach it."""
        if step_run.adapter is None or step_run.state in (StepState.PLANNED, StepState.REJECTED):
            return None
        if isinstance(work, MlWork):
            raise Refused(f"step {step_run.step_id}: an ml step is not recorded yet")

        def resolved(value: Any) -> Any:
            return resolve(value, results, artifacts, record)

        outcome = {
            StepState.SUCCEEDED: "succeeded",
            StepState.STOPPED: "stopped",
        }.get(step_run.state, "failed")
        answer: dict[str, Any] = {"adapter": step_run.adapter, "outcome": outcome}
        if step_run.estimate is not None:
            answer["estimate"] = step_run.estimate.document()
        if step_run.consumption is not None:
            answer["consumption"] = step_run.consumption.document()
        stored = await self.stored(step_run)
        if isinstance(work, ConnectorRule):
            answer |= {"kind": "connector", "operation": work.operation}
            answer["request"] = request(connector_request(work.operation, resolved(work.input)))
            effect = "read"
            if stored is not None:
                answer["result"] = self.keep(f"results/{step_run.step_id}.json", stored)
                effect = str(stored.get("effect", {}).get("kind", "read"))
            declare(operations, work.operation, work.capability, effect, step_run, calls=1)
            return answer
        if isinstance(work, WaitWork) and work.until is not None:
            until = work.until
            answer |= {"kind": "wait", "operation": until.operation}
            answer["request"] = request(connector_request(until.operation, resolved(until.input)))
            if outcome == "succeeded":
                answer["observed"] = {"select": until.select, "value": until.expect[0]}
            calls = int(until.timeout_seconds // until.poll_seconds) + 1
            declare(operations, until.operation, until.capability, "read", step_run, calls=calls)
            return answer
        if isinstance(work, LlmWork):
            values = resolved(work.values)
            rendered = rules.template(
                TemplateRule(rule="template", text=work.prompt, values=work.values), values
            )
            prompt = Prompt(
                system=work.system, user=rendered, max_output_tokens=work.max_output_tokens
            )
            answer |= {"kind": "model", "purpose": work.purpose}
            answer["request"] = request(prompt.document())
            if stored is not None:
                answer["result"] = self.keep(f"results/{step_run.step_id}.json", stored)
                answer["version"] = stored.get("model")
            return answer
        if isinstance(work, WorkerWork):
            task = Task(
                goal=work.task.goal,
                acceptance=work.task.acceptance,
                inputs=resolved(work.task.inputs),
                before=work.task.before,
                after=work.task.after,
            )
            answer |= {"kind": "worker", "capabilities": list(self.required(step_run))}
            answer["request"] = request(task.document())
            kept = []
            for artifact in step_run.artifacts:
                name = f"artifacts/{step_run.step_id}/{artifact.id}"
                self.files[name] = await self.content(step_run, "the artifact", artifact.digest)
                kept.append(
                    {"id": artifact.id, "kind": artifact.kind, "file": name}
                    | ({"media_type": artifact.media_type} if artifact.media_type else {})
                )
            answer["artifacts"] = kept
            return answer
        return None

    def required(self, step_run: StepRun) -> tuple[str, ...]:
        return tuple(self.run.step(step_run.step_id).required_capabilities)

    async def stored(self, step_run: StepRun) -> dict[str, Any] | None:
        checkpoint = step_run.checkpoint
        if step_run.state is not StepState.SUCCEEDED or checkpoint is None:
            return None
        if checkpoint.result_digest is None:
            return None
        document = json.loads(await self.content(step_run, "the result", checkpoint.result_digest))
        return without_persons(document) if isinstance(document, dict) else None

    def keep(self, name: str, document: Any) -> str:
        self.files[name] = _json_file(document)
        return name


def declare(
    operations: dict[str, dict[str, Any]],
    name: str,
    capability: str,
    effect: str,
    step_run: StepRun,
    *,
    calls: int,
) -> None:
    """What the operation was declared as, as far as the run shows it: its effect, and the most
    one call consumes — the step's estimate over the calls it was estimated for. An outward
    operation is declared as recognising a repeat: a replay never repeats one."""
    declared = operations.setdefault(
        name,
        {"name": name, "capability": capability, "effect": effect, "summary": "as recorded"},
    )
    if effect != "read":
        declared["effect"] = effect
        declared["idempotency"] = "marked"
    estimate = None if step_run.estimate is None else step_run.estimate.quantities()
    if not estimate:
        return
    demand = dict(declared.get("demand") or {})
    for key in ("quota_units", "compute_seconds"):
        if key in estimate:
            demand[key] = max(float(demand.get(key, 0.0)), float(estimate[key]) / calls)
    if "currency" in estimate:
        money = dict(demand.get("currency") or {})
        for code, amount in estimate["currency"].items():
            money[code] = max(float(money.get(code, 0.0)), float(amount) / calls)
        demand["currency"] = money
    if demand:
        declared["demand"] = demand


# --- secrets --------------------------------------------------------------------------------


def known_secrets(environment: Mapping[str, str]) -> list[str]:
    """Every value a `TAKTUS_…_FILE` variable points at, and the database URL given inline."""
    found: list[str] = []
    for name, path in environment.items():
        if name.startswith("TAKTUS_") and name.endswith("_FILE"):
            try:
                found.append(Path(path).read_text(encoding="utf-8").strip())
            except OSError:
                continue
    inline = environment.get("TAKTUS_DATABASE_URL", "").strip()
    if inline:
        found.append(inline)
    return [value for value in found if len(value) >= SHORTEST_SECRET]


def check_secrets(files: Mapping[str, bytes], secrets: list[str]) -> None:
    for name, content in sorted(files.items()):
        text = content.decode("utf-8", errors="replace")
        for value in secrets:
            if value in text:
                raise Refused(
                    f"{name} holds the value of a secret the environment points at; nothing "
                    "is written"
                )


# --- the command ----------------------------------------------------------------------------


async def export(
    database: str,
    tenant: str,
    run_id: str,
    objects: Path,
    taken: str,
    held: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, bytes]]:
    postgres = PostgresPersistence(database)
    try:
        async with postgres.transaction(tenant):
            run = await PostgresRepository(postgres, Run).get(tenant, run_id)
    finally:
        await postgres.close()
    if run is None:
        raise Refused(f"no run {run_id} in tenant {tenant}")
    if run.rehearsal:
        raise Refused(f"run {run_id} is a rehearsal; a recording is of a real run")
    if run.state not in ENDED:
        raise Refused(f"run {run_id} is {run.state}; record a run that has ended")
    exported = Export(run, MemoryObjectStore(objects, cache_bytes=0))
    document = await exported.recording(taken, held)
    return document, exported.files


def version_of(process_version: str) -> int:
    """The number of a version reference `process@N`; 0 where it carries none."""
    _, _, number = process_version.rpartition("@")
    return int(number) if number.isdigit() else 0


def chosen(runs: list[Run], process: str) -> Run | None:
    """The run to record of a process: of its highest version, ended and not a rehearsal, the
    newest. None where no run qualifies."""
    candidates = [
        run
        for run in runs
        if run.process_version.rpartition("@")[0] == process
        and not run.rehearsal
        and run.state in ENDED
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda run: (version_of(run.process_version), run.created_at))


async def latest(database: str, tenant: str, process: str) -> str:
    """The identifier of the run `chosen` takes, read from the instance's database."""
    postgres = PostgresPersistence(database)
    try:
        async with postgres.transaction(tenant):
            runs = list(await PostgresRepository(postgres, Run).list(tenant))
    finally:
        await postgres.close()
    run = chosen(runs, process)
    if run is None:
        raise Refused(f"no run of {process} in tenant {tenant} has ended outside a rehearsal")
    return run.id


def write(directory: Path, document: dict[str, Any], files: Mapping[str, bytes]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for name, content in sorted(files.items()):
        target = directory / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    (directory / RECORDING).write_bytes(_json_file(document))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--tenant", required=True, help="the tenant the run is in")
    named = parser.add_mutually_exclusive_group(required=True)
    named.add_argument("--run", help="the run's identifier")
    named.add_argument(
        "--process", help="the process: its newest ended run of its highest version is taken"
    )
    parser.add_argument("--out", required=True, type=Path, help="an empty or new directory")
    parser.add_argument("--objects", type=Path, help="the object store's directory")
    parser.add_argument("--taken", choices=("instance", "local"), default="instance")
    args = parser.parse_args(argv)
    configuration = EnvironmentConfiguration()
    secret = configuration.secret("database.url")
    if secret is None:
        print("set TAKTUS_DATABASE_URL_FILE (or TAKTUS_DATABASE_URL)", file=sys.stderr)
        return 2
    objects = args.objects or (
        Path(os.environ.get("TAKTUS_STATE_DIR", "~/.cache/taktus/taktusd")).expanduser() / "objects"
    )
    if args.out.exists() and any(args.out.iterdir()):
        print(f"{args.out} is not empty; nothing is written", file=sys.stderr)
        return 2
    budget = load_budget(configuration)
    table = budget.table()
    held = {
        "prices": None if table is None else table.document(),
        "uncalibrated_margin": budget.uncalibrated_margin,
    }
    try:
        run_id = args.run or asyncio.run(latest(secret.reveal(), args.tenant, args.process))
        document, files = asyncio.run(
            export(secret.reveal(), args.tenant, run_id, objects, args.taken, held)
        )
        everything = {**files, RECORDING: _json_file(document)}
        check_secrets(everything, [*known_secrets(os.environ), secret.reveal()])
    except Refused as refused:
        print(str(refused), file=sys.stderr)
        return 1
    write(args.out, document, files)
    print(f"{args.out}: run {run_id} of {document['process_version']}, {len(files)} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
