"""The software business's processes built in the remainders of release 1.0, run against fakes of
the systems behind their capabilities (UC-03, DEC-0228).

The world is `test_software_operations.py`'s, with a browser worker in place of the fake one: it
answers each assignment with the report the browser worker's last step writes (ADR-0218,
ADR-0234).
"""

from __future__ import annotations

import json
from typing import Any

from fakes import FakeWorker, InnerStep

from taktus.adapters.driven.workers.pool import StaticWorkerPool
from taktus.components.run.domain.model import RunState

from .test_software_operations import Outside, World, outside

__all__ = ["outside"]

BROWSER = ("browser.check", "browser.headless", "workspace.isolated")


def report(*pages: dict[str, Any]) -> bytes:
    """The gathered report of the browser worker, as `worker.gathered` writes it."""
    failed = [p["name"] for p in pages if not p["passed"]]
    return json.dumps(
        {
            "checks": list(pages),
            "count": len(pages),
            "passed": len(pages) - len(failed),
            "failed": len(failed),
            "failures": failed,
        },
        sort_keys=True,
    ).encode()


def page(name: str, findings: list[str], exposed: list[str] | None = None) -> dict[str, Any]:
    return {
        "name": name,
        "url": f"https://app.example/{name}",
        "passed": not findings,
        "security": {
            "https": True,
            "tls": "TLS 1.3",
            "headers_missing": [f.split()[2] for f in findings if f.endswith("is missing")],
            "disclosed": [],
            "cookies": [],
            "exposed": exposed or [],
            "findings": findings,
        },
    }


def browsing(w: World, *pages: dict[str, Any]) -> FakeWorker:
    worker = FakeWorker(
        capabilities_offered=BROWSER,
        json_artifacts=frozenset({"report"}),
        script=(InnerStep("report", artifacts=(("report", report(*pages)),)),),
    )
    w.engine._workers = StaticWorkerPool([("worker.browser", worker)])
    return worker


async def test_b_7_09_files_a_page_that_gives_something_away_once_and_tries_nothing_on_it(
    outside: Outside,
) -> None:
    w = await World(outside).ready()
    version = await w.registered("B-7.09-security-check.yaml")
    worker = browsing(
        w,
        page("start", []),
        page("login", ["the header content-security-policy is missing"], ["/.env"]),
    )
    before = len(outside.issues())
    run = await w.confirmed(await w.start(version))
    assert run.state is RunState.FINISHED, [(s.step_id, s.reason) for s in run.step_runs]
    (assignment,) = worker.assignments
    assert assignment.task.inputs["security"] is True, "every page is a security check"
    assert assignment.frame.allowed_hosts == ("app.example",), "the tenant's own host only"
    [filed] = outside.issues()[: len(outside.issues()) - before]
    assert filed["title"] == "login"
    assert "security-check:login" in filed["body"]
    assert "content-security-policy" in filed["body"] and "/.env" in filed["body"]
    assert "Nothing was tried on the application" in filed["body"]

    again = await w.confirmed(await w.start(version))
    assert again.state is RunState.FINISHED
    assert (await w.result(again, "exposed"))["count"] == 0, "filed once, never twice"
    assert len(outside.issues()) == before + 1


async def test_b_7_09_a_page_without_findings_files_nothing(outside: Outside) -> None:
    w = await World(outside).ready()
    version = await w.registered("B-7.09-security-check.yaml")
    browsing(w, page("start", []))
    before = len(outside.issues())
    run = await w.confirmed(await w.start(version))
    assert run.state is RunState.FINISHED
    assert (await w.result(run, "exposed"))["count"] == 0
    assert len(outside.issues()) == before
