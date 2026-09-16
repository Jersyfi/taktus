"""The suite: W-01 to W-12 against a live worker.

The endpoint is the only required input. The suite reads the worker's capabilities, asks for an
estimate, and then posts up to five assignments, each for a purpose:

1. `main` — the worker's default work within a frame that admits every declared capability.
   Proves W-03, W-04, W-05, W-09 and the artifact half of W-11; supplies the tool for W-07.
2. `narrowed` — the same work in a frame that excludes one tool the main run used. Proves W-07.
3. `stopped` — the same work, stopped while a step runs. Proves W-06.
4. `resumed` — the same work resumed from the checkpoint of the stopped run. Proves W-11.
5. `over-limit` — the same work with a limit below the estimate. Proves W-10.

W-08 scans everything the suite saw for the value of the credential it referenced by name. W-12
is reported as pending: the removal test needs processes, and the suite has none.

What the worker does inside a step is its own business. The suite sends a generic task unless
the caller supplies one; a worker that needs a real task to do anything is given one with
`--task`.

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
from taktus.conformance.report import CheckResult, Report, RunSummary
from taktus.conformance.rules import CHECKS, Violation

type Json = dict[str, Any]

DEFAULT_CREDENTIAL = "TAKTUS_CONFORMANCE_CREDENTIAL"
DEFAULT_TASK: Json = {
    "goal": "Conformance run of the worker contract v1: do your default work within the frame.",
    "acceptance": ["the stream ends with assignment.finished"],
    "inputs": {},
}
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
GENEROUS = 1_000_000

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
    credential_name: str = DEFAULT_CREDENTIAL
    credential_value: str | None = None  # never written anywhere; only searched for
    worker_log: Path | None = None
    timeout: float = 300.0  # one assignment, start to finish
    idle_timeout: float = 60.0  # between two events


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


class Findings:
    """Violations and evidence per check, from every run, folded into results at the end."""

    def __init__(self) -> None:
        self.violations: dict[str, list[str]] = {c: [] for c in CHECKS}
        self.evidence: dict[str, list[str]] = {c: [] for c in CHECKS}
        self.inconclusive: dict[str, str] = {}

    def add(self, violation: Violation, where: str) -> None:
        self.violations[violation.check].append(f"{where}: {violation.message}")

    def fail(self, check: str, message: str) -> None:
        self.violations[check].append(message)

    def ok(self, check: str, message: str, *, first: bool = False) -> None:
        if first:
            self.evidence[check].insert(0, message)
        else:
            self.evidence[check].append(message)

    def result(self, check: str) -> CheckResult:
        if self.violations[check]:
            return CheckResult.failed(
                check, self.violations[check][0], self.violations[check][1:] + self.evidence[check]
            )
        if check in self.inconclusive:
            return CheckResult.inconclusive(check, self.inconclusive[check], self.evidence[check])
        if self.evidence[check]:
            return CheckResult.passed(check, self.evidence[check][0], self.evidence[check][1:])
        return CheckResult.inconclusive(check, "the suite never reached this check")


async def run_suite(options: SuiteOptions) -> Report:
    report = Report(endpoint=options.endpoint)
    findings = Findings()
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

            main = await _run(client, options, "main", declared, [], fitting)
            runs.append(main)
            await _judge(client, main, estimate, findings)
            await _w03_resume(client, main, findings)
            await _w07(client, options, main, declared, fitting, estimate, findings, runs)
            stopped = await _w06(client, options, main, declared, fitting, estimate, findings, runs)
            await _w11(client, options, stopped, declared, fitting, estimate, findings, runs)
            await _w10(client, options, declared, estimate, findings, runs)
        except httpx.HTTPError as error:
            findings.fail("W-01", f"the worker at {options.endpoint} did not answer: {error!r}")
            for check in CHECKS:
                if check not in {"W-01", "W-12"}:
                    findings.inconclusive.setdefault(
                        check, "not reached: the worker stopped answering (see W-01)"
                    )
    _w08(options, runs, findings)
    _w09(runs, findings)
    findings.inconclusive.setdefault("W-12", "")
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
    assignment = _assignment(options, declared, [], {"quota": {"units": GENEROUS}})
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
    forbidden: Sequence[str],
    limits: Json,
    *,
    checkpoint_ref: str | None = None,
) -> Json:
    context: Json = {"workspace": {"kind": "none"}}
    if checkpoint_ref is not None:
        context["checkpoint_ref"] = checkpoint_ref
    frame: Json = {"autonomy_level": 2, "allowed_tools": list(allowed), "max_steps": GENEROUS}
    if forbidden:
        frame["forbidden"] = list(forbidden)
    return {
        "assignment_id": "asg_conf_" + secrets.token_hex(6),
        "task": options.task or DEFAULT_TASK,
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
    forbidden: Sequence[str],
    limits: Json,
    *,
    checkpoint_ref: str | None = None,
    stop_on_step: str | bool | None = False,
) -> Run:
    """Post an assignment and read its stream to the end. `stop_on_step` names the step at
    whose start a stop is requested; None means the first step; False means never."""
    assignment = _assignment(options, allowed, forbidden, limits, checkpoint_ref=checkpoint_ref)
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
        run.assignment, estimate, run.events, stopped=run.stop_requested
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
    remaining = [t for t in declared if t != tool]
    if remaining:
        allowed, forbidden, how = remaining, [], f"removed {tool!r} from allowed_tools"
    else:
        allowed, forbidden, how = [tool], [tool], f"listed {tool!r} under forbidden"
    run = await _run(client, options, "narrowed", allowed, forbidden, limits)
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
    run = await _run(
        client, options, "stopped", declared, [], limits, stop_on_step=_stop_target(main)
    )
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
    run = await _run(client, options, "resumed", declared, [], limits, checkpoint_ref=checkpoint)
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
    run = await _run(client, options, "over-limit", declared, [], limits)
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
