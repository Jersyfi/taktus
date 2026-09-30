"""The rules of the model contract that no schema can express: what a declaration promises about
one call, held against what the call did.

A declaration (`Model.json#/$defs/Calculability`) says how an adapter counts a prompt before
the call, whether the output limit holds, and which price kinds the provider reports. An
exchange (`Model.json#/$defs/Exchange`) is one call as observed: the count before it, the limit
it set, the usage after it. These functions judge an exchange against its declaration and
return every violation, each naming its check. They serve the fixtures under
`contracts/model/v1/examples/exchange` and the live suite alike; nothing here does I/O.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from taktus.conformance.catalogue import Catalogue
from taktus.conformance.findings import Violation

type Json = dict[str, Any]

CHECKS: dict[str, str] = {
    "M-01": "the declaration validates and names its billing basis",
    "M-02": "a declared input count holds against what the provider reports",
    "M-03": "a declared hard output limit holds",
    "M-04": "every price kind the declaration names is reported, and the kinds add up",
}

SECTIONS: dict[str, str] = {
    "M-01": "§2 The declaration",
    "M-02": "§3 Before the call",
    "M-03": "§3 Before the call",
    "M-04": "§5 After the call",
}

REQUIREMENTS: dict[str, str] = {
    "M-01": "the adapter's declaration validates against Model.json#/$defs/Calculability: "
    "input_count, output_cap, usage_kinds and billing are always present",
    "M-02": "with input_count exact, the count before the call equals the input tokens the "
    "provider reports; with upper_bound it is never below them; estimate and none promise "
    "nothing to hold",
    "M-03": "with output_cap hard, the output tokens the provider reports never exceed the "
    "limit the call set, reasoning included",
    "M-04": "every kind in usage_kinds appears in the usage split by price kind; the input "
    "kinds add up to the input tokens and output to the output tokens",
}

CATALOGUE = Catalogue.build(
    "model/v1",
    "contracts/model/v1/README.md",
    CHECKS,
    REQUIREMENTS,
    SECTIONS,
    unrunnable=frozenset(),
)

MESSAGE_OVERHEAD = 16
REQUEST_OVERHEAD = 16


def dialect_bound(messages: Sequence[Json]) -> int:
    """The chat-completions dialect's upper bound on a prompt's input tokens (README §3): one
    token per UTF-8 byte of every message's content, sixteen per message, sixteen per request.
    A tokenizer that works on bytes emits at most one token per byte; a chat template adds a
    few per message. The model adapter computes the same bound; `tests/contract` holds both to
    it."""
    return REQUEST_OVERHEAD + sum(
        len(str(message.get("content", "")).encode("utf-8")) + MESSAGE_OVERHEAD
        for message in messages
    )


def exchange_violations(exchange: Json) -> list[Violation]:
    """Every rule the exchange breaks: M-02, M-03, M-04."""
    declaration = exchange["declaration"]
    usage = exchange["usage"]
    out: list[Violation] = []
    counted = exchange.get("counted")
    reported = int(usage["tokens_in"])
    how = declaration["input_count"]
    if how in ("exact", "upper_bound") and counted is None:
        out.append(Violation("M-02", f"input_count {how} is declared, and nothing was counted"))
    elif how == "exact" and counted != reported:
        out.append(Violation("M-02", f"counted {counted} exactly, the provider reports {reported}"))
    elif how == "upper_bound" and counted is not None and counted < reported:
        out.append(
            Violation(
                "M-02",
                f"the upper bound {counted} is below the {reported} input tokens the provider "
                "reports: a budget reserved from it would be crossed",
            )
        )
    limit = int(exchange["max_output_tokens"])
    if declaration["output_cap"] == "hard" and int(usage["tokens_out"]) > limit:
        out.append(
            Violation(
                "M-03",
                f"{usage['tokens_out']} output tokens against a hard limit of {limit}",
            )
        )
    by_kind = usage.get("by_kind") or {}
    missing = [kind for kind in declaration["usage_kinds"] if kind not in by_kind]
    if missing:
        out.append(
            Violation("M-04", "the usage does not report " + ", ".join(missing) + ", declared")
        )
    elif by_kind:
        inputs = sum(int(by_kind.get(k, 0)) for k in ("input", "cache_read", "cache_write"))
        if inputs != reported:
            out.append(Violation("M-04", f"the input kinds add up to {inputs}, not to {reported}"))
        if "output" in by_kind and int(by_kind["output"]) != int(usage["tokens_out"]):
            out.append(
                Violation(
                    "M-04", f"output {by_kind['output']} is not the {usage['tokens_out']} reported"
                )
            )
    return out
