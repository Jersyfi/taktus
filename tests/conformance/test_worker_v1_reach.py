"""What the suite reads from a worker's statement of its reach (ADR-0098).

W-07 and W-13 pass on a statement only where it leaves the withdrawn tool or host out and no
call to it occurred. A worker that states nothing has said nothing: the suite keeps such a run
inconclusive. A statement a call contradicts is not believed, and the call is the violation.
"""

from __future__ import annotations

from typing import Any

from taktus.conformance.rules import not_offered, reach_violations

type Json = dict[str, Any]

DIGEST = "sha256:" + "0" * 64


def stream(*events: Json) -> list[Json]:
    return [{"seq": n, **e} for n, e in enumerate(events, 1)]


def stated(tools: list[str], hosts: list[str] | None = None) -> Json:
    event: Json = {"type": "reach.stated", "tools": tools}
    if hosts is not None:
        event["hosts"] = hosts
    return event


STEP = {"type": "step.started", "step_id": "s1", "kind": "read", "summary": "read"}


def call(tool: str, host: str | None = None, *, refused: bool = False) -> Json:
    event: Json = {"type": "tool.called", "tool": tool, "arguments_digest": DIGEST}
    if host is not None:
        event["host"] = host
    if refused:
        event["refused"] = True
    return event


def test_a_worker_that_states_nothing_passes_nothing_on_a_statement() -> None:
    events = stream(STEP, call("code.read"))
    assert not_offered(events, tool="web.fetch") is None
    assert not_offered(events, host="registry.example") is None
    assert reach_violations(events) == []


def test_a_statement_that_leaves_the_tool_out_is_the_evidence() -> None:
    events = stream(stated(["code.read"]), STEP, call("code.read"))
    statement = not_offered(events, tool="web.fetch")
    assert statement is not None and statement["seq"] == 1
    assert not_offered(events, tool="code.read") is None, "named: it was offered"


def test_hosts_count_only_where_the_statement_bounds_them() -> None:
    unbounded = stream(stated(["code.read", "web.fetch"]), STEP)
    assert not_offered(unbounded, host="registry.example") is None
    bounded = stream(stated(["code.read"], []), STEP)
    assert not_offered(bounded, host="registry.example") is not None
    named = stream(stated(["web.fetch"], ["registry.example"]), STEP)
    assert not_offered(named, host="registry.example") is None


def test_a_call_contradicts_the_statement_and_is_the_violation() -> None:
    events = stream(stated(["code.read"], []), STEP, call("web.fetch", "registry.example"))
    assert not_offered(events, tool="web.fetch") is None
    assert not_offered(events, host="registry.example") is None
    assert {v.check for v in reach_violations(events)} == {"W-07", "W-13"}


def test_a_refused_call_outside_the_statement_still_makes_it_false() -> None:
    events = stream(stated(["code.read"]), STEP, call("web.fetch", refused=True))
    assert [v.check for v in reach_violations(events)] == ["W-07"]


def test_the_statement_is_made_once_before_the_work() -> None:
    late = stream(STEP, stated(["code.read"]))
    twice = stream(stated(["code.read"]), stated(["code.read"]), STEP)
    assert [v.check for v in reach_violations(late)] == ["W-07"]
    assert [v.check for v in reach_violations(twice)] == ["W-07"]
