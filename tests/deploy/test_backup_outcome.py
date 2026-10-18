"""Every run of the backup records its outcome, and nothing but its own values reach the
statement (ADR-0106). The recording never changes what the run did."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from deploy.backup_program import backup
from taktus.ports.backups import REASONS

AT = datetime(2026, 10, 18, 3, 17, tzinfo=UTC)


def test_the_steps_it_names_are_the_ones_the_instance_reads() -> None:
    assert frozenset(backup.STEPS) == REASONS
    assert set(backup.TOOL_STEPS.values()) <= REASONS


def test_the_statement_records_one_row_per_tenant_with_the_run_s_own_values() -> None:
    name = backup.name_at(AT)
    ok = backup.outcome_sql(name, AT, None)
    assert "FROM tenant" in ok and "ON CONFLICT DO NOTHING" in ok
    assert f"'{name}'" in ok and "'2026-10-18T03:17:00Z'" in ok and "'ok', NULL" in ok
    failed = backup.outcome_sql(name, AT, "store")
    assert "'failed', 'store'" in failed


@pytest.mark.parametrize(
    ("name", "step"),
    [("taktus-x'; DROP TABLE tenant; --", None), ("taktus-20261018T031700Z", "store'; --")],
)
def test_nothing_from_outside_reaches_the_statement(name: str, step: str | None) -> None:
    with pytest.raises(backup.BackupError):
        backup.outcome_sql(name, AT, step)


def secrets(tmp_path: Path) -> dict[str, str]:
    url = tmp_path / "url"
    url.write_text("postgresql://backup:pw@db:5432/taktus\n", encoding="utf-8")
    return {"TAKTUS_DATABASE_URL_FILE": str(url), "TAKTUS_BACKUP_STORE_DIRECTORY": str(tmp_path)}


def test_a_failed_run_records_the_step_it_failed_at_and_still_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorded: list[dict[str, Any]] = []

    def record(url: str, env: object, **kwargs: Any) -> bool:
        recorded.append({"url": url, **kwargs})
        return True

    def refused(*args: object, **kwargs: object) -> str:
        raise backup.BackupError("rclone failed (1): denied", step="store")

    monkeypatch.setattr(backup, "record_outcome", record)
    monkeypatch.setattr(backup, "backup", refused)
    assert backup.main(["backup"], secrets(tmp_path)) == 1
    (one,) = recorded
    assert one["step"] == "store" and "pw" not in one["url"]
    assert backup.NAME.match(f"{one['name']}.json") is not None


def test_a_wrong_configuration_is_recorded_where_the_database_can_be_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorded: list[str | None] = []
    monkeypatch.setattr(
        backup, "record_outcome", lambda *a, **k: recorded.append(k["step"]) or True
    )
    env = secrets(tmp_path) | {"TAKTUS_BACKUP_RETENTION_DAYS": "x"}
    assert backup.main(["backup"], env) == 1
    assert recorded == ["configuration"]
    assert backup.main(["backup"], {"TAKTUS_BACKUP_STORE_DIRECTORY": str(tmp_path)}) == 1
    assert recorded == ["configuration"], "without the database's URL nothing can be recorded"


def test_a_recording_that_fails_changes_nothing_of_the_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def no_database(*args: object, **kwargs: object) -> str:
        raise backup.BackupError("psql failed (2): could not connect", step="database")

    monkeypatch.setattr(backup, "run", no_database)
    assert backup.record_outcome("postgresql://db/taktus", {}, name="taktus-20261018T031700Z",
                                 at=AT, step=None) is False  # fmt: skip
    assert "was not recorded" in capsys.readouterr().err
    monkeypatch.setattr(backup, "backup", lambda s, now: backup.name_at(now))
    monkeypatch.setattr(backup, "keep_retention", lambda s, now: [])
    assert backup.main(["backup"], secrets(tmp_path)) == 0, "the backup was written"


def test_listing_records_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    recorded: list[object] = []
    monkeypatch.setattr(backup, "record_outcome", lambda *a, **k: recorded.append(k) or True)
    monkeypatch.setattr(backup, "listing", lambda s: [])
    assert backup.main(["list"], secrets(tmp_path)) == 0
    assert recorded == []
