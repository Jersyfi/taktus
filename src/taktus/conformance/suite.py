"""The suite: W-01 to W-21 against a live worker.

The endpoint is the only required input. The suite reads the worker's capabilities, asks for an
estimate, and then posts up to seven assignments one after the other, each for a purpose:

1. `main` — the worker's default work within a frame that admits every declared capability
   and the hosts the caller names. Proves W-03, W-04, W-05, W-09 and the artifact half of
   W-11; supplies the tool for W-07 and the host for W-13.
2. `narrowed` — the same work in a frame that excludes one tool the main run used. Proves W-07:
   the worker refuses the tool when it calls it, or states in `reach.stated` that it did not
   offer it and calls it nowhere (ADR-0098).
3. `narrowed-hosts` — the same work in a frame whose allowed_hosts lacks one host the main run
   reached. Proves W-13 the same way, by a refusal or by a statement whose hosts leave it out.
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
that artifact. Then the same work twice with a command before it: `before-command` prints a
value only this run knows, which must come back as the artifact the task names, produced by the
first step, with the work after it; `before-command-failing` exits with 1, which must fail the
assignment before any step of the work starts.

Then the work once more, sent a message while its first step runs (`steered`), and the message
again under the same id: a worker that declares steering accepts both and receives the message
once, at a boundary; one that does not refuses it (W-19). Then the work handed over while its
first step runs (`handed-over`): a worker that declares handover ends it at a boundary with a
`handover.state` document, from which the work is continued (`continued`); one that does not
refuses the request, and the work runs on (W-20).

W-08 scans everything the suite saw for the value of the credential it referenced by name. W-12
is reported as pending: the removal test needs processes, and the suite has none.

With `listen` the suite serves the outbound binding itself (`relay.py`) instead of calling an
endpoint: it waits for the worker to connect, runs every check above over the binding, and
judges the binding itself as W-21. Against an endpoint, W-21 is reported as pending.

What the worker does inside a step is its own business. The suite sends a generic task unless
the caller supplies one; a worker that needs a real task to do anything is given one with
`--task`, and the hosts that task reaches are named with `--hosts`, so that the main run allows
them and the narrowed run can withdraw one.

Every schema violation in an event is attributed to the check that owns the event type — a bad
`arguments_digest` is a W-09 failure, not a generic one — so that the report names the rule to
fix. Base fields, unknown types and transport faults belong to W-03.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import re
import secrets
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from taktus.conformance import rules
from taktus.conformance.client import Response, Stream, WorkerClient
from taktus.conformance.contracts import first_error
from taktus.conformance.findings import Findings
from taktus.conformance.relay import RelayHost
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
BEFORE_ARTIFACT = "before-output"

# Which check a schema violation in an event belongs to, by event type.
EVENT_OWNER = {
    "reach.stated": "W-07",
    "consumption.reported": "W-04",
    "step.boundary": "W-05",
    "tool.called": "W-09",
    "artifact.produced": "W-11",
    "message.received": "W-19",
}
CONNECT_SECONDS = 60.0
"""How long the suite with `listen` waits for the worker to connect."""


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
    listen: str | None = None
    """`host:port` where the suite serves the outbound binding for a worker that connects to
    it; `endpoint` is then only the label of the report (README §8)."""
    connect_timeout: float = CONNECT_SECONDS


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
    messages: list[Json] = field(default_factory=list)
    """The steering messages the worker accepted, each with the `last_seq` its answer named."""
    message_answers: list[Response] = field(default_factory=list)
    handover: Response | None = None
    handover_requested: bool = False
    """A handover was requested while the assignment ran and the worker answered `stopping`."""

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
            ("the response to POST /handover", self.handover),
            ("the artifact list", self.artifacts),
            *(("the response to POST /messages", r) for r in self.message_answers),
        ):
            if response is not None:
                out.append((label, response.text))
        out.extend(
            (f"artifact {artifact_id!r}", content.decode("latin-1"))
            for artifact_id, content in self.artifact_bytes.items()
        )
        return out


async def run_suite(options: SuiteOptions) -> Report:
    host = RelayHost(options.listen) if options.listen else None
    if host is not None:
        await host.start()
    try:
        return await _suite(options, host)
    finally:
        if host is not None:
            await host.close()


async def _suite(options: SuiteOptions, host: RelayHost | None) -> Report:
    endpoint = options.endpoint if host is None else f"{host.base} (outbound binding)"
    report = Report(endpoint=endpoint, contract=CATALOGUE.contract)
    findings = Findings(CHECKS)
    runs: list[Run] = []
    async with WorkerClient(
        options.endpoint if host is None else "http://worker.relay",
        timeout=options.timeout,
        idle_timeout=options.idle_timeout,
        transport=None if host is None else host.transport(),
    ) as client:
        try:
            if host is not None:
                await _connected(host, options, report)
            await _health(client, report)
            capabilities = await _w01(client, findings)
            declared = _declared_tools(capabilities)
            estimate = await _w02(client, findings, declared, options, capabilities)
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
            await _w18_before(client, options, declared, fitting, estimate, findings, runs)
            await _w19(
                client, options, capabilities, main, declared, fitting, estimate, findings, runs
            )
            await _w20(
                client, options, capabilities, main, declared, fitting, estimate, findings, runs
            )
        except httpx.HTTPError as error:
            report.notes.append(f"the worker at {endpoint} stopped answering: {error!r}")
            if not findings.evidence["W-01"]:
                findings.fail("W-01", f"the worker at {endpoint} did not answer: {error!r}")
            for check in CHECKS:
                if check not in ("W-12", "W-21") and not findings.evidence[check]:
                    findings.inconclusive.setdefault(
                        check, "not reached: the worker stopped answering (see the notes)"
                    )
    _w08(options, runs, findings)
    _w09(runs, findings)
    if host is not None:
        _w21(host, findings)
    for check in CHECKS:
        if check == "W-12":
            report.add(
                CheckResult.pending(
                    "W-12",
                    "not run: the removal test needs processes that use the adapter, and no "
                    "process exists yet; this half of maturity stays pending",
                )
            )
        elif check == "W-21" and host is None:
            report.add(
                CheckResult.pending(
                    "W-21",
                    "not run: the suite called the worker at an endpoint, so the outbound "
                    "binding was not in use; run the suite with --listen and the worker "
                    "connected to it to check the binding",
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
    client: WorkerClient,
    findings: Findings,
    declared: list[str],
    options: SuiteOptions,
    capabilities: Json,
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
    estimator = capabilities.get("estimator")
    if isinstance(estimator, dict):
        yielded = declared_estimate(estimator, body["task"])
        short = below(yielded, estimate)
        if short:
            findings.fail(
                "W-02",
                f"the declared {estimator.get('kind')} estimator yields less than the answer of "
                f"POST /v1/estimate for the same request: {', '.join(short)}",
            )
            return estimate
    findings.ok(
        "W-02",
        f"answered with confidence {estimate['confidence']!r}, {estimate['steps']} step(s), "
        f"{estimate['wall_seconds']}s wall time"
        + (
            f"; its declared {estimator.get('kind')} estimator yields no less"
            if isinstance(estimator, dict)
            else ""
        ),
    )
    return estimate


def declared_estimate(estimator: Json, task: Json) -> Json:
    """What a declared estimator yields for a task (contracts/worker/v1 §5): `fixed` its
    estimate; `per_item` its `each` once per item of `task.inputs[input]`, else `otherwise`."""
    if estimator.get("kind") == "fixed":
        return dict(estimator.get("estimate") or {})
    items = (task.get("inputs") or {}).get(estimator.get("input"))
    if not isinstance(items, list) or not items:
        return dict(estimator.get("otherwise") or {})
    each: Json = _times(dict(estimator.get("each") or {}), len(items))
    return each


def _times(value: Any, n: int) -> Any:
    if isinstance(value, bool | str):
        return value
    if isinstance(value, int | float):
        return value * n
    if isinstance(value, dict):
        return {key: _times(item, n) for key, item in value.items()}
    return value


def below(declared: Json, answered: Json, path: str = "") -> list[str]:
    """Every quantity of the worker's answer that the declared estimate does not reach, as
    `name: declared < answered`; the confidence and the count of steps describe and are not
    held."""
    short: list[str] = []
    for name, value in answered.items():
        if not path and name in ("confidence", "steps", "resource_class"):
            continue
        where = f"{path}{name}"
        mine = declared.get(name) if isinstance(declared, dict) else None
        if isinstance(value, dict):
            short += below(mine if isinstance(mine, dict) else {}, value, f"{where}.")
        elif isinstance(value, int | float) and not isinstance(value, bool):
            held = mine if isinstance(mine, int | float) else 0
            if held + 1e-6 < value:
                short.append(f"{where}: {held} < {value}")
    return short


# --- building assignments -----------------------------------------------------------------------


def _assignment(
    options: SuiteOptions,
    allowed: Sequence[str],
    limits: Json,
    *,
    hosts: Sequence[str] | None = None,
    checkpoint_ref: str | None = None,
    after: Json | None = None,
    before: Json | None = None,
    handover: Json | None = None,
) -> Json:
    """`hosts` None means the hosts the caller named; a list is exactly that list, which is how
    the narrowed run withdraws one. The list is always sent: the affirmative form is the
    contract's, and an empty list is the explicit "nothing". `after` is the task's command
    after the work (W-18), added to whichever task is sent; `before` the command before it.
    `handover` is a handover document the assignment continues from (W-20)."""
    task: Json = dict(options.task or DEFAULT_TASK)
    if before is not None:
        task["before"] = before
    if after is not None:
        task["after"] = after
    context: Json = {"workspace": {"kind": "none"}}
    if checkpoint_ref is not None:
        context["checkpoint_ref"] = checkpoint_ref
    if handover is not None:
        context["handover"] = handover
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
    stop_on_artifact: bool = False,
    after: Json | None = None,
    before: Json | None = None,
    handover: Json | None = None,
    also: Callable[[Run, Json], Awaitable[None]] | None = None,
) -> Run:
    """Post an assignment and read its stream to the end. `stop_on_step` names the step at
    whose start a stop is requested; None means the first step; False means never.
    `stop_on_artifact` requests it instead when the first artifact is announced. `also` runs
    for every event while the stream is open, after the stop: how a message is sent or a
    handover requested mid-run."""
    assignment = _assignment(
        options,
        allowed,
        limits,
        hosts=hosts,
        checkpoint_ref=checkpoint_ref,
        after=after,
        before=before,
        handover=handover,
    )
    accepted = await client.post("/v1/assignments", assignment)
    run = Run(purpose, assignment, accepted, Stream(status=0))
    if accepted.status != 201:
        return run

    async def on_event(event: Json) -> None:
        await stop(event)
        if also is not None:
            await also(run, event)

    async def stop(event: Json) -> None:
        if stop_on_step is False or run.stop_requested:
            return
        if stop_on_artifact:
            if event.get("type") != "artifact.produced":
                return
        elif event.get("type") != "step.started":
            return
        elif stop_on_step is not None and event.get("step_id") != stop_on_step:
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
        run.assignment,
        estimate,
        run.events,
        stopped=run.stop_acknowledged,
        messages=run.messages,
        handover_requested=run.handover_requested,
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
        if event.get("handover") is not None:
            return "W-20"
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
        statement = rules.not_offered(run.events, tool=tool)
        if statement is not None:
            findings.ok(
                "W-07",
                f"{how}; the worker did not offer {tool!r}: its reach.stated (seq "
                f"{statement['seq']}) leaves it out, no call to it occurred, and the run ended "
                f"with outcome {run.outcome!r}",
            )
            return
        findings.inconclusive["W-07"] = (
            f"{how}; the worker never attempted {tool!r} in the narrowed run and stated no "
            "reach that leaves it out, so the refusal could not be observed; a worker that "
            "does not offer a tool outside the frame says so in reach.stated"
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
        statement = rules.not_offered(run.events, host=host)
        if statement is not None:
            findings.ok(
                "W-13",
                f"{how}; the worker did not put {host!r} within reach: its reach.stated (seq "
                f"{statement['seq']}) names only {statement.get('hosts')}, no call named it, "
                f"and the run ended with outcome {run.outcome!r}",
            )
            return
        findings.inconclusive["W-13"] = (
            f"{how}; the worker never named {host!r} in the narrowed run and stated no reach "
            "that leaves it out, so the refusal could not be observed; a worker that puts no "
            "tool that reaches a host within reach says so in reach.stated with its hosts"
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


STOP_ATTEMPTS = 4
"""How often the suite runs the work to stop it, at most: once, and again each time the stop
came too late (#551)."""


def _stop_came_too_late(run: Run, main: Run) -> bool:
    """The stop was requested and answered, but could not be what the checks need: the
    assignment had finished by the time it arrived, or it ended at a boundary before any artifact
    the main run produced was announced. Both depend on how fast the suite's request reaches the
    worker, not on the worker: a machine under load delays the request by more than the work
    lasts. A stop that was never requested, was refused, or met a stream without a boundary is
    the worker's to answer for and is not repeated."""
    stop = run.stop
    if not run.stop_requested or stop is None or stop.status != 202 or stop.json is None:
        return False
    if stop.json.get("status") == "finished":
        return True
    wanted = any(e.get("type") == "artifact.produced" for e in main.events)
    announced = any(e.get("type") == "artifact.produced" for e in run.events)
    return wanted and not announced and any(e.get("type") == "step.boundary" for e in run.events)


async def _stopped_run(
    client: WorkerClient,
    options: SuiteOptions,
    main: Run,
    declared: list[str],
    limits: Json,
) -> Run:
    """The work again, stopped so that the resume has something not to repeat. Where the main run
    produced an artifact before its last step, the stop is requested when the stopped run
    announces its first artifact, not at a step or a time chosen beforehand: which step ends up
    holding a change depends on timing, and an artifact announced is the one thing the stop can
    then not precede. Otherwise it is requested at the first step. A stop that comes too late is
    no evidence either way (W-06 and W-11 would both end inconclusive on the speed of the
    machine), so the work is run again, up to `STOP_ATTEMPTS` times in all; the last run is the
    one the checks judge."""
    on_artifact = _stop_target(main) is not None
    run = await _run(
        client,
        options,
        "stopped",
        declared,
        limits,
        stop_on_step=None,
        stop_on_artifact=on_artifact,
    )
    for _ in range(STOP_ATTEMPTS - 1):
        if not _stop_came_too_late(run, main):
            break
        run = await _run(
            client,
            options,
            "stopped",
            declared,
            limits,
            stop_on_step=None,
            stop_on_artifact=on_artifact,
        )
    return run


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
    run = await _stopped_run(client, options, main, declared, limits)
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


async def _w18_before(
    client: WorkerClient,
    options: SuiteOptions,
    declared: list[str],
    limits: Json,
    estimate: Json | None,
    findings: Findings,
    runs: list[Run],
) -> None:
    """The same work twice with a command before it (ADR-0100). The first prints a value only
    this run knows, which must come back as the named artifact, produced by the first step,
    with the work's steps after it. The second exits with 1, which must fail the assignment
    with no step after the command's. Both commands are POSIX utilities: `printf` and `false`."""
    nonce = "taktus-conformance-" + secrets.token_hex(8)
    expected = f"{nonce}\n".encode()
    printed = await _run(
        client,
        options,
        "before-command",
        declared,
        limits,
        before={"command": ["printf", "%s\\n", nonce], "artifact": BEFORE_ARTIFACT},
    )
    runs.append(printed)
    await _judge(client, printed, estimate, findings)
    where = f"before-command run {printed.id}"
    if printed.outcome != "succeeded":
        finished = printed.events[-1] if printed.events else {}
        findings.fail(
            "W-18",
            f"{where}: with a command before the work, the assignment ended with outcome "
            f"{printed.outcome!r}"
            + (f": {finished.get('reason')}" if finished.get("reason") else ""),
        )
        return
    content = printed.artifact_bytes.get(BEFORE_ARTIFACT)
    if content is None:
        if not findings.failed("W-18"):
            findings.fail("W-18", f"{where}: the artifact {BEFORE_ARTIFACT!r} could not be fetched")
        return
    if content != expected:
        findings.fail(
            "W-18",
            f"{where}: the artifact {BEFORE_ARTIFACT!r} is {content[:80]!r}, the command printed "
            f"{expected!r}",
        )
        return
    started = [e.get("step_id") for e in printed.events if e.get("type") == "step.started"]
    if len(started) < 2:
        findings.fail(
            "W-18",
            f"{where}: no step of the work started after the command before it; steps {started}",
        )
        return

    failing = await _run(
        client,
        options,
        "before-command-failing",
        declared,
        limits,
        before={"command": ["false"], "artifact": BEFORE_ARTIFACT},
    )
    runs.append(failing)
    await _judge(client, failing, estimate, findings)
    where = f"before-command-failing run {failing.id}"
    if failing.outcome != "failed":
        findings.fail(
            "W-18",
            f"{where}: a command before the work that exits with 1 must fail the assignment; it "
            f"ended with outcome {failing.outcome!r}",
        )
        return
    started = [e.get("step_id") for e in failing.events if e.get("type") == "step.started"]
    if len(started) > 1:
        findings.fail(
            "W-18",
            f"{where}: the command before the work exited with 1 and the work started all the "
            f"same: steps {started}",
        )
        return
    if not findings.failed("W-18"):
        findings.ok(
            "W-18",
            f"the command before the work ran first and its output came back as "
            f"{BEFORE_ARTIFACT!r}; a command before the work that exited with 1 failed the "
            "assignment before the work started",
        )


# --- W-19 steering, W-20 handover, W-21 the outbound binding ------------------------------------


async def _connected(host: RelayHost, options: SuiteOptions, report: Report) -> None:
    """Wait for the worker to connect to the binding; a worker that never does is one that
    does not answer."""
    try:
        await asyncio.wait_for(host.connected.wait(), options.connect_timeout)
    except TimeoutError as error:
        raise httpx.ConnectError(
            f"no worker connected to {host.base} within {options.connect_timeout:.0f}s"
        ) from error
    report.notes.append(
        f"the worker connected to {host.base}; every check ran over the outbound binding"
    )


async def _w19(
    client: WorkerClient,
    options: SuiteOptions,
    capabilities: Json,
    main: Run,
    declared: list[str],
    limits: Json,
    estimate: Json | None,
    findings: Findings,
    runs: list[Run],
) -> None:
    """A message while the first step runs, and the same message again. A worker that
    declares steering accepts both and receives the message once, at a boundary; one that does
    not refuses it and runs on."""
    declares = bool((capabilities.get("supports") or {}).get("steering"))
    message: Json = {
        "message_id": "msg_conf_" + secrets.token_hex(6),
        "text": "Conformance W-19: a message to the running assignment. It asks for nothing.",
    }

    async def send(run: Run, event: Json) -> None:
        if run.message_answers or event.get("type") != "step.started":
            return
        path = f"/v1/assignments/{run.id}/messages"
        first = await client.post(path, message)
        run.message_answers.append(first)
        state = first.json or {}
        if first.status == 202 and isinstance(state.get("last_seq"), int):
            run.messages.append(
                {"message_id": message["message_id"], "accepted_at_seq": state["last_seq"]}
            )
            run.message_answers.append(await client.post(path, message))

    run = await _run(client, options, "steered", declared, limits, also=send)
    runs.append(run)
    await _judge(client, run, estimate, findings)
    if run.accepted.status != 201:
        return
    where = f"steered run {run.id}"
    if not run.message_answers:
        findings.inconclusive["W-19"] = (
            "the steered run started no step, so no message could be sent while it ran"
        )
        return
    first = run.message_answers[0]
    if not declares:
        if first.status < 400:
            findings.fail(
                "W-19",
                f"{where}: the worker declares no steering, but answered a message with "
                f"{first.status} instead of refusing it",
            )
        elif run.outcome != main.outcome:
            findings.fail(
                "W-19",
                f"{where}: after a refused message the run ended {run.outcome!r}, the same work "
                f"without one {main.outcome!r}: the refusal changed the assignment",
            )
        elif not findings.violations["W-19"]:
            findings.ok(
                "W-19",
                f"{where}: declares no steering; a message to the running assignment was "
                f"refused with {first.status}, nothing was received, and the run ended "
                f"{run.outcome!r} as without it",
            )
        return
    state = first.json
    if first.status != 202 or state is None:
        findings.fail(
            "W-19",
            f"{where}: a message to the running assignment answered {first.status} with "
            f"{first.text[:120]!r}, expected 202",
        )
        return
    if (why := first_error("AssignmentState", state)) is not None:
        findings.fail("W-19", f"{where}: the answer to the message is invalid: {why}")
        return
    if state.get("status") == "finished":
        findings.inconclusive["W-19"] = (
            "the assignment had already finished when the message arrived; the worker ran too "
            "fast for a message to land mid-run"
        )
        return
    again = run.message_answers[1] if len(run.message_answers) > 1 else None
    if again is None or again.status != 202:
        findings.fail(
            "W-19",
            f"{where}: the same message posted again answered "
            f"{again.status if again else '-'}, expected 202",
        )
        return
    if findings.violations["W-19"]:
        return
    if not any(e.get("type") == "step.boundary" for e in run.events):
        findings.inconclusive["W-19"] = (
            "the steered run carried no step.boundary at all (see W-05), so there was no "
            "boundary the message could be received at"
        )
        return
    received = [e for e in run.events if e.get("type") == "message.received"]
    if not received:
        findings.inconclusive["W-19"] = (
            f"the steered run ended {run.outcome!r} before a boundary at which the message "
            "could be received"
        )
        return
    findings.ok(
        "W-19",
        f"{where}: a message accepted at seq {state.get('last_seq')} and posted again was "
        f"received once, at seq {received[0].get('seq')}, at the boundary of step "
        f"{received[0].get('step_id')!r}",
    )


async def _w20(
    client: WorkerClient,
    options: SuiteOptions,
    capabilities: Json,
    main: Run,
    declared: list[str],
    limits: Json,
    estimate: Json | None,
    findings: Findings,
    runs: list[Run],
) -> None:
    """A handover requested while the first step runs. A worker that declares handover ends
    the assignment at a boundary with a `handover.state` document, from which a new
    assignment continues the work; one that does not refuses it and runs on."""
    declares = bool((capabilities.get("supports") or {}).get("handover"))

    async def hand_over(run: Run, event: Json) -> None:
        if run.handover is not None or event.get("type") != "step.started":
            return
        run.handover = await client.post(
            f"/v1/assignments/{run.id}/handover",
            {"reason": "conformance W-20", "ceiling_seconds": max(1, int(options.timeout))},
        )
        state = run.handover.json or {}
        run.handover_requested = (
            declares and run.handover.status == 202 and state.get("status") == "stopping"
        )

    run = await _run(client, options, "handed-over", declared, limits, also=hand_over)
    runs.append(run)
    await _judge(client, run, estimate, findings)
    if run.accepted.status != 201:
        return
    where = f"handed-over run {run.id}"
    answer = run.handover
    if answer is None:
        findings.inconclusive["W-20"] = (
            "the handed-over run started no step, so no handover could be requested while it ran"
        )
        return
    if not declares:
        if answer.status < 400:
            findings.fail(
                "W-20",
                f"{where}: the worker declares no handover, but answered the request with "
                f"{answer.status} instead of refusing it",
            )
        elif run.outcome != main.outcome:
            findings.fail(
                "W-20",
                f"{where}: after a refused handover the run ended {run.outcome!r}, the same "
                f"work without one {main.outcome!r}: the refusal changed the assignment",
            )
        elif not findings.violations["W-20"]:
            findings.ok(
                "W-20",
                f"{where}: declares no handover; the request was refused with {answer.status}, "
                f"and the run ended {run.outcome!r} as without it",
            )
        return
    state = answer.json
    if answer.status != 202 or state is None:
        findings.fail(
            "W-20",
            f"{where}: POST /handover answered {answer.status} with {answer.text[:120]!r}, "
            "expected 202",
        )
        return
    if (why := first_error("AssignmentState", state)) is not None:
        findings.fail("W-20", f"{where}: the answer to POST /handover is invalid: {why}")
        return
    if state.get("status") == "finished":
        findings.inconclusive["W-20"] = (
            "the assignment had already finished when the handover was requested; the worker "
            "ran too fast for a handover to land mid-run"
        )
        return
    if findings.violations["W-20"] or not run.events:
        return
    if not any(e.get("type") == "step.boundary" for e in run.events):
        findings.inconclusive["W-20"] = (
            "the handed-over run carried no step.boundary at all (see W-05), so there was no "
            "boundary the handover could take effect at"
        )
        return
    document = _handover_document(run, where, findings)
    if document is None:
        return
    continued = await _run(client, options, "continued", declared, limits, handover=document)
    runs.append(continued)
    await _judge(client, continued, estimate, findings)
    if continued.outcome != "succeeded":
        finished = continued.events[-1] if continued.events else {}
        findings.fail(
            "W-20",
            f"continued from the handover of {run.id}, the assignment ended with outcome "
            f"{continued.outcome!r}"
            + (f": {finished.get('reason')}" if finished.get("reason") else ""),
        )
        return
    if not findings.violations["W-20"]:
        findings.ok(
            "W-20",
            f"{where}: handed over at a boundary with checkpoint "
            f"{document['checkpoint_ref']!r}; the document validates and lists "
            f"{len(document['steps'])} step(s) done and {len(document['artifacts'])} "
            f"artifact(s); continued from it as {continued.id}, the work succeeded without "
            "repeating either",
        )


def _handover_document(run: Run, where: str, findings: Findings) -> Json | None:
    """The handover document of a handed-over run, read from its artifact and checked against
    the run: the shape `Handover`, the assignment, the checkpoint, and every other artifact the
    run produced. None, with the failure recorded, when any of it does not hold."""
    last = run.events[-1]
    named = str(last.get("handover"))
    content = run.artifact_bytes.get(named)
    if content is None:
        findings.fail("W-20", f"{where}: the bytes of the handover artifact {named!r} were not had")
        return None
    try:
        document = json.loads(content)
    except ValueError:
        findings.fail("W-20", f"{where}: the handover artifact {named!r} is not JSON")
        return None
    if not isinstance(document, dict):
        findings.fail("W-20", f"{where}: the handover artifact {named!r} is not a JSON object")
        return None
    if (why := first_error("Handover", document)) is not None:
        findings.fail("W-20", f"{where}: the handover document is invalid: {why}")
        return None
    if document.get("assignment_id") != run.id:
        findings.fail(
            "W-20",
            f"{where}: the handover document names {document.get('assignment_id')!r}, not the "
            "assignment it was handed over from",
        )
        return None
    if document.get("checkpoint_ref") != last.get("checkpoint_ref"):
        findings.fail(
            "W-20",
            f"{where}: the handover document names checkpoint {document.get('checkpoint_ref')!r}, "
            f"the assignment ended at {last.get('checkpoint_ref')!r}",
        )
        return None
    listed = {(a.get("id"), a.get("digest")) for a in document.get("artifacts", [])}
    missing = [
        e.get("artifact_id")
        for e in run.events
        if e.get("type") == "artifact.produced"
        and e.get("kind") != "handover.state"
        and (e.get("artifact_id"), e.get("digest")) not in listed
    ]
    if missing:
        findings.fail(
            "W-20",
            f"{where}: the handover document does not list artifact(s) {missing} the "
            "assignment produced before it",
        )
        return None
    return document


def _w21(host: RelayHost, findings: Findings) -> None:
    """The binding itself: every request relayed was answered exactly once, with a status."""
    probe = host.probe()
    if not probe["relayed"]:
        findings.inconclusive["W-21"] = "no request was relayed: no worker connected"
        return
    for violation in rules.relay_violations(probe):
        findings.add(violation, f"over the outbound binding at {host.base}")
    if not findings.violations["W-21"]:
        findings.ok(
            "W-21",
            f"{len(probe['relayed'])} request(s) relayed over the outbound binding, each "
            "answered exactly once with a status",
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
