# ruff: noqa: F811 — every test requests the imported fixture `outside` by its name
"""The back-office processes of the blueprint `software-operations` over an account directory
and an audit log, each registered as shipped and run against fakes of the systems behind its
capabilities (UC-03 §4.5; ADR-0209).

The world of `test_software_operations.py`, its engine rebuilt with the connectors of
`directory.accounts` and `audit.events` served in-process over MCP, as the daemon wires them.
`audit.events` is proven over both of its connectors: an organisation's audit log, and a
workspace's activity reports with its token endpoint. What is faked: the directory, the audit
log and the reports (`tests/fakes/`).

What is proven, per process: what it reads, what each rule marks, that a mark is red and an
incident, and that nothing is counted per person (principle 14).
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fakes import FakeIdentifiers, audit_log_service, directory_service, workspace_reports_service
from fakes.maturity import VERIFIED
from fakes.owner_channel import TENANT
from taktus_connectors.githubaudit.operations import Config as LogConfig
from taktus_connectors.githubaudit.server import build_server as log_server
from taktus_connectors.googleworkspace.operations import Config as ReportsConfig
from taktus_connectors.googleworkspace.server import build_server as reports_server
from taktus_connectors.scim.operations import Config as DirectoryConfig
from taktus_connectors.scim.server import build_server as directory_server

from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.adapters.driven.connectors.pool import StaticConnectorPool
from taktus.adapters.driven.memory import MemoryQueue
from taktus.adapters.driven.models import StaticModelPool
from taktus.adapters.driven.telemetry import NoTelemetry
from taktus.adapters.driven.workers.pool import StaticWorkerPool
from taktus.components.reporting.domain.model import Level
from taktus.components.run.application.service import EngineOptions, RunEngine
from taktus.components.run.domain.model import Run, RunState

from .test_software_operations import (
    TOKEN,
    Outside,
    World,
    outside,  # noqa: F401 — the fixture, requested by name
)

ACCOUNT = "audit@project.iam.example"


def service_account_key(email: str) -> str:
    """A service account's key file, as the service hands one out."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()
    return json.dumps({"type": "service_account", "client_email": email, "private_key": pem})


def _serving(server: Any) -> str:
    threading.Thread(target=server.serve_forever, args=(0.05,), daemon=True).start()
    return f"http://127.0.0.1:{server.server_address[1]}"


class BackOffice:
    """The directory, the audit log and the reports, each a fake in a thread."""

    def __init__(self) -> None:
        self.servers = [
            directory_service.make_server("127.0.0.1", 0, {TOKEN}),
            audit_log_service.make_server("127.0.0.1", 0, {TOKEN}),
            workspace_reports_service.make_server("127.0.0.1", 0, {ACCOUNT}),
        ]
        self.directory, self.log, self.reports = [_serving(s) for s in self.servers]

    def stop(self) -> None:
        for server in self.servers:
            server.shutdown()
            server.server_close()


