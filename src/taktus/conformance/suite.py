"""The suite: W-01 to W-18 against a live worker.

The endpoint is the only required input. The suite reads the worker's capabilities, asks for an
estimate, and then posts up to seven assignments one after the other, each for a purpose:

1. `main` — the worker's default work within a frame that admits every declared capability
   and the hosts the caller names. Proves W-03, W-04, W-05, W-09 and the artifact half of
   W-11; supplies the tool for W-07 and the host for W-13.
2. `narrowed` — the same work in a frame that excludes one tool the main run used. Proves W-07.
3. `narrowed-hosts` — the same work in a frame whose allowed_hosts lacks one host the main run
   reached. Proves W-13.
4. `stopped` — the same work, stopped while a step runs. Proves W-06.
5. `resumed` — the same work resumed from the checkpoint of the stopped run. Proves W-11.
6. `over-limit` — the same work with a limit below the estimate. Proves W-10.
7. `tight` — the same work with one kind's limit equal to the estimate, where the main run's
   actual consumption of that kind exceeded the estimate. The estimate fits, so the worker must
   start (W-10); the running total must then cross the limit, so the worker must halt at a
   boundary and name the limit. Proves W-14. A worker whose actual never exceeded its estimate
   cannot be made to cross a limit its estimate fits, and W-14 is then inconclusive.

Then the suite asks for the state of an id it never posted. The worker must answer `404` with a
problem body. Proves W-16.

Then comes the capacity probe, the one time the suite holds assignments side by side. It posts
as many assignments as the worker declares in `max_concurrent_assignments` (purpose `held`)
and then one more (`one-more`, recorded only when the worker accepts it). The worker must
answer `503` with a problem body and record nothing. Proves W-15. A worker that finishes a held
assignment before the suite has filled its places, or declares more places than the suite
fills, leaves W-15 inconclusive.

Last the suite posts assignments whose id the worker already holds: a fresh one (`repeated`)
again while it runs, and `main` again after it finished. The worker must answer each repeat with
`409` and a problem body, and still hold the first assignment of that id afterwards. Proves
W-17. A repeat the worker accepted appears as `repeated-running` or `repeated-finished`; the
suite stops every assignment of this probe and reads its stream to the end.

Then the same work twice with a command after it (W-18): `after-command` prints a value only
this run knows, which must come back as the artifact the task names, byte for byte, after every
step of the work; `after-command-failing` exits with 1, which must fail the assignment without
that artifact.

W-08 scans everything the suite saw for the value of the credential it referenced by name. W-12
is reported as pending: the removal test needs processes, and the suite has none.

What the worker does inside a step is its own business. The suite sends a generic task unless
the caller supplies one; a worker that needs a real task to do anything is given one with
`--task`, and the hosts that task reaches are named with `--hosts`, so that the main run allows
them and the narrowed run can withdraw one.

Every schema violation in an event is attributed to the check that owns the event type — a bad
`arguments_digest` is a W-09 failure, not a generic one — so that the report names the rule to
fix. Base fields, unknown types and transport faults belong to W-03.
"""

from __future__ import annotations

import base64
import hashlib
import re
import secrets
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from taktus.conformance import rules
from taktus.conformance.client import Response, Stream, WorkerClient
from taktus.conformance.contracts import first_error
from taktus.conformance.findings import Findings
from taktus.conformance.report import CheckResult, Report, RunSummary
from taktus.conformance.rules import CATALOGUE, CHECKS

type Json = dict[str, Any]

DEFAULT_CREDENTIAL = "TAKTUS_CONFORMANCE_CREDENTIAL"
DEFAULT_TASK: Json = {
    "goal": "Conformance run of the worker contract v1: do your default work within the frame.",
    "acceptance": ["the stream ends with assignment.finished"],
    "inputs": {},
}
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
GENEROUS = 1_000_000
MAX_HELD = 16
AFTER_ARTIFACT = "after-output"

# Which check a schema violation in an event belongs to, by event type.
EVENT_OWNER = {
    "consumption.reported": "W-04",
    "step.boundary": "W-05",
    "tool.called": "W-09",
    "artifact.produced": "W-11",
}


@dataclass
class SuiteOptions:
    endpoint: str
    task: Json | None = None
    hosts: Sequence[
        str
    ] = ()  # what the main run's frame allows; the task is expected to reach them
    credential_name: str = DEFAULT_CREDENTIAL
    credential_value: str | None = None  # never written anywhere; only searched for
    worker_log: Path | None = None
    timeout: float = 300.0  # one assignment, start to finish
    idle_timeout: float = 60.0  # between two events
    max_held: int = MAX_HELD  # the most assignments W-15 holds at once to fill a worker


@dataclass
class Run:
    """One assignment the suite posted and everything it observed about it."""

    purpose: str
    assignment: Json
    accepted: Response
    stream: Stream
    final: Response | None = None
    stop_requested: bool = False
    stop: Response | None = None
    artifacts: Response | None = None
    artifact_bytes: dict[str, bytes] = field(default_factory=dict)

    @property
    def id(self) -> str:
        return str(self.assignment["assignment_id"])

    @property
    def events(self) -> list[Json]:
        return self.stream.events

    @property
    def stop_acknowledged(self) -> bool:
        """A stop was requested while the assignment ran and the worker answered `stopping`."""
        state = self.stop.json if self.stop is not None else None
        return self.stop_requested and state is not None and state.get("status") == "stopping"

    @property
    def outcome(self) -> str | None:
        finished = [e for e in self.events if e.get("type") == "assignment.finished"]
        return str(finished[-1].get("outcome")) if finished else None

    def summary(self) -> RunSummary:
        return RunSummary(self.purpose, self.id, self.outcome, len(self.events))

    def texts(self) -> list[tuple[str, str]]:
        """Everything the worker sent for this assignment, as labelled text, for the credential
        scan."""
        out = [("the response to POST /v1/assignments", self.accepted.text)]
        out.extend(("the event stream", text) for text in self.stream.raw)
        for label, response in (
            ("the assignment state", self.final),
            ("the response to POST /stop", self.stop),
            ("the artifact list", self.artifacts),
        ):
            if response is not None:
                out.append((label, response.text))
        out.extend(
            (f"artifact {artifact_id!r}", content.decode("latin-1"))
            for artifact_id, content in self.artifact_bytes.items()
        )
        return out


