"""The rules of the connector contract: what a declaration, a result, an error and an intake
result must satisfy beyond their schema.

These are the executable reading of the checks C-01 to C-09 of contracts/connector/v1/README.md
§8, as far as they can be judged on documents alone: the schema says what a result looks like,
these rules say what it must say given what was declared and what was asked. They take the
documents the suite collected and return every violation found, each naming its check. The live
suite (`suite.py`) applies them to what a running connector answered; `tests/conformance` applies
them to known-good and known-bad documents. Nothing here does I/O.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from taktus.conformance.catalogue import Catalogue
from taktus.conformance.findings import Violation

type Json = dict[str, Any]

INTAKE_TOOL = "intake"
CAPABILITIES_RESOURCE = "taktus://connector/v1/capabilities"
OUTWARD = frozenset({"write", "delivery"})
REPEATABLE = frozenset({"native", "marked"})

# Which quantity of a result's consumption a declared kind is reported in.
QUANTITY_OF_KIND: Mapping[str, tuple[str, ...]] = {
    "quota": ("quota_units",),
    "currency": ("currency",),
    "compute": ("compute_seconds",),
}

# Causes after which the same call may never be repeated blindly.
NOT_RETRYABLE = frozenset({"unauthenticated", "forbidden", "not_found", "invalid", "conflict"})

CHECKS: dict[str, str] = {
    "C-01": "capabilities declares the contract, at least one capability, and every operation "
    "as a tool of the same name",
    "C-02": "every operation declares its effect and, when it leaves the system, its idempotency; "
    "a result carries the declared effect",
    "C-03": "a call without the requesting identity's credential is refused, not served with "
    "another",
    "C-04": "no credential value appears in a result, an error, the declaration or the log",
    "C-05": "an outward call repeated with the same idempotency key returns the original result "
    "and acts once",
    "C-06": "an error is classified: a failure with cause, effect and retryable, never a bare "
    "message",
    "C-07": "a correctly signed intake payload becomes a well-formed intake command",
    "C-08": "an unsigned or wrongly signed intake payload is refused, never processed",
    "C-09": "every result reports consumption in a declared kind",
    "C-10": "the adapter passes the removal test: removing it breaks no process",
}

SECTIONS: dict[str, str] = {
    "C-01": "§2 The MCP binding and §3 Capabilities",
    "C-02": "§3 Capabilities and §5 A call",
    "C-03": "§5 A call",
    "C-04": "§5 A call",
    "C-05": "§4 Idempotency",
    "C-06": "§6 Errors",
    "C-07": "§7 Intake",
    "C-08": "§7 Intake",
    "C-09": "§5 A call",
    "C-10": "§8 Conformance",
}

REQUIREMENTS: dict[str, str] = {
    "C-01": "the resource taktus://connector/v1/capabilities is application/json and validates "
    "against Connector.json#/$defs/Capabilities; every operation's name extends its capability, "
    "and that capability is declared; tools/list holds exactly the declared operations plus "
    "intake when an intake is declared",
    "C-02": "every operation declares effect, and idempotency exactly when the effect is write or "
    "delivery (the schema enforces both); the result of a call carries effect.kind equal to the "
    "declared effect, and for an outward effect at least one record",
    "C-03": "a call whose context references no credential ends with isError true and an Error "
    "with cause unauthenticated and effect none; the connector has no credential of its own",
    "C-04": "the value of a credential the scenario names never appears — in clear or base64 — "
    "in the capabilities document, the tool list, any result, any error, any intake result or "
    "the connector's log",
    "C-05": "a write or delivery operation whose idempotency is native or marked, called twice "
    "with the same idempotency key, returns the same records the second time with "
    "replayed: true, and with a new key acts again on new records with replayed: false",
    "C-06": "a call the target must refuse ends with isError true and an Error that validates: "
    "class failure, a cause from the vocabulary — the one the scenario expects — effect none or "
    "unknown, retryable false after unauthenticated, forbidden, not_found, invalid or conflict",
    "C-07": "the intake tool, given a payload signed with the intake secret under the declared "
    "scheme, returns accepted with an Intake that validates, names an event the declaration "
    "lists, a sender, a context and a reply address",
    "C-08": "the intake tool returns refused with reason unsigned for a payload without a "
    "signature and bad_signature for a wrongly signed one; an event the declaration does not "
    "list is refused as unsupported_event; the connector's own action is refused as own_action",
    "C-09": "every Result carries consumption with at least one quantity, and a quantity of a "
    "kind the capabilities declare",
    "C-10": "removing the adapter changes quality or cost but breaks no process",
}

CATALOGUE = Catalogue.build(
    "connector/v1",
    "contracts/connector/v1/README.md",
    CHECKS,
    REQUIREMENTS,
    SECTIONS,
    unrunnable=frozenset({"C-10"}),
)


def operations_of(capabilities: Json) -> dict[str, Json]:
    return {str(op.get("name")): op for op in capabilities.get("operations", [])}


def declaration_violations(capabilities: Json, tools: Sequence[str]) -> list[Violation]:
    """C-01 beyond the schema: names agree with capabilities, and the tool list agrees with the
    declaration."""
    out: list[Violation] = []
    declared = set(capabilities.get("capabilities", []))
    operations = operations_of(capabilities)
    for name, operation in operations.items():
        capability = str(operation.get("capability"))
        if not name.startswith(capability + "."):
            out.append(
                Violation(
                    "C-01",
                    f"operation {name!r} does not extend its capability {capability!r}",
                )
            )
        if capability not in declared:
            out.append(
                Violation(
                    "C-01",
                    f"operation {name!r} belongs to {capability!r}, which capabilities does "
                    "not declare",
                )
            )
    expected = set(operations)
    if "intake" in capabilities:
        expected.add(INTAKE_TOOL)
    served = set(tools)
    for name in sorted(expected - served):
        out.append(Violation("C-01", f"declared operation {name!r} is not served as a tool"))
    for name in sorted(served - expected):
        what = "intake" if name == INTAKE_TOOL else "tool"
        out.append(Violation("C-01", f"served {what} {name!r} is not declared"))
    return out


def result_violations(
    capabilities: Json, operation: str, result: Json, *, where: str = ""
) -> list[Violation]:
    """C-02 and C-09 on one successful result: the effect is the declared one and consumption
    is reported in a declared kind."""
    out: list[Violation] = []
    declared = operations_of(capabilities).get(operation, {})
    effect = result.get("effect", {})
    if declared and effect.get("kind") != declared.get("effect"):
        out.append(
            Violation(
                "C-02",
                f"{where}{operation} is declared with effect {declared.get('effect')!r} but the "
                f"result reports {effect.get('kind')!r}",
            )
        )
    if effect.get("kind") in OUTWARD and not effect.get("records"):
        out.append(
            Violation("C-02", f"{where}{operation} left the system but the result names no record")
        )
    out.extend(consumption_violations(capabilities, result.get("consumption"), where=where))
    return out


def consumption_violations(
    capabilities: Json, consumption: Any, *, where: str = ""
) -> list[Violation]:
    """C-09: at least one quantity, and one of a declared kind."""
    if not isinstance(consumption, dict) or not consumption:
        return [Violation("C-09", f"{where}the result reports no consumption")]
    kinds = capabilities.get("consumption", {}).get("kinds", [])
    wanted = [q for kind in kinds for q in QUANTITY_OF_KIND.get(kind, ())]
    if wanted and not any(q in consumption for q in wanted):
        return [
            Violation(
                "C-09",
                f"{where}consumption {sorted(consumption)} reports none of the declared kinds "
                f"{kinds} ({wanted})",
            )
        ]
    return []


def error_violations(
    error: Any, *, expected_cause: str | None = None, where: str = ""
) -> list[Violation]:
    """C-06 beyond the schema: the cause is the expected one and retryable is consistent with
    it. The schema itself is checked by the caller."""
    out: list[Violation] = []
    if not isinstance(error, dict):
        return [Violation("C-06", f"{where}the error is not an Error envelope")]
    cause = error.get("cause")
    if expected_cause is not None and cause != expected_cause:
        out.append(
            Violation(
                "C-06",
                f"{where}the scenario expects cause {expected_cause!r}, the error says {cause!r}",
            )
        )
    if cause in NOT_RETRYABLE and error.get("retryable") is True:
        out.append(
            Violation(
                "C-06",
                f"{where}cause {cause!r} cannot be retried, but retryable is true",
            )
        )
    return out


def repeat_violations(
    operation: str, first: Json, repeat: Json, fresh: Json | None, *, where: str = ""
) -> list[Violation]:
    """C-05 on three results of one outward operation: `first` with a key, `repeat` with the
    same key, `fresh` with a new key."""
    out: list[Violation] = []
    first_effect = first.get("effect", {})
    repeat_effect = repeat.get("effect", {})
    if first_effect.get("replayed") is not False:
        out.append(
            Violation(
                "C-05",
                f"{where}the first call of {operation} reports replayed "
                f"{first_effect.get('replayed')!r}; a first call acts and says so",
            )
        )
    if repeat_effect.get("replayed") is not True:
        out.append(
            Violation(
                "C-05",
                f"{where}{operation} called again with the same idempotency key reports replayed "
                f"{repeat_effect.get('replayed')!r}: the repeat was not recognised",
            )
        )
    if _record_ids(repeat_effect) != _record_ids(first_effect):
        out.append(
            Violation(
                "C-05",
                f"{where}{operation} called again with the same key names records "
                f"{_record_ids(repeat_effect)}, the first call {_record_ids(first_effect)}: "
                "the connector acted twice",
            )
        )
    if fresh is not None:
        fresh_effect = fresh.get("effect", {})
        if fresh_effect.get("replayed") is not False:
            out.append(
                Violation(
                    "C-05",
                    f"{where}{operation} with a new idempotency key reports replayed "
                    f"{fresh_effect.get('replayed')!r}: a new key must act again",
                )
            )
        if _record_ids(fresh_effect) & _record_ids(first_effect):
            out.append(
                Violation(
                    "C-05",
                    f"{where}{operation} with a new idempotency key returned the records of the "
                    "first call: the connector recognises the input, not the key",
                )
            )
    return out


def _record_ids(effect: Json) -> set[tuple[str, str]]:
    return {(str(r.get("kind")), str(r.get("id"))) for r in effect.get("records", [])}


def intake_violations(
    capabilities: Json,
    result: Json,
    *,
    expect: str,
    reason: str | None = None,
    where: str = "",
) -> list[Violation]:
    """C-07 and C-08 on one intake result. `expect` is "accepted" or "refused"; `reason` the
    refusal reason expected. The schema itself is checked by the caller."""
    out: list[Violation] = []
    check = "C-07" if expect == "accepted" else "C-08"
    if expect == "accepted":
        if "accepted" not in result:
            refusal = result.get("refused", {})
            out.append(
                Violation(
                    check,
                    f"{where}a correctly signed payload was refused with reason "
                    f"{refusal.get('reason')!r}: {refusal.get('detail')}",
                )
            )
            return out
        intake = result["accepted"]
        events = capabilities.get("intake", {}).get("events", [])
        if intake.get("event") not in events:
            out.append(
                Violation(
                    check,
                    f"{where}the intake names event {intake.get('event')!r}, which the "
                    f"declaration does not list ({events})",
                )
            )
        return out
    if "refused" not in result:
        out.append(
            Violation(
                check,
                f"{where}the payload was accepted as event "
                f"{result.get('accepted', {}).get('event')!r} although it must be refused "
                f"as {reason!r}",
            )
        )
        return out
    got = result["refused"].get("reason")
    if reason is not None and got != reason:
        out.append(Violation(check, f"{where}refused with reason {got!r}, expected {reason!r}"))
    return out
