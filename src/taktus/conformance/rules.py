"""The stream rules of the worker contract: what a whole event stream must satisfy.

A stream rule cannot be expressed in JSON Schema because it concerns the order and the
completeness of events, not the shape of one. These are the executable reading of the checks
W-03 to W-07, W-10, W-11, W-13, W-14 and W-18 of contracts/worker/v1/README.md §7. They take a
transcript — the assignment, the estimate the worker gave for it, and every event in order — and
return every violation found, each naming its check. Three rules concern no stream. W-15 judges a
capacity probe — the assignments the suite held, and the answer to one more
(`capacity_violations`). W-16 judges the answer to the state of an id the worker never received
(`unknown_id_violations`). W-17 judges the answer to an assignment whose id the worker already
holds, and what it holds afterwards (`repeated_id_violations`).

The same functions serve two callers: the gate under tests/conformance, which applies them to the
fixtures under contracts/worker/v1/examples/transcript, and the live suite, which applies them to
the streams it collects from a running worker. Nothing here does I/O.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from taktus.conformance.catalogue import Catalogue
from taktus.conformance.findings import Violation

type Json = dict[str, Any]

CHECKS: dict[str, str] = {
    "W-01": "capabilities returns valid schema and declares at least one consumption kind",
    "W-02": "estimate answers even at confidence low",
    "W-03": "events carry a gapless seq; the stream resumes from seq",
    "W-04": "consumption.reported appears per step, not only at the end",
    "W-05": "step.boundary appears at least once per assignment",
    "W-06": "stop takes effect at a step boundary with a checkpoint set",
    "W-07": "a tool outside allowed_tools is refused, not ignored",
    "W-08": "no credential appears in an event, artifact or log",
    "W-09": "tool.called transmits arguments hashed, never in clear",
    "W-10": "exceeding limits yields rejected before starting, not an abort afterwards",
    "W-11": "resuming from a checkpoint produces no duplicate artifact",
    "W-12": "the adapter passes the removal test: removing it breaks no process",
    "W-13": "a host outside allowed_hosts is refused, not ignored",
    "W-14": "a running total that would cross limits halts the assignment at its next step "
    "boundary",
    "W-15": "a worker holding max_concurrent_assignments answers one more with 503",
    "W-16": "the state of an assignment id the worker never received answers 404",
    "W-17": "an assignment whose id the worker holds answers 409 and starts no second one",
    "W-18": "a task's command after the work runs once the work is done, and its standard "
    "output is the artifact it names, byte for byte",
}

# Where the README states each rule. A failure cites this so that the reader can look it up.
SECTIONS: dict[str, str] = {
    "W-01": "§2 Capabilities",
    "W-02": "§5 Estimation",
    "W-03": "§4 Events",
    "W-04": "§4 Events",
    "W-05": "§4 Events",
    "W-06": "§6 Stopping",
    "W-07": "§3 Assignment and §4 Events",
    "W-08": "§3 Assignment",
    "W-09": "§4 Events",
    "W-10": "§3 Assignment",
    "W-11": "§3 Assignment and §4 Events",
    "W-12": "§7 Conformance",
    "W-13": "§3 Assignment and §4 Events",
    "W-14": "§6 Stopping",
    "W-15": "§2 Capabilities",
    "W-16": "§3 Assignment",
    "W-17": "§3 Assignment",
    "W-18": "§3 Assignment",
}

REQUIREMENTS: dict[str, str] = {
    "W-01": "GET /v1/capabilities answers 200 with a body that validates against "
    "Worker.json#/$defs/Capabilities and lists at least one consumption kind",
    "W-02": "POST /v1/estimate answers 200 with a body that validates against "
    "Worker.json#/$defs/Estimate; confidence, wall_seconds and steps are always present",
    "W-03": "every event validates against Worker.json#/$defs/Event; seq starts at 1 and "
    "increases by exactly 1; the SSE id field carries seq and the SSE event field carries type; "
    "the stream ends with assignment.finished; a client that sends the last seq it has seen in "
    "Last-Event-ID or as ?after= receives exactly the events after it",
    "W-04": "every step that started has a consumption.reported with its step_id before the next "
    "step starts; a worker that only settles up at the end makes admission control impossible",
    "W-05": "at least one step.boundary per assignment that was not rejected; each names a step "
    "that started",
    "W-06": "after POST /stop is acknowledged the running step finishes, the worker emits "
    "step.boundary and then assignment.finished with outcome stopped and the same checkpoint_ref; "
    "no step starts after that boundary; GET /v1/assignments/{id} agrees",
    "W-07": "a tool.called for a tool outside allowed_tools carries refused: true and is not "
    "executed",
    "W-08": "a credential referenced by name in the assignment never appears — as its value — in "
    "any event, in any artifact, in the assignment state, or in the worker's log",
    "W-09": "every tool.called carries arguments_digest as sha256: followed by 64 lowercase hex "
    "characters, and no argument in clear",
    "W-10": "an assignment whose estimate exceeds its limits is answered with status finished "
    "and outcome rejected, and its stream carries exactly one event, assignment.finished with "
    "outcome rejected and a reason",
    "W-11": "an assignment resumed from a checkpoint_ref produces no artifact that was produced "
    "before that checkpoint; every artifact.produced appears in GET /artifacts with the same "
    "digest, and its bytes hash to it",
    "W-12": "removing the adapter changes quality or cost but breaks no process",
    "W-13": "a tool.called that reaches a host names it in host; a host outside the frame's "
    "allowed_hosts carries refused: true and is not reached — an absent or empty list allows "
    "no host at all",
    "W-14": "no step starts once the reported running total of a limited kind has reached its "
    "limit; an assignment halted by a limit ends stopped at the boundary it is at, with that "
    "boundary's checkpoint_ref, and names the limit in assignment.finished",
    "W-15": "a worker that holds as many assignments as max_concurrent_assignments declares "
    "answers a further POST /v1/assignments with 503 and a problem body — a JSON object with a "
    "title and status 503 — and records nothing: GET /v1/assignments/{id} of that assignment "
    "answers 404",
    "W-16": "GET /v1/assignments/{id} of an id the worker never received answers 404 with a "
    "problem body — a JSON object with a title and status 404",
    "W-17": "a POST /v1/assignments whose assignment_id the worker already holds, running or "
    "finished, answers 409 with a problem body — a JSON object with a title and status 409 — "
    "and starts nothing: the assignment of that id is still the first, with its accepted_at, "
    "its stream not begun again and, once finished, its outcome",
    "W-18": "an assignment whose task names a command after the work runs that command in its "
    "workspace as its last step, after every step of the work: a succeeded assignment carries "
    "exactly one artifact.produced with the artifact_id the task names, no step starts after "
    "it, and its bytes are the command's standard output; a command that exits with anything "
    "but 0 fails the assignment, and the artifact is not produced",
}

CATALOGUE = Catalogue.build(
    "worker/v1",
    "contracts/worker/v1/README.md",
    CHECKS,
    REQUIREMENTS,
    SECTIONS,
    unrunnable=frozenset({"W-12"}),
)


def outside_frame(tool: str, frame: Json) -> bool:
    """True when the frame does not admit the tool: it is not in allowed_tools."""
    return tool not in set(frame.get("allowed_tools", []))


def host_outside_frame(host: str, frame: Json) -> bool:
    """True when the frame does not admit the host: it is not in allowed_hosts. An absent or
    empty list allows no host at all (§3)."""
    return host not in set(frame.get("allowed_hosts") or [])


def exceeds_limits(estimate: Json, limits: Json) -> str | None:
    """The first quantity of the estimate that lies above its limit, or None when all fit."""
    for code, amount in estimate.get("currency", {}).items():
        ceiling = limits.get("currency", {}).get(code)
        if ceiling is not None and amount > ceiling:
            return f"currency {code} {amount} > {ceiling}"
    if "quota" in limits and estimate.get("quota_units", 0) > limits["quota"]["units"]:
        return f"quota {estimate['quota_units']} > {limits['quota']['units']}"
    compute = limits.get("compute")
    if compute and estimate.get("resource_class") == compute["resource_class"]:
        if estimate.get("compute_seconds", 0) > compute["seconds"]:
            return f"compute {estimate['compute_seconds']} > {compute['seconds']}"
    for direction in ("in", "out"):
        ceiling = limits.get("tokens", {}).get(direction)
        amount = estimate.get(f"tokens_{direction}", 0)
        if ceiling is not None and amount > ceiling:
            return f"tokens {direction} {amount} > {ceiling}"
    return None


def ceilings(limits: Json) -> dict[str, tuple[str, float]]:
    """Every quantity the limits bound, by the name a running total is kept under, with the
    limit kind it belongs to and its ceiling."""
    out: dict[str, tuple[str, float]] = {}
    for code, amount in limits.get("currency", {}).items():
        out[f"currency {code}"] = ("currency", float(amount))
    if "quota" in limits:
        out["quota units"] = ("quota", float(limits["quota"]["units"]))
    if "compute" in limits:
        compute = limits["compute"]
        out[f"compute seconds in {compute['resource_class']}"] = (
            "compute",
            float(compute["seconds"]),
        )
    for direction in ("in", "out"):
        if direction in limits.get("tokens", {}):
            out[f"tokens {direction}"] = ("tokens", float(limits["tokens"][direction]))
    return out


def reported(event: Json, limits: Json) -> dict[str, float]:
    """The quantities of one consumption.reported that count against the limits, by the names
    `ceilings` keeps them under."""
    out: dict[str, float] = {}
    for code, amount in (event.get("currency") or {}).items():
        out[f"currency {code}"] = float(amount)
    if "quota_units" in event:
        out["quota units"] = float(event["quota_units"])
    compute = limits.get("compute")
    if compute and "compute_seconds" in event:
        if event.get("resource_class") == compute["resource_class"]:
            out[f"compute seconds in {compute['resource_class']}"] = float(event["compute_seconds"])
    for direction in ("in", "out"):
        if f"tokens_{direction}" in event:
            out[f"tokens {direction}"] = float(event[f"tokens_{direction}"])
    return out


def running_totals(events: Sequence[Json], limits: Json) -> dict[str, float]:
    """What the stream reported in total, per quantity the limits bound."""
    totals = dict.fromkeys(ceilings(limits), 0.0)
    for event in (e for e in events if e.get("type") == "consumption.reported"):
        for name, amount in reported(event, limits).items():
            if name in totals:
                totals[name] += amount
    return totals


def limit_violations(
    assignment: Json, events: Sequence[Json], *, stop_requested: bool
) -> list[Violation]:
    """W-14: the limits are the worker's hard ceiling. Once the reported running total of a
    limited quantity has reached its limit, no further step starts. An assignment that names
    the limit that halted it ends stopped — the boundary part is `stop_violations` — and names
    a kind its limits set; one that ends stopped after reaching a limit, without a stop being
    requested, names the limit."""
    out: list[Violation] = []
    limits = assignment["limits"]
    bounds = ceilings(limits)
    totals = dict.fromkeys(bounds, 0.0)
    reached: tuple[str, int] | None = None
    for event in events:
        kind = event.get("type")
        if kind == "consumption.reported":
            for name, amount in reported(event, limits).items():
                if name in totals:
                    totals[name] += amount
            if reached is None:
                for name, (_, ceiling) in bounds.items():
                    if totals[name] >= ceiling:
                        reached = (name, int(event["seq"]))
                        break
        elif kind == "step.started" and reached is not None:
            name, seq = reached
            out.append(
                Violation(
                    "W-14",
                    f"step {event.get('step_id')!r} started (seq {event['seq']}) after the "
                    f"running total of {name} had reached its limit of {bounds[name][1]:g} "
                    f"(seq {seq}): the worker did not halt at the boundary",
                )
            )
            break
    finished = [e for e in events if e.get("type") == "assignment.finished"]
    if not finished:
        return out
    last = finished[-1]
    named = last.get("limit")
    if named is not None:
        if last.get("outcome") != "stopped":
            out.append(
                Violation(
                    "W-14",
                    f"assignment.finished names the limit {named!r} with outcome "
                    f"{last.get('outcome')!r}: only a halted assignment names one, and it ends "
                    "stopped",
                )
            )
        if named not in limits:
            out.append(
                Violation(
                    "W-14",
                    f"assignment.finished names the limit {named!r}, which the assignment's "
                    f"limits do not set (they set {sorted(limits)})",
                )
            )
    elif last.get("outcome") == "stopped" and reached is not None and not stop_requested:
        out.append(
            Violation(
                "W-14",
                f"the running total of {reached[0]} reached its limit and the assignment ended "
                "stopped without a stop being requested, but assignment.finished names no limit",
            )
        )
    return out


def stream_violations(
    assignment: Json,
    estimate: Json | None,
    events: Sequence[Json],
    *,
    stopped: bool = False,
) -> list[Violation]:
    """Every stream rule the transcript breaks. `stopped` says that a stop was requested and
    acknowledged while the assignment ran, which is when W-06 has something to check; a fixture
    that ends in `stopped` implies it."""
    out: list[Violation] = []
    if not events:
        return [Violation("W-03", "the stream carried no event at all")]
    assignment_id = assignment["assignment_id"]
    frame = assignment["frame"]

    foreign = [e.get("seq") for e in events if e.get("assignment_id") != assignment_id]
    if foreign:
        out.append(Violation("W-03", f"events {foreign} carry a foreign assignment_id"))

    seqs = [e.get("seq") for e in events]
    if seqs != list(range(1, len(events) + 1)):
        out.append(Violation("W-03", f"seq is not gapless from 1: {seqs}"))

    last = events[-1]
    finished = [e for e in events if e.get("type") == "assignment.finished"]
    if last.get("type") != "assignment.finished":
        out.append(Violation("W-03", "the last event is not assignment.finished"))
    if len(finished) > 1:
        out.append(Violation("W-03", "assignment.finished appears more than once"))
    if not finished:
        return out
    last = finished[0]
    outcome = last.get("outcome")

    excess = exceeds_limits(estimate, assignment["limits"]) if estimate else None
    if excess and (outcome != "rejected" or len(events) != 1):
        out.append(
            Violation(
                "W-10",
                f"the estimate exceeds the limits ({excess}) but the stream did not reject "
                f"before starting: outcome {outcome!r} after {len(events)} event(s)",
            )
        )
    if outcome == "rejected":
        if len(events) != 1:
            out.append(
                Violation(
                    "W-10",
                    f"a rejected assignment emits exactly one event, this stream has {len(events)}",
                )
            )
        return out

    started = [e["step_id"] for e in events if e.get("type") == "step.started" and "step_id" in e]
    if len(started) > frame["max_steps"]:
        out.append(
            Violation(
                "W-10",
                f"{len(started)} steps started but the frame allows {frame['max_steps']}; "
                "a frame that cannot be honoured is rejected before starting",
            )
        )

    out.extend(consumption_violations(events, started))

    boundaries = [e for e in events if e.get("type") == "step.boundary"]
    if not boundaries:
        out.append(Violation("W-05", "no step.boundary in the stream"))
    unknown = sorted({str(e.get("step_id")) for e in boundaries} - set(started))
    if unknown:
        out.append(Violation("W-05", f"step.boundary for step(s) {unknown} that never started"))

    if (stopped or outcome == "stopped") and boundaries:
        # A halt at a limit has the shape of a requested stop; its faults are W-14's.
        check = "W-14" if last.get("limit") and not stopped else "W-06"
        out.extend(stop_violations(events, last, boundaries, check=check))
    out.extend(limit_violations(assignment, events, stop_requested=stopped))

    for event in (e for e in events if e.get("type") == "tool.called"):
        tool = event.get("tool", "")
        refused = event.get("refused", False)
        if outside_frame(tool, frame) and not refused:
            out.append(
                Violation(
                    "W-07",
                    f"tool {tool!r} lies outside the frame and was not refused "
                    f"(seq {event['seq']})",
                )
            )
        host = event.get("host")
        if host is not None and host_outside_frame(str(host), frame) and not refused:
            out.append(
                Violation(
                    "W-13",
                    f"host {host!r} lies outside the frame's allowed_hosts and was reached "
                    f"without refusal (seq {event['seq']})",
                )
            )

    out.extend(artifact_violations(events))
    out.extend(after_violations(assignment, events, str(outcome)))
    return out


def after_violations(assignment: Json, events: Sequence[Json], outcome: str) -> list[Violation]:
    """W-18 within one stream: the command after the work is the assignment's last step. A
    succeeded assignment carries the artifact the task names, and no step starts after it. A
    resumed assignment may have produced it before its checkpoint, so a resumed stream is not
    held to its presence. That the bytes are the command's output only a live run can show."""
    after = (assignment.get("task") or {}).get("after")
    if not isinstance(after, dict) or outcome != "succeeded":
        return []
    named = after.get("artifact")
    produced = [
        n
        for n, e in enumerate(events)
        if e.get("type") == "artifact.produced" and e.get("artifact_id") == named
    ]
    if not produced:
        if (assignment.get("context") or {}).get("checkpoint_ref") is not None:
            return []
        return [
            Violation(
                "W-18",
                f"the assignment succeeded without the artifact {named!r} that its command "
                "after the work names",
            )
        ]
    later = [e.get("step_id") for e in events[produced[0] + 1 :] if e.get("type") == "step.started"]
    if later:
        return [
            Violation(
                "W-18",
                f"step(s) {later} started after the artifact {named!r} of the command after "
                f"the work (seq {events[produced[0]].get('seq')}): the command ran before the "
                "work was done",
            )
        ]
    return []