async def run_suite(options: SuiteOptions) -> Report:
    report = Report(endpoint=options.endpoint, contract=CATALOGUE.contract)
    findings = Findings(CHECKS)
    runs: list[Run] = []
    async with WorkerClient(
        options.endpoint, timeout=options.timeout, idle_timeout=options.idle_timeout
    ) as client:
        try:
            await _health(client, report)
            capabilities = await _w01(client, findings)
            declared = _declared_tools(capabilities)
            estimate = await _w02(client, findings, declared, options)
            fitting = _fitting_limits(capabilities, estimate)

            main = await _run(client, options, "main", declared, fitting)
            runs.append(main)
            await _judge(client, main, estimate, findings)
            await _w03_resume(client, main, findings)
            await _w07(client, options, main, declared, fitting, estimate, findings, runs)
            await _w13(client, options, main, declared, fitting, estimate, findings, runs)
            stopped = await _w06(client, options, main, declared, fitting, estimate, findings, runs)
            await _w11(client, options, stopped, declared, fitting, estimate, findings, runs)
            await _w10(client, options, declared, estimate, findings, runs)
            await _w14(client, options, main, declared, fitting, estimate, findings, runs)
            await _w16(client, findings)
            await _w15(client, options, capabilities, declared, fitting, findings, runs)
            await _w17(client, options, main, declared, fitting, findings, runs)
            await _w18(client, options, declared, fitting, estimate, findings, runs)
        except httpx.HTTPError as error:
            report.notes.append(f"the worker at {options.endpoint} stopped answering: {error!r}")
            if not findings.evidence["W-01"]:
                findings.fail("W-01", f"the worker at {options.endpoint} did not answer: {error!r}")
            for check in CHECKS:
                if check != "W-12" and not findings.evidence[check]:
                    findings.inconclusive.setdefault(
                        check, "not reached: the worker stopped answering (see the notes)"
                    )
    _w08(options, runs, findings)
    _w09(runs, findings)
    for check in CHECKS:
        if check == "W-12":
            report.add(
                CheckResult.pending(
                    "W-12",
                    "not run: the removal test needs processes that use the adapter, and no "
                    "process exists yet; this half of maturity stays pending",
                )
            )
        else:
            report.add(findings.result(check))
    report.runs = [r.summary() for r in runs]
    return report.finish()


# --- preflight, W-01, W-02 ------------------------------------------------------------------------


async def _health(client: WorkerClient, report: Report) -> None:
    response = await client.get("/v1/health")
    body = response.json
    if response.status != 200 or body is None or body.get("status") != "ready":
        report.notes.append(
            f"GET /v1/health answered {response.status} {response.text[:120]!r}; the suite "
            "continued anyway, so a failure below may be a consequence"
        )
    elif (why := first_error("Health", body)) is not None:
        report.notes.append(f"GET /v1/health does not validate against Health: {why}")


async def _w01(client: WorkerClient, findings: Findings) -> Json:
    response = await client.get("/v1/capabilities")
    body = response.json
    if response.status != 200 or body is None:
        findings.fail(
            "W-01", f"GET /v1/capabilities answered {response.status} with {response.text[:120]!r}"
        )
        return {}
    why = first_error("Capabilities", body)
    if why is not None:
        findings.fail("W-01", f"the body does not validate against Capabilities: {why}")
    kinds = body.get("consumption", {}).get("kinds", [])
    if not kinds:
        findings.fail("W-01", "consumption.kinds is empty: no consumption kind declared")
    if why is None and kinds:
        findings.ok(
            "W-01",
            f"declares {len(body.get('capabilities', []))} capabilities and consumption "
            f"kinds {kinds}",
        )
    return body


def _declared_tools(capabilities: Json) -> list[str]:
    tools = capabilities.get("capabilities")
    if isinstance(tools, list) and tools:
        return [str(t) for t in tools]
    return ["shell.script"]


async def _w02(
    client: WorkerClient, findings: Findings, declared: list[str], options: SuiteOptions
) -> Json | None:
    assignment = _assignment(options, declared, {"quota": {"units": GENEROUS}})
    body = {k: assignment[k] for k in ("task", "context", "frame")}
    response = await client.post("/v1/estimate", body)
    estimate = response.json
    if response.status != 200 or estimate is None:
        findings.fail(
            "W-02", f"POST /v1/estimate answered {response.status} with {response.text[:120]!r}"
        )
        return None
    why = first_error("Estimate", estimate)
    if why is not None:
        findings.fail("W-02", f"the body does not validate against Estimate: {why}")
        return None
    findings.ok(
        "W-02",
        f"answered with confidence {estimate['confidence']!r}, {estimate['steps']} step(s), "
        f"{estimate['wall_seconds']}s wall time",
    )
    return estimate


# --- building assignments -----------------------------------------------------------------------


def _assignment(
    options: SuiteOptions,
    allowed: Sequence[str],
    limits: Json,
    *,
    hosts: Sequence[str] | None = None,
    checkpoint_ref: str | None = None,
    after: Json | None = None,
) -> Json:
    """`hosts` None means the hosts the caller named; a list is exactly that list, which is how
    the narrowed run withdraws one. The list is always sent: the affirmative form is the
    contract's, and an empty list is the explicit "nothing". `after` is the task's command
    after the work (W-18), added to whichever task is sent."""
    task: Json = dict(options.task or DEFAULT_TASK)
    if after is not None:
        task["after"] = after
    context: Json = {"workspace": {"kind": "none"}}
    if checkpoint_ref is not None:
        context["checkpoint_ref"] = checkpoint_ref
    frame: Json = {
        "autonomy_level": 2,
        "allowed_tools": list(allowed),
        "allowed_hosts": list(options.hosts if hosts is None else hosts),
        "max_steps": GENEROUS,
    }
    return {
        "assignment_id": "asg_conf_" + secrets.token_hex(6),
        "task": task,
        "context": context,
        "frame": frame,
        "limits": limits,
        "credentials": [{"name": options.credential_name, "injected_as": "env"}],
        "callback": {"events": "sse"},
    }


def _fitting_limits(capabilities: Json, estimate: Json | None) -> Json:
    """Limits comfortably above the estimate, for every kind the worker declares or estimates.
    Without an estimate every limit is simply generous."""
    consumption = capabilities.get("consumption", {})
    kinds = set(consumption.get("kinds", []))
    known = estimate is not None
    estimate = estimate or {}

    def above(amount: float, floor: float) -> float:
        return max(floor, 10.0 * amount) if known else float(GENEROUS)

    limits: Json = {}
    currencies = list(consumption.get("currencies", [])) or list(estimate.get("currency", {}))
    if ("currency" in kinds or "currency" in estimate) and currencies:
        limits["currency"] = {
            code: above(float(estimate.get("currency", {}).get(code, 0)), 1.0)
            for code in currencies
        }
    if "quota" in kinds or "quota_units" in estimate:
        limits["quota"] = {"units": above(float(estimate.get("quota_units", 0)), 1.0)}
    classes = list(consumption.get("resource_classes", []))
    resource_class = estimate.get("resource_class") or (classes[0] if classes else None)
    if ("compute" in kinds or "compute_seconds" in estimate) and resource_class:
        limits["compute"] = {
            "seconds": above(float(estimate.get("compute_seconds", 0)), 60.0),
            "resource_class": resource_class,
        }
    return limits or {"quota": {"units": GENEROUS}}


