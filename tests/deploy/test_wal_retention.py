"""Which archived segments of the write-ahead log the retention deletes, and the settings of
point-in-time recovery and the drill (ADR-0174 §1 to §3). Pure functions; no database."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from deploy.backup_program import backup

CLUSTER = "7702839390357131285"
OTHER = "7702839390357999999"
NOW = datetime(2026, 10, 31, 12, tzinfo=UTC)


def base(at: datetime, first: str, cluster: str = CLUSTER) -> str:
    return f"{backup.name_at(at)}.base-{cluster}-{first}.tar.gz"


def segment(n: int, timeline: int = 1) -> str:
    return f"{timeline:08X}{0:08X}{n:08X}"


def test_a_base_backup_s_name_is_one_of_the_program_s_own() -> None:
    name = base(NOW, segment(3))
    assert backup.time_of(name) == NOW
    assert backup.time_of(name + ".age") == NOW
    assert backup.time_of(f"{backup.name_at(NOW)}.base-x-{segment(3)}.tar.gz") is None


def test_segments_before_the_oldest_kept_base_go_and_the_ones_it_needs_stay() -> None:
    kept = [base(NOW - timedelta(days=2), segment(5)), base(NOW, segment(9)), "notes.txt"]
    wal = [f"{CLUSTER}/{segment(n)}" for n in range(1, 12)]
    wal += [f"{CLUSTER}/00000002.history", f"{CLUSTER}/{segment(4)}.00000028.backup"]
    wal += [f"{CLUSTER}/{segment(3)}.age", f"{CLUSTER}/foreign.txt"]

    doomed = backup.wal_expired(kept, wal)

    assert doomed == sorted(
        [f"{CLUSTER}/{segment(n)}" for n in range(1, 5)]
        + [f"{CLUSTER}/{segment(4)}.00000028.backup", f"{CLUSTER}/{segment(3)}.age"]
    )


def test_a_later_timeline_keeps_what_its_place_in_the_log_needs() -> None:
    kept = [base(NOW, segment(9, timeline=2))]
    wal = [f"{CLUSTER}/{segment(8, timeline=1)}", f"{CLUSTER}/{segment(9, timeline=1)}"]
    wal += [f"{CLUSTER}/{segment(10, timeline=2)}"]
    assert backup.wal_expired(kept, wal) == [f"{CLUSTER}/{segment(8, timeline=1)}"]


def test_a_cluster_no_kept_base_names_goes_and_nothing_goes_without_a_base() -> None:
    wal = [f"{OTHER}/{segment(1)}", f"{CLUSTER}/{segment(7)}", f"{OTHER}/00000001.history"]
    assert backup.wal_expired([base(NOW, segment(7))], wal) == [f"{OTHER}/{segment(1)}"]
    assert backup.wal_expired([f"{backup.name_at(NOW)}.dump"], wal) == []


def test_the_drills_are_kept_by_the_retention_and_the_newest_always() -> None:
    old = f"{backup.name_at(NOW - timedelta(days=40))}.drill.json"
    older = f"{backup.name_at(NOW - timedelta(days=50))}.drill.json.age"
    doomed = backup.expired([old, older, "a.txt"], now=NOW, retention_days=30, pattern=backup.DRILL)
    assert doomed == [older]


@pytest.mark.parametrize("file", ["../etc/passwd", "000000010000000000000003; rm", "x"])
def test_only_a_file_of_the_log_reaches_a_path(tmp_path: Path, file: str) -> None:
    s = backup.settings({"TAKTUS_BACKUP_STORE_DIRECTORY": str(tmp_path)}, database=False)
    with pytest.raises(backup.BackupError, match="not a file of the write-ahead log"):
        backup.archive_wal(s, tmp_path / "x", file, data_dir=tmp_path)
    with pytest.raises(backup.BackupError, match="not a file of the write-ahead log"):
        backup.fetch_wal(s, CLUSTER, file, tmp_path / "y")


def test_the_settings_of_point_in_time_and_of_the_drill(tmp_path: Path) -> None:
    env = {"TAKTUS_BACKUP_STORE_DIRECTORY": str(tmp_path)}
    s = backup.settings(env, database=False)
    assert (s.point_in_time, s.identity, s.restore_seconds, s.database_url) == (
        False, None, None, ""
    )  # fmt: skip
    key = tmp_path / "key.txt"
    key.write_text("AGE-SECRET-KEY-for-the-test\n", encoding="utf-8")
    s = backup.settings(
        env | {"TAKTUS_BACKUP_POINT_IN_TIME": "true",
               "TAKTUS_CREDENTIAL_BACKUP_IDENTITY_FILE": str(key),
               "TAKTUS_DRILL_RESTORE_SECONDS": "3600"},
        database=False,
    )  # fmt: skip
    assert (s.point_in_time, s.identity, s.restore_seconds) == (True, key, 3600)
    for change, message in [
        ({"TAKTUS_BACKUP_POINT_IN_TIME": "yes"}, "true or false"),
        ({"TAKTUS_CREDENTIAL_BACKUP_IDENTITY_FILE": str(tmp_path / "none")}, "cannot be read"),
        ({"TAKTUS_DRILL_RESTORE_SECONDS": "an hour"}, "whole number"),
    ]:
        with pytest.raises(backup.BackupError, match=message):
            backup.settings(env | change, database=False)


def test_a_moment_names_its_offset_or_is_latest() -> None:
    assert backup.moment("latest") == "latest"
    assert backup.moment("2026-10-31T12:00:00Z") == NOW
    with pytest.raises(backup.BackupError, match="no offset"):
        backup.moment("2026-10-31T12:00:00")
    with pytest.raises(backup.BackupError, match="neither"):
        backup.moment("yesterday")
