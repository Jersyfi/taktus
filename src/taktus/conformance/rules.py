"""The stream rules of the worker contract: what a whole event stream must satisfy.

A stream rule cannot be expressed in JSON Schema because it concerns the order and the
completeness of events, not the shape of one. These are the executable reading of the checks
W-03 to W-07, W-10, W-11 and W-13 of contracts/worker/v1/README.md §7. They take a transcript — the
assignment, the estimate the worker gave for it, and every event in order — and return every
violation found, each naming its check.

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
    return None


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
        out.extend(stop_violations(events, last, boundaries))

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
    return out


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
    events: Sequence[Json], last: Json, boundaries: Sequence[Json]
) -> list[Violation]:
    """W-06: after an acknowledged stop the assignment ends at a boundary: no step starts after
    the last step.boundary, the outcome is stopped, and the checkpoint is the boundary's."""
    out: list[Violation] = []
    outcome = last.get("outcome")
    if outcome != "stopped":
        out.append(
            Violation(
                "W-06",
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
                "W-06",
                f"step {after[0].get('step_id')!r} started (seq {after[0]['seq']}) after the last "
                f"step.boundary (seq {final['seq']}): the stop did not take effect at a boundary",
            )
        )
    checkpoint = last.get("checkpoint_ref")
    if not checkpoint:
        out.append(
            Violation("W-06", "assignment.finished with outcome stopped carries no checkpoint_ref")
        )
    elif checkpoint != final.get("checkpoint_ref"):
        out.append(
            Violation(
                "W-06",
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