def _exceeding_limits(estimate: Json) -> tuple[Json, str] | None:
    """Limits with one quantity below the estimate, and which one. None when the estimate is
    zero everywhere, because then no limit can lie below it."""
    for code, amount in estimate.get("currency", {}).items():
        if amount > 0:
            return {"currency": {code: amount / 2}}, f"currency {code} {amount / 2} < {amount}"
    quota = estimate.get("quota_units", 0)
    if quota > 0:
        return {"quota": {"units": quota / 2}}, f"quota {quota / 2} < {quota}"
    compute = estimate.get("compute_seconds", 0)
    if compute > 0 and estimate.get("resource_class"):
        limits = {"compute": {"seconds": compute / 2, "resource_class": estimate["resource_class"]}}
        return limits, f"compute {compute / 2} < {compute} ({estimate['resource_class']})"
    return None


# --- running and judging a stream -------------------------------------------------------------


async def _run(
    client: WorkerClient,
    options: SuiteOptions,
    purpose: str,
    allowed: Sequence[str],
    limits: Json,
    *,
    hosts: Sequence[str] | None = None,
    checkpoint_ref: str | None = None,
    stop_on_step: str | bool | None = False,
    after: Json | None = None,
) -> Run:
    """Post an assignment and read its stream to the end. `stop_on_step` names the step at
    whose start a stop is requested; None means the first step; False means never."""
    assignment = _assignment(
        options, allowed, limits, hosts=hosts, checkpoint_ref=checkpoint_ref, after=after
    )
    accepted = await client.post("/v1/assignments", assignment)
    run = Run(purpose, assignment, accepted, Stream(status=0))
    if accepted.status != 201:
        return run

    async def on_event(event: Json) -> None:
        if stop_on_step is False or run.stop_requested:
            return
        if event.get("type") != "step.started":
            return
        if stop_on_step is not None and event.get("step_id") != stop_on_step:
            return
        run.stop_requested = True
        run.stop = await client.post(
            f"/v1/assignments/{run.id}/stop",
            {"reason": "conformance W-06", "ceiling_seconds": max(1, int(options.timeout))},
        )

    run.stream = await client.stream(run.id, on_event=on_event)
    run.final = await client.get(f"/v1/assignments/{run.id}")
    run.artifacts = await client.get(f"/v1/assignments/{run.id}/artifacts")
    for event in run.events:
        if event.get("type") != "artifact.produced":
            continue
        uri = str(
            event.get("uri") or f"/v1/assignments/{run.id}/artifacts/{event.get('artifact_id')}"
        )
        if uri.startswith(("/", "http://", "https://")):
            status, content = await client.get_bytes(uri)
            if status == 200:
                run.artifact_bytes[str(event.get("artifact_id"))] = content
    return run


async def _judge(client: WorkerClient, run: Run, estimate: Json | None, findings: Findings) -> None:
    """Everything a completed stream proves on its own: transport and schema (W-03 and the
    owning checks), the stream rules, the state endpoint, and the artifact endpoints."""
    where = f"{run.purpose} run {run.id}"
    if run.accepted.status != 201:
        findings.fail(
            "W-03",
            f"{where}: POST /v1/assignments answered {run.accepted.status} "
            f"with {run.accepted.text[:160]!r}",
        )
        return
    state = run.accepted.json or {}
    if (why := first_error("AssignmentState", state)) is not None:
        findings.fail("W-03", f"{where}: the response to POST /v1/assignments is invalid: {why}")
    for problem in run.stream.problems:
        findings.fail("W-03", f"{where}: {problem}")
    if not run.events:
        return

    for message, event in zip(run.stream.messages, run.events, strict=False):
        seq = event.get("seq")
        if message.id != str(seq):
            findings.fail("W-03", f"{where}: SSE id {message.id!r} does not carry seq {seq!r}")
        if message.event != event.get("type"):
            findings.fail(
                "W-03",
                f"{where}: SSE event field {message.event!r} does not carry type "
                f"{event.get('type')!r} (seq {seq})",
            )
        why = first_error("Event", event)
        if why is not None:
            findings.fail(_owner(event), f"{where}: event seq {seq} is invalid: {why}")

    for violation in rules.stream_violations(
        run.assignment, estimate, run.events, stopped=run.stop_acknowledged
    ):
        findings.add(violation, where)

    n = len(run.events)
    final = run.final.json if run.final else None
    if run.final is None or run.final.status != 200 or final is None:
        findings.fail(
            "W-03",
            f"{where}: GET /v1/assignments/{run.id} answered "
            f"{run.final.status if run.final else '-'}",
        )
    else:
        if (why := first_error("AssignmentState", final)) is not None:
            findings.fail("W-03", f"{where}: the assignment state is invalid: {why}")
        elif final.get("status") != "finished" or final.get("outcome") != run.outcome:
            findings.fail(
                "W-03",
                f"{where}: the stream ended with outcome {run.outcome!r} but the state says "
                f"status {final.get('status')!r}, outcome {final.get('outcome')!r}",
            )
        elif final.get("last_seq") != n:
            findings.fail(
                "W-03",
                f"{where}: last_seq is {final.get('last_seq')} but the stream has {n} events",
            )
    _artifacts(run, findings, where)
    findings.ok("W-03", f"{where}: {n} events, seq 1..{n}, outcome {run.outcome!r}")
    if any(e.get("type") == "step.started" for e in run.events):
        steps = sum(1 for e in run.events if e.get("type") == "step.started")
        findings.ok("W-04", f"{where}: consumption reported for each of {steps} step(s) in time")
        findings.ok(
            "W-05",
            f"{where}: {sum(1 for e in run.events if e.get('type') == 'step.boundary')} "
            f"step.boundary event(s)",
        )


def _owner(event: Json) -> str:
    kind = str(event.get("type"))
    if kind == "assignment.finished":
        if event.get("limit") is not None:
            return "W-14"
        return {"stopped": "W-06", "rejected": "W-10"}.get(str(event.get("outcome")), "W-03")
    return EVENT_OWNER.get(kind, "W-03")