def consumption_violations(events: Sequence[Json], started: Sequence[str]) -> list[Violation]:
    """W-04: every started step reports its consumption before the next step starts. A worker
    that settles up at the end gives admission control nothing to work with."""
    out: list[Violation] = []
    reported_in_time: set[str] = set()
    reported_late: dict[str, int] = {}
    current: str | None = None
    for event in events:
        kind = event.get("type")
        if kind == "step.started":
            current = str(event.get("step_id"))
        elif kind == "consumption.reported":
            step = str(event.get("step_id"))
            if step == current:
                reported_in_time.add(step)
            elif step not in reported_in_time:
                reported_late.setdefault(step, event["seq"])
    unreported = [s for s in started if s not in reported_in_time and s not in reported_late]
    if unreported:
        out.append(Violation("W-04", f"no consumption.reported for step(s) {unreported}"))
    for step, seq in reported_late.items():
        if step in started:
            out.append(
                Violation(
                    "W-04",
                    f"consumption for step {step!r} was reported at seq {seq}, after the next "
                    "step had started — consumption comes per step, not at the end",
                )
            )
        else:
            out.append(Violation("W-04", f"consumption.reported for unknown step {step!r}"))
    return out


def stop_violations(
    events: Sequence[Json], last: Json, boundaries: Sequence[Json], *, check: str = "W-06"
) -> list[Violation]:
    """W-06: after an acknowledged stop the assignment ends at a boundary: no step starts after
    the last step.boundary, the outcome is stopped, and the checkpoint is the boundary's. A halt
    at a limit (W-14) has the same shape, and `check` names which of the two is judged."""
    out: list[Violation] = []
    outcome = last.get("outcome")
    if outcome != "stopped":
        out.append(
            Violation(
                check,
                f"a stop was requested and acknowledged, but the outcome is {outcome!r}, "
                "not 'stopped'",
            )
        )
        return out
    final = boundaries[-1]
    after = [e for e in events if e["seq"] > final["seq"] and e.get("type") == "step.started"]
    if after:
        out.append(
            Violation(
                check,
                f"step {after[0].get('step_id')!r} started (seq {after[0]['seq']}) after the last "
                f"step.boundary (seq {final['seq']}): the stop did not take effect at a boundary",
            )
        )
    checkpoint = last.get("checkpoint_ref")
    if not checkpoint:
        out.append(
            Violation(check, "assignment.finished with outcome stopped carries no checkpoint_ref")
        )
    elif checkpoint != final.get("checkpoint_ref"):
        out.append(
            Violation(
                check,
                f"checkpoint_ref {checkpoint!r} of assignment.finished differs from the last "
                f"boundary's {final.get('checkpoint_ref')!r}",
            )
        )
    return out


