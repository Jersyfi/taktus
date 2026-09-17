"""The suite: C-01 to C-10 against a live connector over MCP.

Two inputs: the connector's MCP endpoint and a scenario (`Connector.json#/$defs/Scenario`). The
suite cannot know which input an operation needs, so the scenario names one read, one or more
writes, one call the target must refuse, and the recorded payloads for intake. The suite then:

1. reads the declaration and the tool list — C-01;
2. calls the read with a fresh key, and once without any credential — C-02, C-03, C-09;
3. calls every write twice with one key and once with another — C-05, and C-02, C-09 again;
4. calls the invalid case — C-06;
5. delivers the intake payload signed, unsigned, wrongly signed, and the unsupported and
   own-action payloads where the scenario has them — C-07, C-08;
6. scans everything it saw, and the connector's log, for every credential value it knows —
   C-04;
7. reports C-10 as pending: the removal test needs processes, and the suite has none.

Every schema violation is attributed to the check that owns the document: an invalid
declaration is C-01, an invalid Result is C-02, an invalid Error is C-06, an invalid IntakeResult
is C-07 or C-08 depending on what was expected. Transport faults are C-01.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from taktus.conformance.connector import rules
from taktus.conformance.connector.client import Answer, ConnectorClient
from taktus.conformance.connector.rules import (
    CAPABILITIES_RESOURCE,
    CATALOGUE,
    CHECKS,
    INTAKE_TOOL,
    OUTWARD,
    REPEATABLE,
)
from taktus.conformance.contracts import first_error
from taktus.conformance.findings import Findings
from taktus.conformance.report import CallSummary, CheckResult, Report

type Json = dict[str, Any]

CONTRACT = "connector/v1"
UNIQUE = "{{unique}}"


@dataclass
class ConnectorSuiteOptions:
    endpoint: str
    scenario: Json
    credential_values: Mapping[str, str] = field(default_factory=dict)
    """Name to value, read from the suite's own environment. Never sent; the actions value is
    only searched for, the intake value only used to sign."""
    adapter_log: Path | None = None
    timeout: float = 60.0


@dataclass
class Seen:
    """Everything the connector answered, as labelled text, for the credential scan."""

    places: list[tuple[str, str]] = field(default_factory=list)
    calls: list[CallSummary] = field(default_factory=list)

    def note(self, label: str, text: str) -> None:
        self.places.append((label, text))

    def answered(self, purpose: str, answer: Answer) -> None:
        outcome = (
            "transport error"
            if answer.transport_error
            else ("error" if answer.is_error else "result")
        )
        self.calls.append(CallSummary(purpose, answer.tool, outcome))
        self.note(f"the answer to {answer.tool} ({purpose})", answer.text)


async def run_connector_suite(options: ConnectorSuiteOptions) -> Report:
    report = Report(endpoint=options.endpoint, contract=CONTRACT)
    findings = Findings(CHECKS)
    seen = Seen()
    scenario = options.scenario
    try:
        async with ConnectorClient(options.endpoint, timeout=options.timeout) as client:
            capabilities = await _c01(client, findings, seen)
            await _reads(client, options, capabilities, findings, seen)
            await _writes(client, scenario, capabilities, findings, seen)
            await _c06(client, scenario, findings, seen)
            await _intake(client, options, capabilities, findings, seen)
    except Exception as error:
        report.notes.append(f"the connector at {options.endpoint} stopped answering: {error!r}")
        if not findings.evidence["C-01"]:
            findings.fail("C-01", f"the connector at {options.endpoint} did not answer: {error!r}")
        for check in CATALOGUE.runnable:
            if not findings.evidence[check] and not findings.failed(check):
                findings.inconclusive.setdefault(
                    check, "not reached: the connector stopped answering (see the notes)"
                )
    _c04(options, seen, findings)
    for check in CHECKS:
        if check == "C-10":
            report.add(
                CheckResult.pending(
                    "C-10",
                    "not run: the removal test needs processes that use the adapter, and no "
                    "process uses a connector yet; this half of maturity stays pending",
                )
            )
        else:
            report.add(findings.result(check))
    report.calls = list(seen.calls)
    return report.finish()


# --- C-01 ---------------------------------------------------------------------------------------


async def _c01(client: ConnectorClient, findings: Findings, seen: Seen) -> Json:
    declaration = await client.declaration(CAPABILITIES_RESOURCE)
    seen.note("the capabilities resource", declaration.text)
    if declaration.problem is not None or declaration.json is None:
        findings.fail("C-01", declaration.problem or "the capabilities resource is not an object")
        return {}
    capabilities = declaration.json
    if declaration.mime_type != "application/json":
        findings.fail(
            "C-01",
            f"the capabilities resource is served as {declaration.mime_type!r}, "
            "not application/json",
        )
    if (why := first_error("Capabilities", capabilities, CONTRACT)) is not None:
        findings.fail("C-01", f"the declaration does not validate against Capabilities: {why}")
        return capabilities
    tools = await client.tools()
    seen.note("the tool list", tools.text)
    for violation in rules.declaration_violations(capabilities, tools.names):
        findings.add(violation, "declaration")
    if not findings.failed("C-01"):
        operations = rules.operations_of(capabilities)
        outward = sum(1 for op in operations.values() if op.get("effect") in OUTWARD)
        findings.ok(
            "C-01",
            f"declares {len(capabilities['capabilities'])} capabilities, {len(operations)} "
            f"operations ({outward} leaving the system) and "
            f"{'an' if 'intake' in capabilities else 'no'} intake; the tool list agrees",
        )
        findings.ok(
            "C-02",
            f"every one of the {len(operations)} operations declares its effect, and every "
            "outward one its idempotency (schema-checked)",
        )
    return capabilities


# --- building calls ----------------------------------------------------------------------------


def _key(step: str) -> str:
    return f"conf-{secrets.token_hex(8)}:{step}:1"


def _context(scenario: Json, step: str, key: str, *, credentials: bool = True) -> Json:
    names = [scenario["credentials"]["actions"]] if credentials else []
    return {
        "tenant": "conformance",
        "identity": "idn_conformance",
        "run_id": "run_conformance",
        "step_id": step,
        "attempt": 1,
        "idempotency_key": key,
        "credentials": [{"name": name, "injected_as": "env"} for name in names],
        "autonomy_level": 2,
    }


def _unique(value: Any, token: str) -> Any:
    if isinstance(value, str):
        return value.replace(UNIQUE, token)
    if isinstance(value, dict):
        return {k: _unique(v, token) for k, v in value.items()}
    if isinstance(value, list):
        return [_unique(v, token) for v in value]
    return value


async def _call(
    client: ConnectorClient,
    seen: Seen,
    purpose: str,
    case: Json,
    context: Json,
    *,
    token: str | None = None,
) -> Answer:
    arguments = {"context": context, "input": _unique(case["input"], token or "")}
    answer = await client.call(str(case["operation"]), arguments)
    seen.answered(purpose, answer)
    return answer


def _result_of(answer: Answer, findings: Findings, where: str) -> Json | None:
    """The validated Result of a successful call, or None with the failure recorded."""
    if answer.transport_error:
        findings.fail("C-01", f"{where}: the call did not go through: {answer.transport_error}")
        return None
    if answer.is_error:
        detail = answer.json or {}
        findings.fail(
            "C-02",
            f"{where}: the call ended in an error ({detail.get('cause', 'no cause')}: "
            f"{detail.get('detail', answer.text[:160])}) although the scenario expects it to "
            "succeed",
        )
        return None
    if answer.json is None:
        findings.fail("C-02", f"{where}: the result has no structured content")
        return None
    if (why := first_error("Result", answer.json, CONTRACT)) is not None:
        findings.fail("C-02", f"{where}: the result does not validate against Result: {why}")
        return None
    return answer.json


def _error_of(answer: Answer, findings: Findings, where: str) -> Json | None:
    """The validated Error of a failed call, or None with the failure recorded under C-06."""
    if answer.transport_error:
        findings.fail("C-01", f"{where}: the call did not go through: {answer.transport_error}")
        return None
    if not answer.is_error:
        return None
    if answer.json is None:
        findings.fail(
            "C-06",
            f"{where}: the error carries no Error envelope, only text: {answer.text[:160]!r}",
        )
        return None
    if (why := first_error("Error", answer.json, CONTRACT)) is not None:
        findings.fail("C-06", f"{where}: the error does not validate against Error: {why}")
        return None
    return answer.json


# --- C-02, C-03, C-09 on the read --------------------------------------------------------------


async def _reads(
    client: ConnectorClient,
    options: ConnectorSuiteOptions,
    capabilities: Json,
    findings: Findings,
    seen: Seen,
) -> None:
    scenario = options.scenario
    case = scenario["read"]
    operation = str(case["operation"])
    where = f"read {operation}"
    answer = await _call(client, seen, "read", case, _context(scenario, "read", _key("read")))
    result = _result_of(answer, findings, where)
    if result is not None:
        for violation in rules.result_violations(capabilities, operation, result, where=""):
            findings.add(violation, where)
        if not findings.failed("C-02"):
            findings.ok("C-02", f"{where}: the result reports effect {result['effect']['kind']!r}")
        if not findings.failed("C-09"):
            findings.ok("C-09", f"{where}: consumption {result['consumption']}")

    bare = await _call(
        client,
        seen,
        "read without credential",
        case,
        _context(scenario, "read", _key("read"), credentials=False),
    )
    where = f"read {operation} without a credential"
    if bare.transport_error:
        findings.fail("C-01", f"{where}: the call did not go through: {bare.transport_error}")
        return
    if not bare.is_error:
        findings.fail(
            "C-03",
            f"{where}: the call was served although the context referenced no credential; the "
            "connector acted with a credential of its own",
        )
        return
    error = _error_of(bare, findings, where)
    if error is None:
        findings.inconclusive.setdefault(
            "C-03", f"{where}: refused, but the error is not classified (see C-06)"
        )
        return
    if error.get("cause") != "unauthenticated" or error.get("effect") != "none":
        findings.fail(
            "C-03",
            f"{where}: refused with cause {error.get('cause')!r} and effect "
            f"{error.get('effect')!r}, expected unauthenticated and none",
        )
        return
    findings.ok("C-03", f"{where}: refused with cause unauthenticated and no effect")


# --- C-05 on the writes ------------------------------------------------------------------------


async def _writes(
    client: ConnectorClient,
    scenario: Json,
    capabilities: Json,
    findings: Findings,
    seen: Seen,
) -> None:
    operations = rules.operations_of(capabilities)
    for case in scenario["writes"]:
        operation = str(case["operation"])
        declared = operations.get(operation)
        if declared is None:
            findings.fail("C-05", f"the scenario names {operation!r}, which is not declared")
            continue
        if declared.get("effect") not in OUTWARD:
            findings.inconclusive.setdefault(
                "C-05",
                f"the scenario lists {operation!r} as a write, but it is declared with effect "
                f"{declared.get('effect')!r}; name an operation that leaves the system",
            )
            continue
        if declared.get("idempotency") not in REPEATABLE:
            findings.inconclusive.setdefault(
                "C-05",
                f"{operation!r} declares idempotency {declared.get('idempotency')!r}; the suite "
                "does not repeat such an operation (README §4) — name a native or marked one",
            )
            continue
        token = secrets.token_hex(4)
        key = _key(operation.rsplit(".", 1)[-1])
        first = await _call(
            client, seen, "write", case, _context(scenario, "write", key), token=token
        )
        first_result = _result_of(first, findings, f"first {operation}")
        if first_result is None:
            continue
        for violation in rules.result_violations(capabilities, operation, first_result):
            findings.add(violation, f"first {operation}")
        repeat = await _call(
            client, seen, "write repeated", case, _context(scenario, "write", key), token=token
        )
        repeat_result = _result_of(repeat, findings, f"repeated {operation}")
        if repeat_result is None:
            continue
        fresh = await _call(
            client,
            seen,
            "write with a new key",
            case,
            _context(scenario, "write", _key("fresh")),
            token=secrets.token_hex(4),
        )
        fresh_result = _result_of(fresh, findings, f"fresh {operation}")
        for violation in rules.repeat_violations(
            operation, first_result, repeat_result, fresh_result
        ):
            findings.add(violation, "C-05")
        if not findings.failed("C-05"):
            records = first_result["effect"]["records"]
            findings.ok(
                "C-05",
                f"{operation}: acted on {[r['id'] for r in records]}, returned the same with "
                "replayed: true on the repeat, and acted again on a new key",
            )
        if not findings.failed("C-02"):
            findings.ok(
                "C-02",
                f"{operation}: the result reports effect {first_result['effect']['kind']!r} "
                f"with {len(first_result['effect']['records'])} record(s)",
            )


# --- C-06 on the invalid case ------------------------------------------------------------------


async def _c06(client: ConnectorClient, scenario: Json, findings: Findings, seen: Seen) -> None:
    case = scenario["invalid"]
    operation = str(case["operation"])
    expected = case.get("expected_cause")
    where = f"invalid {operation}"
    answer = await _call(client, seen, "invalid", case, _context(scenario, "invalid", _key("inv")))
    if answer.transport_error:
        findings.fail("C-01", f"{where}: the call did not go through: {answer.transport_error}")
        return
    if not answer.is_error:
        findings.fail(
            "C-06",
            f"{where}: the call succeeded although the scenario says the target must refuse it",
        )
        return
    error = _error_of(answer, findings, where)
    if error is None:
        return
    for violation in rules.error_violations(error, expected_cause=expected):
        findings.add(violation, where)
    if not findings.failed("C-06"):
        findings.ok(
            "C-06",
            f"{where}: a failure with cause {error['cause']!r}, effect {error['effect']!r}, "
            f"retryable {error['retryable']}",
        )


# --- C-07, C-08 on intake ----------------------------------------------------------------------


def _sign(body: str, secret: str) -> str:
    return hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()


async def _intake(
    client: ConnectorClient,
    options: ConnectorSuiteOptions,
    capabilities: Json,
    findings: Findings,
    seen: Seen,
) -> None:
    scenario = options.scenario
    declared = "intake" in capabilities
    if not declared:
        if "intake" in scenario:
            findings.fail(
                "C-07", "the scenario has intake payloads but the declaration has no intake"
            )
            return
        for check in ("C-07", "C-08"):
            findings.ok(check, "not applicable: the declaration has no intake")
        return
    if "intake" not in scenario:
        for check in ("C-07", "C-08"):
            findings.inconclusive.setdefault(
                check, "the declaration has an intake but the scenario has no payload for it"
            )
        return
    secret_name = scenario["credentials"].get("intake")
    secret = options.credential_values.get(secret_name or "")
    if not secret:
        for check in ("C-07", "C-08"):
            findings.inconclusive.setdefault(
                check,
                f"no intake secret to sign with: set {secret_name or 'credentials.intake'} to "
                "the same value in the connector's environment and in the suite's",
            )
        return
    intake = scenario["intake"]
    header = str(intake["signature"]["header"])
    prefix = str(intake["signature"]["prefix"])
    supported = intake["supported"]

    async def deliver(purpose: str, payload: Json, signature: str | None) -> Json | None:
        headers = dict(payload["headers"])
        if signature is not None:
            headers[header] = signature
        arguments = {
            "headers": headers,
            "body": payload["body"],
            "received_at": "2026-01-01T00:00:00Z",
        }
        answer = await client.call(INTAKE_TOOL, arguments)
        seen.answered(purpose, answer)
        check = "C-07" if purpose == "signed" else "C-08"
        if answer.transport_error:
            findings.fail("C-01", f"intake ({purpose}): {answer.transport_error}")
            return None
        if answer.is_error:
            findings.fail(
                check,
                f"intake ({purpose}): the tool call ended in an error instead of deciding: "
                f"{answer.text[:160]!r}",
            )
            return None
        if answer.json is None:
            findings.fail(check, f"intake ({purpose}): no structured content")
            return None
        if (why := first_error("IntakeResult", answer.json, CONTRACT)) is not None:
            findings.fail(
                check, f"intake ({purpose}): does not validate against IntakeResult: {why}"
            )
            return None
        return answer.json

    body = str(supported["body"])
    signed = await deliver("signed", supported, prefix + _sign(body, secret))
    if signed is not None:
        for violation in rules.intake_violations(capabilities, signed, expect="accepted"):
            findings.add(violation, "intake (signed)")
        if not findings.failed("C-07"):
            accepted = signed["accepted"]
            findings.ok(
                "C-07",
                f"a signed payload became event {accepted['event']!r} from sender "
                f"{accepted['sender']['account']!r} with reply address "
                f"{accepted['reply_to']['address']!r}",
            )

    cases: list[tuple[str, Json, str | None, str]] = [
        ("unsigned", supported, None, "unsigned"),
        ("wrongly signed", supported, prefix + _sign(body, secret + "-not"), "bad_signature"),
    ]
    if "unsupported" in intake:
        unsupported = intake["unsupported"]
        cases.append(
            (
                "unsupported",
                unsupported,
                prefix + _sign(str(unsupported["body"]), secret),
                "unsupported_event",
            )
        )
    if "own_action" in intake:
        own = intake["own_action"]
        cases.append(("own action", own, prefix + _sign(str(own["body"]), secret), "own_action"))
    refused = 0
    for purpose, payload, signature, reason in cases:
        result = await deliver(purpose, payload, signature)
        if result is None:
            continue
        for violation in rules.intake_violations(
            capabilities, result, expect="refused", reason=reason
        ):
            findings.add(violation, f"intake ({purpose})")
        refused += 1
    if refused and not findings.failed("C-08"):
        findings.ok(
            "C-08",
            f"{refused} payload(s) refused with the expected reason: "
            + ", ".join(reason for _, _, _, reason in cases),
        )


# --- C-04 across everything --------------------------------------------------------------------


def _c04(options: ConnectorSuiteOptions, seen: Seen, findings: Findings) -> None:
    values = {name: value for name, value in options.credential_values.items() if value}
    if not values:
        findings.inconclusive["C-04"] = (
            "no credential value to look for: set the credentials the scenario names to the "
            "same random values in the connector's environment and in the suite's, then run again"
        )
        return
    places = list(seen.places)
    if options.adapter_log is not None:
        try:
            places.append(("the connector log", options.adapter_log.read_text(errors="replace")))
        except OSError as error:
            findings.inconclusive["C-04"] = f"the connector log could not be read: {error}"
    hits: list[str] = []
    for name, value in values.items():
        needles = {"in clear": value, "base64": base64.b64encode(value.encode()).decode()}
        for where, text in places:
            for form, needle in needles.items():
                if needle in text:
                    hits.append(f"the value of {name} appears {form} in {where}")
    for hit in dict.fromkeys(hits):
        findings.fail("C-04", hit)
    if not hits and "C-04" not in findings.inconclusive:
        scanned = f"{len(seen.places)} answer(s) and the declaration"
        if options.adapter_log is not None:
            scanned += " and the connector log"
        findings.ok(
            "C-04",
            f"{', '.join(sorted(values))} referenced by name; no value appears in {scanned}",
        )