def _artifacts(run: Run, findings: Findings, where: str) -> None:
    produced = [e for e in run.events if e.get("type") == "artifact.produced"]
    listing = run.artifacts.json if run.artifacts else None
    if run.artifacts is None or run.artifacts.status != 200 or listing is None:
        findings.fail(
            "W-11",
            f"{where}: GET /v1/assignments/{run.id}/artifacts answered "
            f"{run.artifacts.status if run.artifacts else '-'}",
        )
        return
    if (why := first_error("ArtifactList", listing)) is not None:
        findings.fail("W-11", f"{where}: the artifact list is invalid: {why}")
        return
    listed = {a["id"]: a["digest"] for a in listing.get("artifacts", [])}
    for event in produced:
        artifact_id = str(event.get("artifact_id"))
        digest = str(event.get("digest"))
        if artifact_id not in listed:
            findings.fail(
                "W-11", f"{where}: artifact {artifact_id!r} was announced but is not listed"
            )
        elif listed[artifact_id] != digest:
            findings.fail(
                "W-11",
                f"{where}: artifact {artifact_id!r} is listed with digest "
                f"{listed[artifact_id][:19]}… but was announced with {digest[:19]}…",
            )
        content = run.artifact_bytes.get(artifact_id)
        if content is None:
            findings.fail(
                "W-11", f"{where}: the bytes of artifact {artifact_id!r} could not be fetched"
            )
        elif "sha256:" + hashlib.sha256(content).hexdigest() != digest:
            findings.fail(
                "W-11", f"{where}: the bytes of artifact {artifact_id!r} do not hash to its digest"
            )
    if produced:
        findings.ok(
            "W-11",
            f"{where}: {len(produced)} artifact(s) announced, listed and fetched with "
            "matching digests",
        )


# --- W-03 resume ------------------------------------------------------------------------------


async def _w03_resume(client: WorkerClient, main: Run, findings: Findings) -> None:
    n = len(main.events)
    if n == 0 or findings.violations["W-03"]:
        return
    k = n // 2
    expected = [(e["seq"], e["type"]) for e in main.events[k:]]
    for label, tail in (
        ("Last-Event-ID: ", await client.stream(main.id, last_event_id=k)),
        ("?after=", await client.stream(main.id, after=k)),
    ):
        got = [(e.get("seq"), e.get("type")) for e in tail.events]
        for problem in tail.problems:
            findings.fail("W-03", f"resume with {label}{k}: {problem}")
        if got != expected:
            findings.fail(
                "W-03",
                f"resume with {label}{k} returned seq {[s for s, _ in got]}, "
                f"expected {[s for s, _ in expected]}",
            )
    empty = await client.stream(main.id, last_event_id=n)
    if empty.events:
        findings.fail(
            "W-03",
            f"resume with Last-Event-ID {n} (the last seq) returned "
            f"{len(empty.events)} event(s), expected none",
        )
    if not findings.violations["W-03"]:
        findings.ok("W-03", f"resumes from seq {k} via Last-Event-ID and via ?after=")


# --- W-07 narrowed frame ----------------------------------------------------------------------


async def _w07(
    client: WorkerClient,
    options: SuiteOptions,
    main: Run,
    declared: list[str],
    limits: Json,
    estimate: Json | None,
    findings: Findings,
    runs: list[Run],
) -> None:
    used = [
        str(e.get("tool"))
        for e in main.events
        if e.get("type") == "tool.called" and not e.get("refused", False)
    ]
    if not used:
        findings.inconclusive["W-07"] = (
            "the main run called no tool, so no tool could be placed outside the frame; give "
            "the worker a task that uses a tool (--task)"
        )
        return
    tool = used[0]
    allowed = [t for t in declared if t != tool]
    if not allowed:
        # allowed_tools needs at least one entry; a worker with a single capability is given
        # a capability it does not have, which excludes the one it used just the same.
        allowed = ["conformance.nothing"]
    how = f"removed {tool!r} from allowed_tools"
    run = await _run(client, options, "narrowed", allowed, limits)
    runs.append(run)
    await _judge(client, run, estimate, findings)
    if run.outcome == "rejected":
        findings.inconclusive["W-07"] = (
            f"{how}; the worker rejected the narrowed frame before starting, which the contract "
            "allows, so the refusal path could not be observed"
        )
        return
    attempts = [e for e in run.events if e.get("type") == "tool.called" and e.get("tool") == tool]
    refused = [e for e in attempts if e.get("refused", False)]
    if findings.violations["W-07"]:
        return
    if not attempts:
        findings.inconclusive["W-07"] = (
            f"{how}; the worker never attempted {tool!r} in the narrowed run, so the refusal "
            "could not be observed"
        )
        return
    if not refused:
        findings.fail(
            "W-07",
            f"{how}; the worker called {tool!r} without refused: true (seq {attempts[0]['seq']})",
        )
        return
    findings.ok(
        "W-07",
        f"{how}; the worker emitted tool.called with refused: true for it "
        f"(seq {refused[0]['seq']}) and ended with outcome {run.outcome!r}",
    )


async def _w13(
    client: WorkerClient,
    options: SuiteOptions,
    main: Run,
    declared: list[str],
    limits: Json,
    estimate: Json | None,
    findings: Findings,
    runs: list[Run],
) -> None:
    """The main run's frame allowed exactly the hosts the caller named. A host reached outside
    that list without refusal is already a failure of the main run (the stream rule). Otherwise
    a run whose frame withdraws one reached host must show the refusal."""
    if findings.violations["W-13"]:
        return
    reached = [
        str(e.get("host"))
        for e in main.events
        if e.get("type") == "tool.called" and e.get("host") and not e.get("refused", False)
    ]
    if not reached:
        refused = [
            e
            for e in main.events
            if e.get("type") == "tool.called" and e.get("refused") and e.get("host")
        ]
        if refused:
            findings.ok(
                "W-13",
                f"the main run refused host {refused[0].get('host')!r}, which its frame did not "
                f"allow (seq {refused[0]['seq']})",
            )
            return
        findings.inconclusive["W-13"] = (
            "the main run reached no host, so no host could be placed outside the frame; give "
            "the worker a task that reaches one (--task) and name that host (--hosts)"
        )
        return
    host = reached[0]
    hosts = [h for h in options.hosts if h != host]
    how = f"removed {host!r} from allowed_hosts"
    run = await _run(client, options, "narrowed-hosts", declared, limits, hosts=hosts)
    runs.append(run)
    await _judge(client, run, estimate, findings)
    if run.outcome == "rejected":
        findings.inconclusive["W-13"] = (
            f"{how}; the worker rejected the narrowed frame before starting, which the contract "
            "allows, so the refusal path could not be observed"
        )
        return
    attempts = [e for e in run.events if e.get("type") == "tool.called" and e.get("host") == host]
    refused = [e for e in attempts if e.get("refused", False)]
    if findings.violations["W-13"]:
        return
    if not attempts:
        findings.inconclusive["W-13"] = (
            f"{how}; the worker never named {host!r} in the narrowed run, so the refusal could "
            "not be observed"
        )
        return
    if not refused:
        findings.fail(
            "W-13",
            f"{how}; the worker reached {host!r} without refused: true (seq {attempts[0]['seq']})",
        )
        return
    findings.ok(
        "W-13",
        f"{how}; the worker emitted tool.called with host and refused: true for it "
        f"(seq {refused[0]['seq']}) and ended with outcome {run.outcome!r}",
    )