def artifact_violations(events: Sequence[Json]) -> list[Violation]:
    """W-11 within one stream: no two artifact.produced share a digest or an artifact_id."""
    out: list[Violation] = []
    digests: dict[str, int] = {}
    ids: dict[str, int] = {}
    for event in (e for e in events if e.get("type") == "artifact.produced"):
        digest = event.get("digest", "")
        artifact_id = event.get("artifact_id", "")
        if digest in digests:
            out.append(
                Violation(
                    "W-11",
                    f"artifact digest {digest[:19]}… emitted twice "
                    f"(seq {digests[digest]} and {event['seq']})",
                )
            )
        digests.setdefault(digest, event["seq"])
        if artifact_id in ids:
            out.append(
                Violation(
                    "W-11",
                    f"artifact_id {artifact_id!r} emitted twice "
                    f"(seq {ids[artifact_id]} and {event['seq']})",
                )
            )
        ids.setdefault(artifact_id, event["seq"])
    return out


def duplicate_artifacts(before: Sequence[Json], after: Sequence[Json]) -> list[Violation]:
    """W-11 across a resume: an artifact produced before the checkpoint appears again after it."""
    out: list[Violation] = []
    earlier = {
        e.get("digest"): e.get("artifact_id")
        for e in before
        if e.get("type") == "artifact.produced"
    }
    for event in (e for e in after if e.get("type") == "artifact.produced"):
        if event.get("digest") in earlier:
            out.append(
                Violation(
                    "W-11",
                    f"artifact {event.get('artifact_id')!r} "
                    f"(digest {event.get('digest', '')[:19]}…) was already produced before "
                    f"the checkpoint as {earlier[event.get('digest')]!r} and was produced "
                    f"again (seq {event['seq']})",
                )
            )
    return out


