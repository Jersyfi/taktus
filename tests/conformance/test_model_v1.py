"""The model contract's checks: the rules against every exchange fixture, and the live suite
against the fake chat-completions endpoint — honest, and with the fault each check must catch."""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fakes import model_service

from taktus.conformance import ModelSuiteOptions, Status, run_model_suite
from taktus.conformance.model import dialect_bound, exchange_violations

ROOT = Path(__file__).resolve().parents[2]
EXCHANGES = ROOT / "contracts" / "model" / "v1" / "examples" / "exchange"
HARD: dict[str, Any] = {
    "contract": "model/v1",
    "input_count": "upper_bound",
    "output_cap": "hard",
    "usage_kinds": ["input", "output"],
    "billing": "per_token",
}
LONG_ANSWER = " ".join(str(n) for n in range(1, 400))


@pytest.mark.parametrize("path", sorted((EXCHANGES / "valid").glob("*.json")), ids=lambda p: p.stem)
def test_a_valid_exchange_breaks_no_rule(path: Path) -> None:
    assert exchange_violations(json.loads(path.read_text())) == []


@pytest.mark.parametrize(
    "path", sorted((EXCHANGES / "invalid").glob("M-*.json")), ids=lambda p: p.stem
)
def test_an_invalid_exchange_breaks_exactly_the_rule_it_is_named_after(path: Path) -> None:
    checks = {v.check for v in exchange_violations(json.loads(path.read_text()))}
    assert checks == {path.name[:4]}


def test_the_adapter_counts_by_the_dialect_rule() -> None:
    from taktus.adapters.driven.models.openai_compatible.client import upper_bound
    from taktus.ports.model import Prompt

    prompt = Prompt(system="Antworte knapp — auf Deutsch.", user="Was ist ein Takt? ☃")
    messages = [
        {"role": "system", "content": prompt.system},
        {"role": "user", "content": prompt.user},
    ]
    assert upper_bound(prompt) == dialect_bound(messages)


@pytest.fixture
def endpoint() -> Iterator[tuple[str, model_service.Script]]:
    server, script = model_service.make_server("127.0.0.1", 0, answer=LONG_ANSWER)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    yield f"http://{host}:{port}", script
    server.shutdown()


async def suite(url: str, declaration: dict[str, Any]) -> dict[str, Status]:
    report = await run_model_suite(
        ModelSuiteOptions(endpoint=url, model="fake-model", declaration=declaration)
    )
    return {r.id: r.status for r in report.checks}


async def test_an_honest_endpoint_passes_every_check(
    endpoint: tuple[str, model_service.Script],
) -> None:
    url, _ = endpoint
    assert set((await suite(url, HARD)).values()) == {Status.PASSED}


async def test_an_endpoint_that_ignores_the_limit_fails_m03(
    endpoint: tuple[str, model_service.Script],
) -> None:
    url, script = endpoint
    script.ignore_limit = True
    statuses = await suite(url, HARD)
    assert statuses["M-03"] is Status.FAILED
    assert {c for c, s in statuses.items() if s is Status.FAILED} == {"M-03"}


async def test_a_soft_limit_claims_nothing_for_m03_to_hold(
    endpoint: tuple[str, model_service.Script],
) -> None:
    url, script = endpoint
    script.ignore_limit = True
    assert (await suite(url, {**HARD, "output_cap": "soft"}))["M-03"] is Status.PASSED


async def test_a_declared_price_kind_the_endpoint_does_not_report_fails_m04(
    endpoint: tuple[str, model_service.Script],
) -> None:
    url, script = endpoint
    declared = {**HARD, "usage_kinds": ["input", "output", "cache_read"]}
    assert (await suite(url, declared))["M-04"] is Status.FAILED
    script.cached = 2
    assert (await suite(url, declared))["M-04"] is Status.PASSED


async def test_an_invalid_declaration_fails_m01_and_calls_nothing(
    endpoint: tuple[str, model_service.Script],
) -> None:
    url, script = endpoint
    declaration = {k: v for k, v in HARD.items() if k != "billing"}
    statuses = await suite(url, declaration)
    assert statuses["M-01"] is Status.FAILED
    assert script.requests == []