# --- W-06 stop, W-11 resume -------------------------------------------------------------------


def _stop_target(main: Run) -> str | None:
    """The step at whose start the stop is requested: the step that produced the first artifact,
    so that the resume has something not to repeat — unless that is the last step, or there is
    no artifact, in which case the first step."""
    started = [str(e.get("step_id")) for e in main.events if e.get("type") == "step.started"]
    produced = [str(e.get("step_id")) for e in main.events if e.get("type") == "artifact.produced"]
    if produced and started and produced[0] in started[:-1]:
        return produced[0]
    return None


async def _w06(
    client: WorkerClient,
    options: SuiteOptions,
    main: Run,
    declared: list[str],
    limits: Json,
    estimate: Json | None,
    findings: Findings,
    runs: list[Run],
) -> Run | None:
    if not any(e.get("type") == "step.started" for e in main.events):
        findings.inconclusive["W-06"] = "the main run started no step, so there was nothing to stop"
        return None
    run = await _run(client, options, "stopped", declared, limits, stop_on_step=_stop_target(main))
    runs.append(run)
    await _judge(client, run, estimate, findings)
    if not run.stop_requested:
        findings.inconclusive["W-06"] = (
            "the step chosen for the stop never started in this run, so no stop was requested"
        )
        return None
    stop = run.stop
    if stop is None or stop.status != 202 or stop.json is None:
        findings.fail(
            "W-06",
            f"POST /v1/assignments/{run.id}/stop answered "
            f"{stop.status if stop else '-'} with {stop.text[:120] if stop else ''!r}, "
            "expected 202",
        )
        return None
    if (why := first_error("AssignmentState", stop.json)) is not None:
        findings.fail("W-06", f"the response to POST /stop is invalid: {why}")
        return None
    if stop.json.get("status") == "finished":
        findings.inconclusive["W-06"] = (
            "the assignment had already finished when the stop arrived; the worker ran too fast "
            "for a stop to land mid-run"
        )
        return None
    if not any(e.get("type") == "step.boundary" for e in run.events):
        findings.inconclusive["W-06"] = (
            "the stopped run carried no step.boundary at all (see W-05), so there was no "
            "boundary the stop could take effect at"
        )
        return None
    if findings.violations["W-06"]:
        return None
    final = run.final.json if run.final else {}
    last = run.events[-1]
    if final and final.get("checkpoint_ref") != last.get("checkpoint_ref"):
        findings.fail(
            "W-06",
            f"the state of {run.id} carries checkpoint_ref {final.get('checkpoint_ref')!r}, "
            f"the stream {last.get('checkpoint_ref')!r}",
        )
        return None
    findings.ok(
        "W-06",
        f"stop acknowledged with status {stop.json.get('status')!r}; the run ended at a boundary "
        f"with checkpoint {last.get('checkpoint_ref')!r}",
    )
    return run


async def _w11(
    client: WorkerClient,
    options: SuiteOptions,
    stopped: Run | None,
    declared: list[str],
    limits: Json,
    estimate: Json | None,
    findings: Findings,
    runs: list[Run],
) -> None:
    if stopped is None:
        findings.inconclusive.setdefault(
            "W-11", "no stopped run with a checkpoint to resume from (see W-06)"
        )
        return
    checkpoint = str(stopped.events[-1].get("checkpoint_ref"))
    run = await _run(client, options, "resumed", declared, limits, checkpoint_ref=checkpoint)
    runs.append(run)
    await _judge(client, run, estimate, findings)
    if run.outcome != "succeeded":
        finished = run.events[-1] if run.events else {}
        findings.fail(
            "W-11",
            f"resumed from {checkpoint!r}, the assignment ended with outcome {run.outcome!r}"
            + (f": {finished.get('reason')}" if finished.get("reason") else ""),
        )
        return
    for violation in rules.duplicate_artifacts(stopped.events, run.events):
        findings.add(violation, f"resumed run {run.id}")
    before = sum(1 for e in stopped.events if e.get("type") == "artifact.produced")
    if before == 0:
        findings.inconclusive["W-11"] = (
            "the stopped run produced no artifact before its checkpoint, so a repeat could not "
            "be observed; the resumed run itself was consistent"
        )
        return
    if not findings.violations["W-11"]:
        findings.ok(
            "W-11",
            f"resumed from {checkpoint!r}: {before} artifact(s) before the checkpoint, none "
            "produced again",
            first=True,
        )


# --- W-10 over limit --------------------------------------------------------------------------


async def _w10(
    client: WorkerClient,
    options: SuiteOptions,
    declared: list[str],
    estimate: Json | None,
    findings: Findings,
    runs: list[Run],
) -> None:
    if estimate is None:
        findings.inconclusive["W-10"] = "no estimate to set a limit below (see W-02)"
        return
    exceeding = _exceeding_limits(estimate)
    if exceeding is None:
        findings.inconclusive["W-10"] = (
            "the estimate is zero for every quantity, so no limit can lie below it"
        )
        return
    limits, how = exceeding
    run = await _run(client, options, "over-limit", declared, limits)
    runs.append(run)
    if run.accepted.status != 201:
        findings.fail(
            "W-10",
            f"with {how}, POST /v1/assignments answered {run.accepted.status}: rejection is a "
            "state, not an HTTP error",
        )
        return
    state = run.accepted.json or {}
    if state.get("status") != "finished" or state.get("outcome") != "rejected":
        findings.fail(
            "W-10",
            f"with {how}, the response to POST /v1/assignments has status "
            f"{state.get('status')!r} and outcome {state.get('outcome')!r}, expected "
            "finished/rejected",
        )
    await _judge(client, run, estimate, findings)
    if findings.violations["W-10"]:
        return
    if not state.get("reason") and not run.events[-1].get("reason"):
        findings.fail("W-10", f"with {how}, the rejection carries no reason")
        return
    findings.ok("W-10", f"with {how}, rejected before starting with one event and a reason")


# --- W-14 tight limits ------------------------------------------------------------------------


