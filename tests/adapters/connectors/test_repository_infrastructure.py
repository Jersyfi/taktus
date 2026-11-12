"""The repository connector's infrastructure operations (ADR-0201), against the fake service:
a lost run rerun and a hung one cancelled, each once however often the call repeats; the
runners, the branches, the rate limit and the dependency alerts read, never a person.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from taktus_connectors.github.server import Config, Connector

from .conftest import Service

type Json = dict[str, Any]

REPOSITORY = "acme/infrastructure"

pytestmark = pytest.mark.usefixtures("credentials")


def context(key: str) -> Json:
    return {
        "tenant": "default",
        "identity": "idn_ops",
        "run_id": "run_01",
        "step_id": "s",
        "attempt": 1,
        "idempotency_key": key,
        "credentials": [{"name": "REPOSITORY_TOKEN", "injected_as": "env"}],
    }


async def call(service: Service, operation: str, input: Json, key: str = "k" * 20) -> Json:
    """Through a fresh connector each time: it remembers nothing of an earlier call."""
    connector = Connector(Config(target=service.url, repository=REPOSITORY, timeout=5.0))
    result = await connector.call(operation, context(key), input)
    assert isinstance(result.structured_content, dict)
    body: Json = result.structured_content
    if result.is_error:
        return {"error": body}
    return body


def fake(service: Service, path: str, body: Json) -> Any:
    answer = httpx.post(f"{service.url}{path}", json={"repository": REPOSITORY, **body}, timeout=5)
    answer.raise_for_status()
    return answer.json()


def runs(service: Service) -> list[Json]:
    answer = httpx.get(
        f"{service.url}/repos/{REPOSITORY}/actions/runs",
        headers={"Authorization": f"Bearer {service.write_value}"},
        timeout=5,
    )
    found: list[Json] = answer.json()["workflow_runs"]
    return found


async def test_a_completed_run_is_rerun_once_for_the_attempt_that_was_read(
    service: Service,
) -> None:
    fake(service, "/_fake/run", {"branch": "main", "conclusion": "failure"})
    (failed,) = [r for r in runs(service) if r["conclusion"] == "failure"]
    first = await call(service, "repository.pipelines.rerun", {"run": failed["id"], "attempt": 1})
    assert first["output"]["rerun"] is True and first["output"]["attempt"] == 2
    assert first["effect"]["replayed"] is False
    again = await call(service, "repository.pipelines.rerun", {"run": failed["id"], "attempt": 1})
    assert again["output"]["rerun"] is False and again["effect"]["replayed"] is True
    (now,) = [r for r in runs(service) if r["id"] == failed["id"]]
    assert now["run_attempt"] == 2, "a repeat reran nothing"


async def test_a_run_not_completed_is_not_rerun(service: Service) -> None:
    fake(service, "/_fake/ci", {"pending": True})
    try:
        await call(
            service,
            "repository.branches.create",
            {
                "name": "work",
                "base": "main",
                "message": "m",
                "files": [{"path": "a", "content": "b"}],
            },
        )
        (pending,) = [r for r in runs(service) if r["status"] == "in_progress"]
        refused = await call(
            service, "repository.pipelines.rerun", {"run": pending["id"], "attempt": 1}
        )
        assert refused["error"]["cause"] == "conflict"
        cancelled = await call(service, "repository.pipelines.cancel", {"run": pending["id"]})
        assert cancelled["output"]["cancelled"] is True
        again = await call(service, "repository.pipelines.cancel", {"run": pending["id"]})
        assert again["output"]["cancelled"] is False and again["effect"]["replayed"] is True
        (now,) = [r for r in runs(service) if r["id"] == pending["id"]]
        assert now["conclusion"] == "cancelled"
    finally:
        fake(service, "/_fake/ci", {"pending": False})


@pytest.mark.parametrize(
    "input", [{"run": "x", "attempt": 1}, {"run": 1}, {"run": 1, "attempt": 0}]
)
async def test_a_rerun_that_names_no_run_or_attempt_is_invalid(
    service: Service, input: Json
) -> None:
    refused = await call(service, "repository.pipelines.rerun", input)
    assert refused["error"]["cause"] == "invalid"


async def test_the_runners_are_listed_with_those_offline_counted(service: Service) -> None:
    fake(service, "/_fake/runner", {"name": "build-1"})
    fake(service, "/_fake/runner", {"name": "build-2", "status": "offline"})
    listed = (await call(service, "repository.runners.list", {}))["output"]
    assert [r["name"] for r in listed["runners"]] == ["build-1", "build-2"]
    assert listed["offline"] == 1 and listed["complete"] is True
    assert listed["runners"][0]["labels"] == ["self-hosted"]


async def test_the_branches_are_listed_page_by_page_and_by_protection(service: Service) -> None:
    for n in range(120):
        service.branch(REPOSITORY, f"b-{n:03d}")
    fake(service, "/_fake/protect", {"branch": "main"})
    every = await call(service, "repository.branches.list", {})
    assert every["output"]["count"] == 121 and every["output"]["complete"] is True
    assert every["consumption"]["quota_units"] == 2, "two pages of 100"
    protected = (await call(service, "repository.branches.list", {"protected": True}))["output"]
    (main,) = protected["branches"]
    assert main["name"] == "main" and main["protected"] is True and main["head_sha"]


async def test_the_rate_limit_is_read_fullest_first_as_decimal_text(service: Service) -> None:
    read = (await call(service, "repository.ratelimit.read", {}))["output"]
    names = [r["resource"] for r in read["resources"]]
    assert names[0] == "core" and set(names) == {"core", "search", "graphql"}
    core = read["resources"][0]
    assert core["limit"] == 5000 and core["used"] >= 1
    assert core["used_share"] == f"0.{core['used'] * 10_000 // 5000:04d}"
    assert 0 <= core["reset_minutes"] <= 30


async def test_the_open_alerts_are_listed_without_a_person(service: Service) -> None:
    fake(service, "/_fake/alert", {"package": "requests", "patched": "2.32.0", "severity": "high"})
    fake(service, "/_fake/alert", {"package": "jinja2", "severity": "low", "state": "fixed"})
    fake(service, "/_fake/alert", {"package": "urllib3", "severity": "critical"})
    read = (await call(service, "repository.advisories.list", {}))["output"]
    assert [a["package"] for a in read["alerts"]] == ["urllib3", "requests"]
    first = read["alerts"][1]
    assert first["patched"] == "2.32.0" and first["severity"] == "high"
    assert first["ghsa_id"].startswith("GHSA-") and first["age_days"] == 0
    assert "person" not in str(read), "a dismisser or an assignee is never copied (principle 14)"
    critical = await call(service, "repository.advisories.list", {"severity": ["critical"]})
    assert [a["package"] for a in critical["output"]["alerts"]] == ["urllib3"]
    refused = await call(service, "repository.advisories.list", {"state": "gone"})
    assert refused["error"]["cause"] == "invalid"
