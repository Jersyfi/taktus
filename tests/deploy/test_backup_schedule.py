"""The backup's schedule on one machine (ADR-0222): a backup every period, a drill after the
backup of every drill period, a drill that fails recorded as a failed run at the step `drill`,
and a round that fails never ending the schedule."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from deploy.backup_program import backup
from taktus.ports.backups import REASONS

START = datetime(2026, 11, 7, 2, 0, tzinfo=UTC)


class Clock:
    def __init__(self) -> None:
        self.now = START
        self.slept: list[float] = []

    def __call__(self) -> datetime:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += timedelta(seconds=seconds)


def environment(tmp_path: Path, **more: str) -> dict[str, str]:
    url = tmp_path / "url"
    url.write_text("postgresql://backup:pw@db:5432/taktus\n", encoding="utf-8")
    return {
        "TAKTUS_DATABASE_URL_FILE": str(url),
        "TAKTUS_BACKUP_STORE_DIRECTORY": str(tmp_path),
        **more,
    }


def scheduled(
    monkeypatch: pytest.MonkeyPatch, *, drill_fails: bool = False, backup_fails: bool = False
) -> tuple[list[str], list[dict[str, Any]]]:
    calls: list[str] = []
    recorded: list[dict[str, Any]] = []
    real_main = backup.main

    def main(argv: list[str], env: dict[str, str]) -> int:
        if argv[0] == "schedule":
            return real_main(argv, env)
        calls.append(argv[0])
        if argv[0] == "backup":
            return 1 if backup_fails else 0
        return 1 if drill_fails else 0

    monkeypatch.setattr(backup, "main", main)
    monkeypatch.setattr(backup, "record_outcome", lambda *a, **k: recorded.append(k) or True)
    return calls, recorded


def test_a_backup_every_day_and_a_drill_after_the_backup_of_every_week(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls, recorded = scheduled(monkeypatch)
    clock = Clock()
    assert backup.schedule(environment(tmp_path), clock=clock, sleep=clock.sleep, rounds=9) == 0
    assert calls.count("backup") == 9
    assert calls.count("drill") == 2, "the first round and the eighth"
    assert calls[:2] == ["backup", "drill"] and calls[2] == "backup"
    assert set(clock.slept) == {24 * 3600.0}
    assert recorded == [], "a drill that verified records nothing beyond the backup's own"


def test_a_drill_that_fails_is_recorded_as_a_failed_run_at_the_step_drill(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, recorded = scheduled(monkeypatch, drill_fails=True)
    clock = Clock()
    backup.schedule(environment(tmp_path), clock=clock, sleep=clock.sleep, rounds=1)
    (one,) = recorded
    assert one["step"] == "drill" and "drill" in REASONS
    assert backup.NAME.match(f"{one['name']}.json") is not None
    assert one["name"] != backup.name_at(START), "not the backup's own name"
    assert "drill" in backup.outcome_sql(one["name"], one["at"], "drill")


def test_a_failed_round_never_ends_the_schedule_and_the_periods_are_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls, _ = scheduled(monkeypatch, backup_fails=True)
    clock = Clock()
    env = environment(tmp_path, TAKTUS_BACKUP_EVERY_HOURS="6", TAKTUS_DRILL_EVERY_DAYS="0")
    backup.schedule(env, clock=clock, sleep=clock.sleep, rounds=4)
    assert calls == ["backup"] * 4, "no drill when its period is 0"
    assert set(clock.slept) == {6 * 3600.0}
    for wrong in ("x", "-1"):
        with pytest.raises(backup.BackupError):
            backup.schedule(environment(tmp_path, TAKTUS_BACKUP_EVERY_HOURS=wrong), rounds=1)
    with pytest.raises(backup.BackupError):
        backup.schedule(environment(tmp_path, TAKTUS_BACKUP_EVERY_HOURS="0"), rounds=1)


ROOT = Path(__file__).resolve().parents[2]


def test_one_machine_schedules_after_the_instance_from_built_or_published_images() -> None:
    import yaml

    compose = yaml.safe_load((ROOT / "deploy" / "docker" / "compose.yml").read_text("utf-8"))
    service = compose["services"]["backup"]
    assert service["command"] == ["schedule"]
    assert service["depends_on"]["taktus"]["condition"] == "service_healthy"
    assert "taktus-state:/var/lib/taktus:ro" in service["volumes"]
    assert service["environment"]["TAKTUS_BACKUP_EVERY_HOURS"] == "${TAKTUS_BACKUP_EVERY_HOURS:-24}"
    assert service["image"] == "${TAKTUS_BACKUP_IMAGE:-taktus-backup:local}" and service["build"]
    assert compose["services"]["taktus"]["image"] == "${TAKTUS_IMAGE:-taktus:local}"
    makefile = (ROOT / "Makefile").read_text("utf-8")
    assert "IMAGES_FROM = $(if $(TAKTUS_IMAGE),--pull always --no-build,--build)" in makefile