def _actual(events: Sequence[Json]) -> dict[str, float]:
    """What a stream reported in total, per quantity: tokens_in, tokens_out, quota_units,
    compute_seconds per resource class (`compute_seconds <class>`), currency per code
    (`currency <code>`)."""
    totals: dict[str, float] = {}

    def add(name: str, amount: Any) -> None:
        totals[name] = totals.get(name, 0.0) + float(amount)

    for event in (e for e in events if e.get("type") == "consumption.reported"):
        for quantity in ("tokens_in", "tokens_out", "quota_units"):
            if quantity in event:
                add(quantity, event[quantity])
        if "compute_seconds" in event:
            add(f"compute_seconds {event.get('resource_class')}", event["compute_seconds"])
        for code, amount in (event.get("currency") or {}).items():
            add(f"currency {code}", amount)
    return totals


def _overrun(estimate: Json, actual: dict[str, float]) -> tuple[str, Json, str] | None:
    """The first quantity the worker used more of than it estimated: the limit kind, that
    kind's limit set to the estimate, and how, with the numbers. Tokens first — a budget is
    enforced in tokens (ADR-0005) — and money last, because a worker may learn it only at the
    end of an assignment. None when the actual stayed within the estimate everywhere."""
    tokens = {
        direction: int(estimate.get(f"tokens_{direction}", 0))
        for direction in ("in", "out")
        if int(estimate.get(f"tokens_{direction}", 0)) >= 1
    }
    for direction, amount in tokens.items():
        used = actual.get(f"tokens_{direction}", 0.0)
        if used > amount:
            how = f"tokens {direction} set to the estimate {amount}; the main run used {used:g}"
            return "tokens", {"tokens": dict(tokens)}, how
    quota = float(estimate.get("quota_units", 0))
    if quota > 0 and actual.get("quota_units", 0.0) > quota:
        used = actual["quota_units"]
        return (
            "quota",
            {"quota": {"units": quota}},
            (f"quota set to the estimate {quota:g} units; the main run used {used:g}"),
        )
    compute = float(estimate.get("compute_seconds", 0))
    resource_class = estimate.get("resource_class")
    used = actual.get(f"compute_seconds {resource_class}", 0.0)
    if compute > 0 and resource_class and used > compute:
        limits = {"compute": {"seconds": compute, "resource_class": resource_class}}
        return (
            "compute",
            limits,
            (
                f"compute set to the estimate {compute:g}s of {resource_class}; the main run used "
                f"{used:g}s"
            ),
        )
    for code, amount in (estimate.get("currency") or {}).items():
        used = actual.get(f"currency {code}", 0.0)
        if amount > 0 and used > amount:
            return (
                "currency",
                {"currency": {code: amount}},
                (f"currency set to the estimate {amount:g} {code}; the main run used {used:g}"),
            )
    return None


def _estimated_and_used(estimate: Json, actual: dict[str, float]) -> str:
    parts = []
    for quantity in ("tokens_in", "tokens_out", "quota_units"):
        if quantity in estimate:
            used = actual.get(quantity, 0.0)
            parts.append(f"{quantity} {estimate[quantity]:g} estimated, {used:g} used")
    if "compute_seconds" in estimate:
        used = actual.get(f"compute_seconds {estimate.get('resource_class')}", 0.0)
        parts.append(f"compute_seconds {estimate['compute_seconds']:g} estimated, {used:g} used")
    for code, amount in (estimate.get("currency") or {}).items():
        parts.append(f"{code} {amount:g} estimated, {actual.get(f'currency {code}', 0):g} used")
    return "; ".join(parts) or "the estimate names no quantity"


async def _w14(
    client: WorkerClient,
    options: SuiteOptions,
    main: Run,
    declared: list[str],
    fitting: Json,
    estimate: Json | None,
    findings: Findings,
    runs: list[Run],
) -> None:
    """The limits are the worker's hard ceiling. A limit equal to the estimate is one the
    worker must accept (W-10); where the main run used more of a quantity than estimated, the
    same work under that limit must cross it, and the worker must halt at a boundary instead
    of starting another step. The stream rule judges the halt; this names the situation."""
    if estimate is None:
        findings.inconclusive["W-14"] = "no estimate to set a limit to (see W-02)"
        return
    actual = _actual(main.events)
    overrun = _overrun(estimate, actual)
    if overrun is None:
        findings.inconclusive["W-14"] = (
            "the main run's actual consumption never exceeded the estimate "
            f"({_estimated_and_used(estimate, actual)}), so no limit the estimate fits can be "
            "crossed, and a halt at the limit cannot be provoked"
        )
        return
    kind, tightened, how = overrun
    limits = {**fitting, **tightened}
    run = await _run(client, options, "tight", declared, limits)
    runs.append(run)
    await _judge(client, run, estimate, findings)
    if findings.violations["W-14"]:
        return
    finished = run.events[-1] if run.events else {}
    totals = rules.running_totals(run.events, tightened)
    reached = ", ".join(
        f"{name} {totals[name]:g} of {ceiling:g}"
        for name, (_, ceiling) in rules.ceilings(tightened).items()
    )
    if run.outcome == "rejected":
        findings.inconclusive["W-14"] = (
            f"{how}; the worker rejected the assignment although its estimate fits the limit "
            f"({finished.get('reason')}), so no halt could be observed"
        )
        return
    if run.outcome == "failed" and main.outcome == "succeeded":
        findings.fail(
            "W-14",
            f"{how}; the tight run ended failed ({finished.get('reason')}) where the main run "
            f"succeeded: a limit halts the assignment at a boundary with outcome stopped, it "
            f"does not fail it (running total {reached})",
        )
        return
    if run.outcome != "stopped" or not finished.get("limit"):
        findings.inconclusive["W-14"] = (
            f"{how}; the tight run ended {run.outcome!r} without naming a limit, and no step "
            f"started after its running total reached the limit ({reached}): nothing remained "
            "to be withheld, so the halt could not be observed"
        )
        return
    boundaries = [e for e in run.events if e.get("type") == "step.boundary"]
    if not boundaries:
        findings.inconclusive["W-14"] = (
            f"{how}; the tight run carried no step.boundary at all (see W-05), so there was no "
            "boundary the halt could take effect at"
        )
        return
    final = run.final.json if run.final else {}
    if final and final.get("checkpoint_ref") != finished.get("checkpoint_ref"):
        findings.fail(
            "W-14",
            f"the state of {run.id} carries checkpoint_ref {final.get('checkpoint_ref')!r}, "
            f"the stream {finished.get('checkpoint_ref')!r}",
        )
        return
    findings.ok(
        "W-14",
        f"{how}; the worker halted at the boundary of step {boundaries[-1].get('step_id')!r} "
        f"(seq {boundaries[-1]['seq']}) with checkpoint {finished.get('checkpoint_ref')!r}, "
        f"named the limit {finished.get('limit')!r} and started no further step (running "
        f"total {reached})"
        + ("" if finished.get("limit") == kind else f"; the limit tightened was {kind!r}"),
    )


# --- W-15 capacity ----------------------------------------------------------------------------

ACCEPTED = (200, 201, 202)


