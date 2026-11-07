"""The product analytics connector reads aggregate event counts in the output of the analytics
connector, refuses what does not add up truthfully, and passes on no person, against the fake
Query API (`analytics.reports`, UC-7.7).

The fake under `tests/fakes/product_analytics_service.py` runs in a thread of this process; the
connector is served in-process over MCP, as an instance reaches it.
"""

from __future__ import annotations

import secrets
import threading
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import pytest
from fakes import product_analytics_service
from taktus_connectors.mixpanel.operations import Config
from taktus_connectors.mixpanel.server import build_server

from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.ports.connector import CallContext, CallFailed, idempotency_key
from taktus.ports.worker import CredentialReference

ACCOUNT = f"taktus-reader.{secrets.token_hex(4)}.mp-service-account:{secrets.token_hex(16)}"
KEYS = {"dimensions", "metrics", "rows", "row_count", "complete", "sampled", "thresholded",
        "other_row"}  # fmt: skip
"""The output of `analytics.reports.run`, as the analytics connector (`googleanalytics/`)
answers it."""


@pytest.fixture(autouse=True)
def credentials(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "ANALYTICS_KEY"
    path.write_text(ACCOUNT, encoding="utf-8")
    monkeypatch.setenv("TAKTUS_CREDENTIAL_ANALYTICS_KEY_FILE", str(path))


@pytest.fixture
def service() -> Iterator[str]:
    server = product_analytics_service.make_server("127.0.0.1", 0, {ACCOUNT})
    threading.Thread(target=server.serve_forever, args=(0.05,), daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def context(name: str = "ANALYTICS_KEY") -> CallContext:
    return CallContext(
        tenant="default",
        identity="idn_analysis",
        run_id="run_analysis",
        step_id="report",
        attempt=1,
        idempotency_key=idempotency_key("run_analysis", "report", 1),
        credentials=(CredentialReference(name=name, injected_as="env"),),
    )


def connector(url: str, project: str = product_analytics_service.PROJECT) -> McpActionConnector:
    return McpActionConnector(build_server(Config(url, project, timeout=5.0)))


def state(url: str) -> dict[str, Any]:
    found: dict[str, Any] = httpx.get(f"{url}/_fake/state", timeout=5).json()
    return found


def fail(url: str, status: int) -> None:
    httpx.post(f"{url}/_fake/fail", json={"status": status}, timeout=5).raise_for_status()


async def test_weekly_unique_users_are_read_in_the_analytics_output(service: str) -> None:
    result = await connector(service).call(
        "analytics.reports.run",
        context(),
        {"events": ["sign up"], "dimensions": ["week"], "metrics": ["unique", "general"],
         "start": "55daysAgo", "end": "yesterday", "order": "week"},
    )  # fmt: skip
    assert result.effect.kind.value == "read"
    output = result.output
    assert set(output) == KEYS
    assert output["dimensions"] == ["week"] and output["metrics"] == ["unique", "general"]
    weeks = [r["dimensions"]["week"] for r in output["rows"]]
    assert weeks == sorted(weeks) and 8 <= len(weeks) <= 9
    assert all(date.fromisoformat(w).weekday() == 0 for w in weeks)
    for row in output["rows"]:
        assert isinstance(row["metrics"]["unique"], str)
        assert int(row["metrics"]["unique"]) < int(row["metrics"]["general"])
    assert output["complete"] is True and output["row_count"] == len(weeks)
    assert output["sampled"] is False and output["thresholded"] is False
    asked = state(service)["asked"]
    assert [q["type"] for q in asked] == ["unique", "general"]
    assert {q["unit"] for q in asked} == {"week"} and asked[0]["project_id"] == "1234567"
    assert ACCOUNT not in str(output)


async def test_events_are_broken_down_by_event_and_summed_without_it(service: str) -> None:
    by_event = await connector(service).call(
        "analytics.reports.run",
        context(),
        {"events": ["sign up", "purchase"], "dimensions": ["event"], "metrics": ["general"],
         "start": "6daysAgo", "end": "today", "order": "-general"},
    )  # fmt: skip
    rows = by_event.output["rows"]
    assert [r["dimensions"]["event"] for r in rows] == ["sign up", "purchase"]
    total = await connector(service).call(
        "analytics.reports.run",
        context(),
        {"events": ["sign up", "purchase"], "metrics": ["general"], "start": "6daysAgo",
         "end": "today"},
    )  # fmt: skip
    assert total.output["rows"] == [
        {"dimensions": {}, "metrics": {"general": str(sum(int(r["metrics"]["general"])
                                                          for r in rows))}}
    ]  # fmt: skip


async def test_a_report_cut_at_its_limit_says_it_is_incomplete(service: str) -> None:
    result = await connector(service).call(
        "analytics.reports.run",
        context(),
        {"events": ["page view"], "dimensions": ["day"], "metrics": ["general"],
         "start": "27daysAgo", "end": "today", "limit": 7},
    )  # fmt: skip
    assert len(result.output["rows"]) == 7
    assert result.output["row_count"] == 28 and result.output["complete"] is False


@pytest.mark.parametrize(
    "input",
    [
        {"metrics": ["sessions"]},
        {"metrics": ["newUsers"]},
        {"dimensions": ["isoYearIsoWeek"]},
        {"dimensions": ["$distinct_id"]},
        {"dimensions": ["day", "week"]},
        {"metrics": ["unique"], "dimensions": []},
        {"metrics": ["average"], "events": ["sign up", "purchase"]},
        {"events": []},
        {"start": "last week"},
        {"start": "today", "end": "7daysAgo"},
        {"limit": 10001},
        {"order": "event"},
    ],
)
async def test_what_the_api_cannot_answer_truthfully_never_reaches_it(
    service: str, input: dict[str, object]
) -> None:
    given = {"events": ["sign up"], "dimensions": ["day"], "metrics": ["general"],
             "start": "7daysAgo", "end": "today", **input}  # fmt: skip
    with pytest.raises(CallFailed) as failed:
        await connector(service).call("analytics.reports.run", context(), given)
    assert failed.value.error.cause.value == "invalid"
    assert state(service)["queries"] == 0


async def test_another_project_is_forbidden(service: str) -> None:
    with pytest.raises(CallFailed) as failed:
        await connector(service, "42").call(
            "analytics.reports.run",
            context(),
            {"events": ["sign up"], "metrics": ["general"], "start": "today", "end": "today"},
        )
    assert failed.value.error.cause.value == "forbidden"


@pytest.mark.parametrize(("status", "cause"), [(429, "unavailable"), (503, "unavailable"),
                                               (400, "invalid"), (418, "unexpected")])  # fmt: skip
async def test_the_api_s_answers_map_to_the_contract_s_causes(
    service: str, status: int, cause: str
) -> None:
    fail(service, status)
    with pytest.raises(CallFailed) as failed:
        await connector(service).call(
            "analytics.reports.run",
            context(),
            {"events": ["sign up"], "metrics": ["general"], "start": "today", "end": "today"},
        )
    assert failed.value.error.cause.value == cause


async def test_a_service_account_the_api_does_not_admit_is_unauthenticated(
    service: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "OTHER"
    path.write_text("someone:wrong-secret", encoding="utf-8")
    monkeypatch.setenv("TAKTUS_CREDENTIAL_OTHER_FILE", str(path))
    with pytest.raises(CallFailed) as failed:
        await connector(service).call(
            "analytics.reports.run",
            context("OTHER"),
            {"events": ["sign up"], "metrics": ["general"], "start": "today", "end": "today"},
        )
    assert failed.value.error.cause.value == "unauthenticated"
    assert "wrong-secret" not in failed.value.error.detail
