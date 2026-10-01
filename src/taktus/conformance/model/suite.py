"""The suite: M-01 to M-04 against a live endpoint that speaks the chat-completions dialect.

The inputs are the endpoint, the model it is asked for, and the declaration the adapter makes
for that endpoint (`Model.json#/$defs/Calculability`). The suite validates the declaration
(M-01), then makes two calls and holds each to it:

1. `short` — a prompt with a short answer, within a generous limit. The count before the call,
   by the rule the declaration names, against the input tokens the provider reports (M-02); the
   price kinds the declaration names against the usage the provider reports (M-04).
2. `capped` — a prompt that asks for far more than a limit of sixteen tokens. With a hard
   output limit declared, the provider must stop at it (M-03).

What the dialect cannot count exactly — it has no count endpoint — the suite does not pretend
to: a declaration of `exact` over the dialect is judged by the dialect's bound, and a mismatch
says so. The credential is read from the environment by name and sent as a bearer value; it is
never printed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from taktus.conformance.contracts import first_error
from taktus.conformance.findings import Findings
from taktus.conformance.model.rules import CATALOGUE, CHECKS, dialect_bound, exchange_violations
from taktus.conformance.report import Report

type Json = dict[str, Any]

CAP = 16
SHORT: list[Json] = [
    {"role": "system", "content": "Answer with one word."},
    {"role": "user", "content": "Is water wet? Answer yes or no."},
]
LONG: list[Json] = [
    {"role": "user", "content": "Count from 1 to 2000, one number per line, and nothing else."}
]


@dataclass
class ModelSuiteOptions:
    endpoint: str
    model: str
    declaration: Json
    credential_value: str | None = None
    timeout: float = 120.0


async def run_model_suite(options: ModelSuiteOptions) -> Report:
    report = Report(endpoint=options.endpoint, contract=CATALOGUE.contract)
    findings = Findings(CHECKS)
    declaration = options.declaration
    why = first_error("Calculability", declaration, "model/v1")
    if why is not None:
        findings.fail("M-01", f"the declaration is invalid: {why}")
    else:
        findings.ok(
            "M-01",
            f"input_count {declaration['input_count']}, output_cap {declaration['output_cap']}, "
            f"billing {declaration['billing']}, reports {', '.join(declaration['usage_kinds'])}",
        )
    if why is None:
        headers = {"Content-Type": "application/json"}
        if options.credential_value:
            headers["Authorization"] = f"Bearer {options.credential_value}"
        async with httpx.AsyncClient(timeout=options.timeout, headers=headers) as client:
            try:
                short = await _call(client, options, SHORT, 256)
                _judge("short", short, findings)
                if declaration["output_cap"] == "hard":
                    capped = await _call(client, options, LONG, CAP)
                    _judge("capped", capped, findings)
                else:
                    findings.ok(
                        "M-03",
                        f"not claimed: the output limit is declared {declaration['output_cap']}, "
                        "so a budget over this model holds its money only as an estimate",
                    )
            except (httpx.HTTPError, _Unanswered) as error:
                report.notes.append(f"the endpoint {options.endpoint} did not answer: {error}")
                for check in ("M-02", "M-03", "M-04"):
                    if not findings.evidence[check] and not findings.violations[check]:
                        findings.inconclusive[check] = "not reached: the endpoint did not answer"
    for check in CHECKS:
        report.add(findings.result(check))
    return report.finish()


class _Unanswered(Exception):
    pass


async def _call(
    client: httpx.AsyncClient, options: ModelSuiteOptions, messages: list[Json], limit: int
) -> Json:
    """One call, as an exchange: the declaration, the count before it by the dialect's rule, the
    limit, and the usage split by price kind as the endpoint reports it."""
    response = await client.post(
        f"{options.endpoint.rstrip('/')}/chat/completions",
        json={"model": options.model, "messages": messages, "max_tokens": limit},
    )
    if response.status_code >= 400:
        raise _Unanswered(f"status {response.status_code}")
    try:
        document = response.json()
        usage = document["usage"]
        tokens_in = int(usage["prompt_tokens"])
        tokens_out = int(usage["completion_tokens"])
        finish = str(document["choices"][0].get("finish_reason") or "")
    except (ValueError, KeyError, IndexError, TypeError) as error:
        raise _Unanswered(f"an answer outside the dialect: {type(error).__name__}") from error
    details = usage.get("prompt_tokens_details") or {}
    by_kind: Json = {}
    read = int(details.get("cached_tokens") or 0) if "cached_tokens" in details else None
    written = (
        int(details.get("cache_write_tokens") or 0) if "cache_write_tokens" in details else None
    )
    by_kind["input"] = tokens_in - (read or 0) - (written or 0)
    by_kind["output"] = tokens_out
    if read is not None:
        by_kind["cache_read"] = read
    if written is not None:
        by_kind["cache_write"] = written
    exchange: Json = {
        "declaration": options.declaration,
        "max_output_tokens": limit,
        "finish": {"stop": "stop", "length": "length"}.get(finish, "other"),
        "usage": {
            "model": str(document.get("model") or options.model),
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "by_kind": by_kind,
        },
    }
    if options.declaration["input_count"] != "none":
        exchange["counted"] = dialect_bound(messages)
    return exchange


def _count(details: Json, name: str) -> int | None:
    """A count the endpoint reports, or None when it does not report that kind at all."""
    return int(details.get(name) or 0) if name in details else None


def _judge(purpose: str, exchange: Json, findings: Findings) -> None:
    for violation in exchange_violations(exchange):
        findings.add(violation, f"{purpose} call")
    usage = exchange["usage"]
    if purpose == "short":
        if not findings.violations["M-02"]:
            findings.ok(
                "M-02",
                f"counted {exchange.get('counted', 'nothing')} before the call "
                f"({exchange['declaration']['input_count']}); the provider reports "
                f"{usage['tokens_in']}",
            )
        if not findings.violations["M-04"]:
            findings.ok("M-04", f"reported {', '.join(sorted(usage['by_kind']))}")
    elif not findings.violations["M-03"]:
        findings.ok(
            "M-03",
            f"{usage['tokens_out']} output tokens against a hard limit of "
            f"{exchange['max_output_tokens']}",
        )