async def _w15(
    client: WorkerClient,
    options: SuiteOptions,
    capabilities: Json,
    declared: list[str],
    limits: Json,
    findings: Findings,
    runs: list[Run],
) -> None:
    """Hold as many assignments as the worker declares, post one more, and judge the answer
    (`rules.capacity_violations`). Every assignment posted here is stopped afterwards and its
    stream read to the end, so that W-08 and W-09 see it and the worker is left idle."""
    capacity = capabilities.get("max_concurrent_assignments")
    if not isinstance(capacity, int) or isinstance(capacity, bool) or capacity < 1:
        findings.inconclusive["W-15"] = (
            "the capabilities declare no max_concurrent_assignments (see W-01), so there are no "
            "places to fill"
        )
        return
    if capacity > options.max_held:
        findings.inconclusive["W-15"] = (
            f"the worker declares {capacity} places and the suite fills at most "
            f"{options.max_held}; for the conformance run, start the worker so that it declares "
            f"max_concurrent_assignments of {options.max_held} or fewer"
        )
        return
    posted: list[Run] = []
    try:
        why = await _fill(client, options, capacity, declared, limits, posted)
        if why is not None:
            findings.inconclusive["W-15"] = why
            return
        extra = _assignment(options, declared, limits)
        answer = await client.post("/v1/assignments", extra)
        if answer.status in ACCEPTED:
            posted.append(Run("one-more", extra, answer, Stream(status=0)))
        states = [await client.get(f"/v1/assignments/{run.id}") for run in posted[:capacity]]
        probe: Json = {
            "max_concurrent_assignments": capacity,
            "held": [state.json or {} for state in states],
            "answer": {"status": answer.status, "body": answer.body},
        }
        # A lookup shows that nothing was recorded only where the worker answers an id it does
        # not hold with 404. Where W-16 failed it does not, and that failure is W-16's alone.
        looked_up = answer.status == 503 and not findings.failed("W-16")
        if looked_up:
            lookup = await client.get(f"/v1/assignments/{extra['assignment_id']}")
            probe["lookup"] = lookup.status
        for violation in rules.capacity_violations(probe):
            findings.add(violation, "capacity probe")
        if findings.violations["W-15"]:
            return
        still = sum(1 for state in probe["held"] if state.get("status") != "finished")
        if answer.status != 503:
            findings.inconclusive["W-15"] = (
                f"the worker accepted one more, but {capacity - still} of the {capacity} held "
                "assignment(s) had finished by then, so it may have had a free place; "
                + _LONGER.format(n=capacity + 1)
            )
            return
        findings.ok(
            "W-15",
            f"holding {still} of {capacity} declared assignment(s), the worker answered one more "
            f"with 503 ({(answer.json or {}).get('title')!r}) and "
            + (
                "recorded nothing"
                if looked_up
                else "was not looked up, because it does not answer an unknown id with 404 (W-16)"
            ),
        )
    finally:
        await _release(client, options, posted, runs, "W-15: the capacity probe is over")


_LONGER = (
    "make the worker's default work last longer than posting {n} assignments takes, or give it "
    "a task that does (--task)"
)


async def _fill(
    client: WorkerClient,
    options: SuiteOptions,
    capacity: int,
    declared: list[str],
    limits: Json,
    posted: list[Run],
) -> str | None:
    """Post `capacity` assignments. None when every one was accepted and none had finished;
    otherwise why the places could not be filled."""
    for index in range(1, capacity + 1):
        assignment = _assignment(options, declared, limits)
        accepted = await client.post("/v1/assignments", assignment)
        if accepted.status not in ACCEPTED:
            return (
                f"the worker answered assignment {index} of the {capacity} it declares with "
                f"{accepted.status}, so its places could not be filled; it may hold assignments "
                "the suite did not post: run the suite against an idle worker"
            )
        posted.append(Run("held", assignment, accepted, Stream(status=0)))
        state = accepted.json or {}
        if state.get("status") == "finished":
            return (
                f"the worker finished assignment {index} of {capacity} at once (outcome "
                f"{state.get('outcome')!r}: {state.get('reason')}), so its places could not be "
                "filled"
            )
    for run in posted:
        state = (await client.get(f"/v1/assignments/{run.id}")).json or {}
        if state.get("status") == "finished":
            return (
                f"a held assignment finished before all {capacity} places were filled; "
                + _LONGER.format(n=capacity + 1)
            )
    return None


async def _release(
    client: WorkerClient, options: SuiteOptions, posted: list[Run], runs: list[Run], why: str
) -> None:
    """Stop every assignment the probe posted that may still run, and read every stream to its
    end."""
    for run in posted:
        if (run.accepted.json or {}).get("status") == "finished":
            continue
        run.stop_requested = True
        run.stop = await client.post(
            f"/v1/assignments/{run.id}/stop",
            {
                "reason": f"conformance {why}",
                "ceiling_seconds": max(1, int(options.timeout)),
            },
        )
    for run in posted:
        run.stream = await client.stream(run.id)
        run.final = await client.get(f"/v1/assignments/{run.id}")
        runs.append(run)


# --- W-16, W-17 an assignment's id ------------------------------------------------------------


async def _w16(client: WorkerClient, findings: Findings) -> None:
    """Ask for the state of an id the suite never posted (`rules.unknown_id_violations`)."""
    unknown = "asg_conf_" + secrets.token_hex(6)
    answer = await client.get(f"/v1/assignments/{unknown}")
    probe: Json = {
        "assignment_id": unknown,
        "answer": {"status": answer.status, "body": answer.body},
    }
    for violation in rules.unknown_id_violations(probe):
        findings.add(violation, "unknown-id probe")
    if not findings.failed("W-16"):
        findings.ok(
            "W-16",
            f"the state of {unknown}, never posted, answered 404 "
            f"({(answer.json or {}).get('title')!r})",
        )


async def _w17(
    client: WorkerClient,
    options: SuiteOptions,
    main: Run,
    declared: list[str],
    limits: Json,
    findings: Findings,
    runs: list[Run],
) -> None:
    """Post an assignment whose id the worker holds, twice: once while it runs, and once for
    `main`, which has finished. Judge each answer and what the worker holds afterwards
    (`rules.repeated_id_violations`). Every assignment posted here is stopped afterwards and its
    stream read to the end, so that W-08 and W-09 see it and the worker is left idle."""
    posted: list[Run] = []
    observed: list[str] = []
    missing: list[str] = []
    try:
        assignment = _assignment(options, declared, limits)
        accepted = await client.post("/v1/assignments", assignment)
        if accepted.status in ACCEPTED and accepted.json is not None:
            posted.append(Run("repeated", assignment, accepted, Stream(status=0)))
            await _repeat(client, assignment, accepted.json, "running", findings, posted, observed)
        else:
            missing.append(
                f"the worker answered the assignment to be repeated with {accepted.status}, so "
                "no running assignment could be repeated; run the suite against an idle worker"
            )
        final = main.final.json if main.final is not None else None
        if main.accepted.status == 201 and final is not None and final.get("status") == "finished":
            await _repeat(client, main.assignment, final, "finished", findings, posted, observed)
        else:
            missing.append("the main run did not finish, so no finished assignment was repeated")
    finally:
        await _release(client, options, posted, runs, "W-17: the repeated-id probe is over")
    if findings.failed("W-17"):
        return
    for line in observed:
        findings.ok("W-17", line)
    if missing:
        findings.inconclusive["W-17"] = "; ".join(missing)