@pytest.fixture
def back_office(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[BackOffice]:
    path = tmp_path / "DIRECTORY_TOKEN"
    path.write_text(TOKEN, encoding="utf-8")
    monkeypatch.setenv("TAKTUS_CREDENTIAL_DIRECTORY_TOKEN_FILE", str(path))
    systems = BackOffice()
    yield systems
    systems.stop()


def audit_credential(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    path = tmp_path / "AUDIT_TOKEN"
    path.write_text(value, encoding="utf-8")
    monkeypatch.setenv("TAKTUS_CREDENTIAL_AUDIT_TOKEN_FILE", str(path))


class BackOfficeWorld(World):
    """The world, its engine serving the directory and one connector of the audit log."""

    def __init__(self, outside: Outside, systems: BackOffice, audit: str = "log") -> None:
        super().__init__(outside)

        def served(server: Any) -> McpActionConnector:
            return McpActionConnector(server, timeout=10.0)

        audit_connector = (
            log_server(LogConfig(systems.log, "example", timeout=5.0))
            if audit == "log"
            else reports_server(
                ReportsConfig(
                    systems.reports, "admin@org.example", f"{systems.reports}/token", timeout=5.0
                )
            )
        )
        connectors = [
            (
                "connector.directory",
                served(directory_server(DirectoryConfig(systems.directory, 5.0))),
            ),
            ("connector.audit", served(audit_connector)),
        ]
        self.engine = RunEngine(
            maturities=VERIFIED,
            runs=self.of(Run),
            work=self.persistence,
            objects=self.objects,
            ledger=self.ledger,
            provenance=self.provenance,
            workers=StaticWorkerPool([]),
            clock=self.clock,
            ids=FakeIdentifiers(),
            telemetry=NoTelemetry(),
            queue=MemoryQueue(self.persistence, self.clock),
            options=EngineOptions(uncalibrated_margin=0.0),
            connectors=StaticConnectorPool(connectors),
            models=StaticModelPool(),
        )

    async def ready(self) -> BackOfficeWorld:
        await super().ready()
        return self


def replace(url: str, records: list[dict[str, Any]]) -> None:
    httpx.post(url, content=json.dumps(records), timeout=5).raise_for_status()


def failures(run: Run) -> list[tuple[str, str | None]]:
    return [(s.step_id, s.reason) for s in run.step_runs]


# --- B-5.03 Access review ------------------------------------------------------------------


async def test_b_5_03_marks_inactive_accounts_with_groups_and_over_privileged_members(
    outside: Outside, back_office: BackOffice
) -> None:
    w = await BackOfficeWorld(outside, back_office).ready()
    version = await w.registered("B-5.03-access-review.yaml")
    for signal, step in (
        ("access.inactive_with_groups", "inactive"),
        ("access.over_privileged", "over-privileged"),
    ):
        await w.corridor(
            signal, version.process_id, step=step, select="count", bounds="fixed",
            direction="above", yellow=0.25, red=0.5,
        )  # fmt: skip
    run = await w.start(version, privileged="Admins")
    assert run.state is RunState.FINISHED, failures(run)
    # The fake directory: u4 is inactive and still in Admins; Admins holds u1 and u4.
    inactive = await w.result(run, "inactive")
    assert [a["id"] for a in inactive["items"]] == ["u4"]
    over = await w.result(run, "over-privileged")
    assert [a["id"] for a in over["items"]] == ["u4"]
    looked = await w.signals.watch.look(TENANT)
    assert {j.level for j in looked.judged} == {Level.RED}
    assert len(looked.incidents) == 2
    text = json.dumps(await w.result(run, "accounts"))
    assert "person1@" not in text and "Family" not in text, "no personal data is read"


async def test_b_5_03_a_service_account_in_the_privileged_group_is_over_privileged(
    outside: Outside, back_office: BackOffice
) -> None:
    groups = directory_service.default_groups()
    groups[0]["members"].append({"value": "u5", "type": "User"})
    replace(f"{back_office.directory}/_fake/groups", groups)
    w = await BackOfficeWorld(outside, back_office).ready()
    version = await w.registered("B-5.03-access-review.yaml")
    run = await w.start(version, privileged="Admins")
    assert run.state is RunState.FINISHED, failures(run)
    over = await w.result(run, "over-privileged")
    assert [a["id"] for a in over["items"]] == ["u4", "u5"]


async def test_b_5_03_a_privileged_group_the_directory_does_not_hold_fails_the_reading(
    outside: Outside, back_office: BackOffice
) -> None:
    w = await BackOfficeWorld(outside, back_office).ready()
    version = await w.registered("B-5.03-access-review.yaml")
    run = await w.start(version, privileged="Nobody")
    assert run.state is not RunState.FINISHED
    assert run.step_run("over-privileged").checkpoint is None, "nothing is marked on no reading"


# --- B-5.04 Auditing privileged actions ----------------------------------------------------


def _events() -> list[dict[str, Any]]:
    """A day's actions: an escalation, sixty repositories created, and one at night."""
    now = datetime.now(UTC)
    night_minutes = (now.hour * 60 + now.minute - 150) % 1440 + 1  # the last half past two UTC
    event = audit_log_service.audit_event
    found = [event(1, "org.add_billing_manager", 10, user="new-billing")]
    found += [event(10 + n, "repo.create", 1 + n / 60, repo=f"example/r{n}") for n in range(60)]
    found.append(event(99, "team.add_member", night_minutes, team="example/core"))
    assert time.time() - found[-1]["@timestamp"] / 1000 < 24 * 3600
    return found


@pytest.mark.parametrize("audit", ["log", "reports"])
async def test_b_5_04_marks_escalations_and_mass_changes_by_rule_and_never_per_person(
    outside: Outside,
    back_office: BackOffice,
    audit: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if audit == "log":
        audit_credential(tmp_path, monkeypatch, TOKEN)
        replace(f"{back_office.log}/_fake/events", _events())
    else:
        audit_credential(tmp_path, monkeypatch, service_account_key(ACCOUNT))
        activity = workspace_reports_service.activity
        items = [activity(1, "DELEGATED_ADMIN_SETTINGS", "ASSIGN_ROLE", 10, ROLE_NAME="Admin")]
        items += [activity(10 + n, "GROUP_SETTINGS", "CREATE_GROUP", 1 + n / 60) for n in range(60)]
        replace(f"{back_office.reports}/_fake/activities", items)
    w = await BackOfficeWorld(outside, back_office, audit).ready()
    version = await w.registered("B-5.04-privileged-actions.yaml")
    for step in ("escalations", "mass-changes"):
        await w.corridor(
            f"audit.{step.replace('-', '_')}", version.process_id, step=step,
            select="count", bounds="fixed", direction="above", yellow=0.25, red=0.5,
        )  # fmt: skip
    run = await w.start(version)
    assert run.state is RunState.FINISHED, "at level 1 it runs without a person"
    escalations = await w.result(run, "escalations")
    assert escalations["count"] == 1 and escalations["first"]["escalation"] is True
    mass = await w.result(run, "mass-changes")
    assert mass["count"] == 1 and mass["first"]["count"] == 60
    assert set(mass["first"]) == {"action", "count"}, "counted per action, never per actor"
    looked = await w.signals.watch.look(TENANT)
    assert {j.level for j in looked.judged} == {Level.RED} and len(looked.incidents) == 2


async def test_b_5_04_an_action_outside_the_organisation_s_window_is_marked(
    outside: Outside, back_office: BackOffice, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audit_credential(tmp_path, monkeypatch, TOKEN)
    replace(f"{back_office.log}/_fake/events", _events())
    w = await BackOfficeWorld(outside, back_office).ready()
    version = await w.registered("B-5.04-privileged-actions.yaml")
    run = await w.start(version)
    assert run.state is RunState.FINISHED, failures(run)
    outside_window = await w.result(run, "outside-window")
    hours = {e["hour"] for e in outside_window["items"]}
    assert 2 in hours and all(h <= 5 or h >= 21 for h in hours)
    assert "team.add_member" in {e["action"] for e in outside_window["items"]}


async def test_b_5_04_a_quiet_day_marks_nothing(
    outside: Outside, back_office: BackOffice, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audit_credential(tmp_path, monkeypatch, TOKEN)
    quiet = [audit_log_service.audit_event(1, "repo.create", 10, repo="example/one")]
    replace(f"{back_office.log}/_fake/events", quiet)
    w = await BackOfficeWorld(outside, back_office).ready()
    version = await w.registered("B-5.04-privileged-actions.yaml")
    run = await w.start(version)
    assert run.state is RunState.FINISHED, failures(run)
    assert (await w.result(run, "escalations"))["count"] == 0
    assert (await w.result(run, "mass-changes"))["count"] == 0