def capacity_violations(probe: Json) -> list[Violation]:
    """W-15: a worker that holds as many assignments as it declares answers one more with
    `503` and a problem body, and records nothing. `probe` has the shape `CapacityProbe` of
    Worker.json: what the worker declared, the states of the assignments the suite held, read
    after the answer, the answer, and what a lookup of the refused assignment returned.

    An accepted assignment is a violation only when every held assignment was still unfinished
    after the answer. A finished state does not change back, so those were all held when the
    worker accepted. Where one had finished, the worker may have had a free place; that is no
    violation, and the suite reports the check inconclusive."""
    declared = int(probe["max_concurrent_assignments"])
    held = [s for s in probe["held"] if s.get("status") != "finished"]
    answer = probe["answer"]
    status = int(answer["status"])
    body = answer.get("body")
    out: list[Violation] = []
    if status in (200, 201, 202):
        if len(held) >= declared:
            out.append(
                Violation(
                    "W-15",
                    f"holding {len(held)} assignment(s) of {declared} declared, the worker "
                    f"accepted one more with {status} instead of answering 503",
                )
            )
        return out
    if status != 503:
        out.append(
            Violation(
                "W-15",
                f"holding {len(held)} assignment(s) of {declared} declared, the worker answered "
                f"one more with {status}, expected 503",
            )
        )
        return out
    if not isinstance(body, dict) or not isinstance(body.get("title"), str):
        out.append(Violation("W-15", "the 503 carries no problem body with a title"))
    elif body.get("status") != 503:
        out.append(
            Violation("W-15", f"the problem body of the 503 says status {body.get('status')!r}")
        )
    lookup = probe.get("lookup")
    if lookup is not None and int(lookup) != 404:
        out.append(
            Violation(
                "W-15",
                f"the worker answered 503 but recorded the assignment: looking it up answered "
                f"{lookup}, expected 404",
            )
        )
    return out