async def _repeat(
    client: WorkerClient,
    assignment: Json,
    held: Json,
    which: str,
    findings: Findings,
    posted: list[Run],
    observed: list[str],
) -> None:
    answer = await client.post("/v1/assignments", assignment)
    if answer.status in ACCEPTED:
        posted.append(Run(f"repeated-{which}", assignment, answer, Stream(status=0)))
    after = await client.get(f"/v1/assignments/{assignment['assignment_id']}")
    probe: Json = {
        "held": held,
        "answer": {"status": answer.status, "body": answer.body},
        "after": after.json or {},
    }
    for violation in rules.repeated_id_violations(probe):
        findings.add(violation, f"repeated-id probe ({which})")
    observed.append(
        f"a repeat of {assignment['assignment_id']} while it was {which} answered 409 "
        f"({(answer.json or {}).get('title')!r}); the worker still holds the first"
    )


# --- W-18 the command after the work ----------------------------------------------------------


async def _w18(
    client: WorkerClient,
    options: SuiteOptions,
    declared: list[str],
    limits: Json,
    estimate: Json | None,
    findings: Findings,
    runs: list[Run],
) -> None:
    """The same work twice with a command after it. The first prints a value only this run
    knows, which must come back as the named artifact, byte for byte, after every step of the
    work. The second exits with 1, which must fail the assignment without the artifact. Both
    commands are POSIX utilities a worker's host has: `printf` and `false`."""
    nonce = "taktus-conformance-" + secrets.token_hex(8)
    expected = f"{nonce}\n".encode()
    printed = await _run(
        client,
        options,
        "after-command",
        declared,
        limits,
        after={"command": ["printf", "%s\\n", nonce], "artifact": AFTER_ARTIFACT},
    )
    runs.append(printed)
    await _judge(client, printed, estimate, findings)
    where = f"after-command run {printed.id}"
    if printed.outcome != "succeeded":
        finished = printed.events[-1] if printed.events else {}
        findings.fail(
            "W-18",
            f"{where}: with a command after the work, the assignment ended with outcome "
            f"{printed.outcome!r}"
            + (f": {finished.get('reason')}" if finished.get("reason") else ""),
        )
        return
    content = printed.artifact_bytes.get(AFTER_ARTIFACT)
    if content is None:
        if not findings.failed("W-18"):
            findings.fail("W-18", f"{where}: the artifact {AFTER_ARTIFACT!r} could not be fetched")
        return
    if content != expected:
        findings.fail(
            "W-18",
            f"{where}: the artifact {AFTER_ARTIFACT!r} is {content[:80]!r}, the command printed "
            f"{expected!r}",
        )
        return

    failing = await _run(
        client,
        options,
        "after-command-failing",
        declared,
        limits,
        after={"command": ["false"], "artifact": AFTER_ARTIFACT},
    )
    runs.append(failing)
    await _judge(client, failing, estimate, findings)
    where = f"after-command-failing run {failing.id}"
    if failing.outcome != "failed":
        findings.fail(
            "W-18",
            f"{where}: a command after the work that exits with 1 must fail the assignment; it "
            f"ended with outcome {failing.outcome!r}",
        )
        return
    if any(
        e.get("type") == "artifact.produced" and e.get("artifact_id") == AFTER_ARTIFACT
        for e in failing.events
    ):
        findings.fail(
            "W-18",
            f"{where}: the command after the work exited with 1 and its artifact "
            f"{AFTER_ARTIFACT!r} was produced all the same",
        )
        return
    if not findings.failed("W-18"):
        findings.ok(
            "W-18",
            f"the command after the work ran last and its output came back as {AFTER_ARTIFACT!r} "
            "byte for byte; a command that exited with 1 failed the assignment without it",
        )


# --- W-08, W-09 across all runs ---------------------------------------------------------------


def _w08(options: SuiteOptions, runs: list[Run], findings: Findings) -> None:
    value = options.credential_value
    if not value:
        findings.inconclusive["W-08"] = (
            f"no credential value to look for: set {options.credential_name} to the same random "
            "value in the worker's environment and in the suite's, then run again"
        )
        return
    needles = {
        "in clear": value,
        "base64": base64.b64encode(value.encode()).decode(),
    }
    places: list[tuple[str, str]] = []
    for run in runs:
        places.extend(
            (f"{label} of the {run.purpose} run {run.id}", text) for label, text in run.texts()
        )
    if options.worker_log is not None:
        try:
            places.append(("the worker log", options.worker_log.read_text(errors="replace")))
        except OSError as error:
            findings.inconclusive["W-08"] = f"the worker log could not be read: {error}"
    hits: list[str] = []
    for where, text in places:
        for form, needle in needles.items():
            if needle in text:
                hits.append(f"the value of {options.credential_name} appears {form} in {where}")
    for hit in dict.fromkeys(hits):
        findings.fail("W-08", hit)
    if not hits and "W-08" not in findings.inconclusive:
        scanned = f"{len(places)} response(s), stream(s) and artifact(s)"
        if options.worker_log is not None:
            scanned += " and the worker log"
        findings.ok(
            "W-08",
            f"{options.credential_name} was referenced by name; its value appears in none of "
            f"{scanned}",
        )


def _w09(runs: list[Run], findings: Findings) -> None:
    calls = [e for run in runs for e in run.events if e.get("type") == "tool.called"]
    if not calls:
        findings.inconclusive.setdefault(
            "W-09",
            "no tool.called was observed in any run; give the worker a task that uses a tool",
        )
        return
    for event in calls:
        digest = str(event.get("arguments_digest", ""))
        if not DIGEST.match(digest):
            findings.fail(
                "W-09",
                f"tool.called seq {event.get('seq')} of {event.get('assignment_id')} carries "
                f"arguments_digest {digest[:40]!r}, not sha256: plus 64 hex characters",
            )
    if not findings.violations["W-09"]:
        findings.ok("W-09", f"{len(calls)} tool.called event(s), every arguments_digest a sha256")
