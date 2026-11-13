"""`taktusctl health`, `taktusctl backup list` and `taktusctl update`: the instance's health, the
backup's listing, and an update of Taktus prepared and commissioned as a plan, which applies
nothing (ADR-0295, ADR-0296, UC-10.2)."""

from __future__ import annotations

import asyncio
import os
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

from taktus.adapters.driving.inventory import READ, READS
from taktus.composition.local import LocalWiring

from .test_first_slice import PLAIN, taktusctl


def ctl(state: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 — our own entry point, fixed arguments
        [taktusctl(), *arguments, "--state-dir", str(state)],
        capture_output=True,
        text=True,
        env={**os.environ, **PLAIN},
        check=False,
    )


def test_the_health_and_the_backup_are_read_on_the_command_line(tmp_path: Path) -> None:
    state = tmp_path / "state"
    health = ctl(state, "health")
    assert health.returncode == 0, health.stdout + health.stderr
    for line in ("release ", "ready       yes", "backup      not recorded", "0 in effect"):
        assert line in health.stdout
    assert "incidents   0 open" in health.stdout
    listed = ctl(state, "backup", "list")
    assert listed.returncode == 0, listed.stdout + listed.stderr
    assert "no backup recorded" in listed.stdout
    assert "TAKTUS_BACKUP_EXPECTED_HOURS is not set" in listed.stdout


def test_an_update_is_prepared_and_commissioned_by_a_person_and_applies_nothing(
    tmp_path: Path,
) -> None:
    state = tmp_path / "state"
    for name, role in (("idn_admin", "admin"), ("idn_bob", "clerk")):
        added = ctl(state, "identity", "add", name, "--role", role)
        assert added.returncode == 0, added.stdout + added.stderr
    assert (
        ctl(
            state, "identity", "grant", "--role", "admin", "--right", "tenant.administer"
        ).returncode
        == 0
    )
    due = (datetime.now(UTC) + timedelta(days=3)).date().isoformat()

    def prepared(who: str) -> str:
        done = ctl(
            state,
            "update",
            "prepare",
            "--to",
            "1.0.1",
            "--due",
            due,
            "--level",
            "1",
            "--reason",
            "a person carries out every step",
            "--identity",
            who,
        )
        assert done.returncode == 0, done.stdout + done.stderr
        assert "backup: " in done.stdout and "check: " in done.stdout
        assert "lacks" not in done.stdout
        return done.stdout.split()[2].rstrip(",")

    refused = ctl(state, "update", "commission", prepared("idn_bob"), "--identity", "idn_bob")
    assert refused.returncode == 2 and "tenant.administer" in refused.stderr
    done = ctl(state, "update", "commission", prepared("idn_admin"), "--identity", "idn_admin")
    assert done.returncode == 0, done.stdout + done.stderr
    assert "commissioned by idn_admin; nothing was applied" in done.stdout


READ_COMMANDS: dict[str, tuple[str, ...]] = {
    "tenant.list": ("tenant", "list"),
    "identity.links": ("identity", "links"),
    "identity.rights": ("identity", "rights"),
    "units.show": ("units", "show"),
    "structure.show": ("structure", "show"),
    "structure.where": ("structure", "where", "process", "invoices"),
    "adapter.list": ("conformance", "list"),
    "backup.list": ("backup", "list"),
    "instance.health": ("health",),
}


def test_every_act_that_reads_is_a_ledger_entry_on_the_command_line(tmp_path: Path) -> None:
    """UC-10.2 §2 on the command line: each act of the inventory that reads leaves
    `administration.read` naming the act and `--identity`, and nothing of what was read
    (NTC-0273). An act that changes something is recorded by the use case it calls, the same
    the HTTP surface calls."""
    assert set(READ_COMMANDS) == READS
    state = tmp_path / "state"
    for act, words in READ_COMMANDS.items():
        done = ctl(state, *words, "--identity", "idn_reader")
        assert done.returncode in (0, 1), f"{act}: {done.stdout}{done.stderr}"

    async def read() -> list[tuple[str | None, str | None, str | None]]:
        async with LocalWiring().services(
            state_dir=state, worker_endpoint="http://127.0.0.1:1"
        ) as services:
            async with services.work.transaction("default"):
                found = await services.ledger.entries("default")
        return [(e.refs.action, e.refs.actor, e.content_digest) for e in found if e.kind == READ]

    assert sorted(asyncio.run(read())) == sorted((act, "idn_reader", None) for act in READ_COMMANDS)