def _problem_answer(check: str, what: str, answer: Json, expected: int) -> list[Violation]:
    """The answer must be `expected` with a problem body: a JSON object with a title and that
    status."""
    status = int(answer["status"])
    body = answer.get("body")
    if status != expected:
        return [Violation(check, f"{what} answered {status}, expected {expected}")]
    if not isinstance(body, dict) or not isinstance(body.get("title"), str):
        return [Violation(check, f"the {expected} to {what} carries no problem body with a title")]
    if body.get("status") != expected:
        return [
            Violation(
                check, f"the problem body of the {expected} says status {body.get('status')!r}"
            )
        ]
    return []


def unknown_id_violations(probe: Json) -> list[Violation]:
    """W-16: the state of an assignment id the worker never received answers `404` with a
    problem body. `probe` has the shape `UnknownIdProbe` of Worker.json: the id asked about and
    the answer. A runner that recovers a run relies on this answer: a `404` makes it post the
    assignment again under the same id (ADR-0038)."""
    what = f"GET /v1/assignments/{probe['assignment_id']}, an id the worker never received,"
    return _problem_answer("W-16", what, probe["answer"], 404)


def repeated_id_violations(probe: Json) -> list[Violation]:
    """W-17: an assignment whose id the worker already holds answers `409` with a problem body,
    and the worker starts nothing. `probe` has the shape `RepeatedIdProbe` of Worker.json: the
    state of the assignment the worker held before the repeat, the answer to the repeat, and
    the state read after it.

    The state after must still be the first assignment's. A finished state does not change. A
    state that had not finished may move on, but not back: the same `accepted_at`, and a
    `last_seq` no lower than before. A lower one means the stream began again, which only a
    second assignment under the same id does."""
    held = probe["held"]
    after = probe["after"]
    assignment_id = held.get("assignment_id")
    out = _problem_answer(
        "W-17",
        f"a repeated POST /v1/assignments of {assignment_id}, an id the worker holds "
        f"({held.get('status')}),",
        probe["answer"],
        409,
    )
    if after.get("assignment_id") != assignment_id:
        out.append(
            Violation(
                "W-17",
                f"after the repeat the state names {after.get('assignment_id')!r}, "
                f"not {assignment_id!r}",
            )
        )
        return out
    if after.get("accepted_at") != held.get("accepted_at"):
        out.append(
            Violation(
                "W-17",
                f"after the repeat {assignment_id} was accepted at {after.get('accepted_at')!r}, "
                f"not {held.get('accepted_at')!r}: the worker took the repeat as a second "
                "assignment",
            )
        )
    if held.get("status") == "finished":
        fields = ("status", "outcome", "last_seq", "finished_at")
        changed = [f for f in fields if after.get(f) != held.get(f)]
        if changed:
            out.append(
                Violation(
                    "W-17",
                    f"{assignment_id} had finished, and after the repeat its "
                    f"{', '.join(changed)} changed: the worker started it again",
                )
            )
    elif int(after.get("last_seq", 0)) < int(held.get("last_seq", 0)):
        out.append(
            Violation(
                "W-17",
                f"after the repeat {assignment_id} is at seq {after.get('last_seq')}, below "
                f"{held.get('last_seq')} before it: its stream began again",
            )
        )
    return out
