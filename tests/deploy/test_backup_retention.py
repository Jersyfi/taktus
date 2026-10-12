"""Taktus keeps the retention of its backups itself (DEC-0058, ADR-0087): a backup older than
the retention is deleted, no younger one is, the newest never is, and nothing it did not write
is touched. The configuration is checked before anything is done."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from deploy.backup_program import backup

NOW = datetime(2026, 10, 11, 3, 17, tzinfo=UTC)
SECRET = "made-up-for-this-test"  # noqa: S105


def pair(at: datetime, *, encrypted: bool = False) -> list[str]:
    suffix = ".age" if encrypted else ""
    name = backup.name_at(at)
    return [f"{name}.dump{suffix}", f"{name}.json{suffix}"]


def store(*ages: timedelta) -> list[str]:
    return [name for age in ages for name in pair(NOW - age)]


@pytest.mark.parametrize(
    ("retention", "kept"),
    [
        # 0 days: everything older than now goes, but the newest backup always stays.
        (0, {timedelta(hours=1)}),
        (1, {timedelta(hours=1), timedelta(hours=23)}),
        (
            30,
            {timedelta(hours=1), timedelta(hours=23), timedelta(days=2), timedelta(days=29)},
        ),
    ],
)
def test_backups_older_than_the_retention_go_and_no_younger_one(
    retention: int, kept: set[timedelta]
) -> None:
    ages = [
        timedelta(hours=1),
        timedelta(hours=23),
        timedelta(days=2),
        timedelta(days=29),
        timedelta(days=31),
        timedelta(days=400),
    ]
    objects = store(*ages)
    doomed = backup.expired(objects, now=NOW, retention_days=retention)
    assert doomed == sorted(store(*(a for a in ages if a not in kept)))
    assert set(objects) - set(doomed) == set(store(*kept))


def test_the_boundary_itself_is_kept() -> None:
    objects = store(timedelta(days=1), timedelta(days=1, seconds=1))
    assert backup.expired(objects, now=NOW, retention_days=1) == pair(
        NOW - timedelta(days=1, seconds=1)
    )


def test_the_newest_backup_is_never_deleted_however_old() -> None:
    objects = store(timedelta(days=90), timedelta(days=100))
    assert backup.expired(objects, now=NOW, retention_days=30) == pair(NOW - timedelta(days=100))


def test_encrypted_backups_are_kept_by_the_same_rule() -> None:
    objects = pair(NOW, encrypted=True) + pair(NOW - timedelta(days=40), encrypted=True)
    assert backup.expired(objects, now=NOW, retention_days=30) == pair(
        NOW - timedelta(days=40), encrypted=True
    )


def test_an_object_it_did_not_write_is_never_touched() -> None:
    foreign = [
        "notes.txt",
        "taktus-2020.dump",
        "taktus-20200101T000000Z.sql",
        "other-20200101T000000Z.dump",
    ]
    assert backup.expired([*foreign, *pair(NOW)], now=NOW, retention_days=0) == []


def test_a_negative_retention_is_refused() -> None:
    with pytest.raises(backup.BackupError, match="negative"):
        backup.expired(pair(NOW), now=NOW, retention_days=-1)


# --- configuration ----------------------------------------------------------------------------


def secret(tmp_path: Path, name: str, value: str) -> str:
    path = tmp_path / name
    path.write_text(value + "\n", encoding="utf-8")
    return str(path)


def base(tmp_path: Path) -> dict[str, str]:
    return {
        "TAKTUS_DATABASE_URL_FILE": secret(
            tmp_path, "url", "postgresql://taktus:pw@db:5432/taktus"
        ),
        "TAKTUS_BACKUP_STORE_ENDPOINT": "https://store.invalid",
        "TAKTUS_BACKUP_STORE_BUCKET": "bucket",
        "TAKTUS_CREDENTIAL_BACKUP_STORE_ACCESS_KEY_ID_FILE": secret(tmp_path, "id", "identifier"),
        "TAKTUS_CREDENTIAL_BACKUP_STORE_FILE": secret(tmp_path, "key", SECRET),
    }


def test_the_defaults_are_thirty_days_and_no_encryption(tmp_path: Path) -> None:
    s = backup.settings(base(tmp_path))
    assert s.retention_days == 30
    assert s.recipient == ""
    assert s.remote == ":s3:bucket"
    assert s.store_env["RCLONE_S3_SECRET_ACCESS_KEY"] == SECRET


def test_the_password_never_reaches_a_command_line(tmp_path: Path) -> None:
    s = backup.settings(base(tmp_path))
    assert "pw" not in s.database_url
    assert s.database_url == "postgresql://taktus@db:5432/taktus"
    assert s.database_env == {"PGPASSWORD": "pw"}


def test_a_driver_in_the_scheme_is_dropped_and_a_url_without_password_kept(tmp_path: Path) -> None:
    env = base(tmp_path) | {
        "TAKTUS_DATABASE_URL_FILE": secret(
            tmp_path, "u2", "postgresql+psycopg://t@db/x?sslmode=require"
        )
    }
    s = backup.settings(env)
    assert s.database_url == "postgresql://t@db/x?sslmode=require"
    assert s.database_env == {}


def test_a_directory_instead_of_a_store(tmp_path: Path) -> None:
    env = base(tmp_path)
    del env["TAKTUS_BACKUP_STORE_ENDPOINT"]
    env["TAKTUS_BACKUP_STORE_DIRECTORY"] = "/backups/"
    s = backup.settings(env)
    assert s.remote == ":local:/backups"
    assert s.store_env == {}


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"TAKTUS_BACKUP_RETENTION_DAYS": "thirty"}, "whole number"),
        ({"TAKTUS_BACKUP_RETENTION_DAYS": "-1"}, "whole number"),
        ({"TAKTUS_BACKUP_RECIPIENT": "ssh-ed25519 AAAA"}, "age public key"),
        ({"TAKTUS_BACKUP_STORE_DIRECTORY": "/backups"}, "exactly one"),
        ({"TAKTUS_BACKUP_STORE_BUCKET": ""}, "BUCKET"),
        ({"TAKTUS_CREDENTIAL_BACKUP_STORE_FILE": "/nonexistent/key"}, "cannot be read"),
        ({"TAKTUS_DATABASE_URL_FILE": ""}, "TAKTUS_DATABASE_URL_FILE is not set"),
    ],
)
def test_a_wrong_configuration_is_refused_before_anything_is_done(
    tmp_path: Path, change: dict[str, str], message: str
) -> None:
    with pytest.raises(backup.BackupError, match=message):
        backup.settings(base(tmp_path) | change)


def test_a_refusal_never_carries_the_secret(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    env = base(tmp_path) | {"TAKTUS_BACKUP_RETENTION_DAYS": "x"}
    assert backup.main(["backup"], env) == 1
    err = capsys.readouterr().err
    assert SECRET not in err and "pw" not in err


# --- waiting for the database -------------------------------------------------------------------


def test_the_backup_waits_while_the_database_refuses_and_goes_on_once_it_answers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    answers = iter([False, False, True])
    calls: list[list[str]] = []

    def run(command: list[str], **_: object) -> str:
        calls.append(command)
        if not next(answers):
            raise backup.BackupError("pg_isready failed (2): refused")
        return ""

    monkeypatch.setattr(backup, "run", run)
    slept: list[float] = []
    backup.wait_for_database(backup.settings(base(tmp_path)), sleep=slept.append)
    assert [c[0] for c in calls] == ["pg_isready"] * 3
    assert slept == [2.0, 2.0]


def test_a_database_that_never_answers_fails_the_run_after_the_wait(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def run(command: list[str], **_: object) -> str:
        raise backup.BackupError("pg_isready failed (2): refused")

    monkeypatch.setattr(backup, "run", run)
    with pytest.raises(backup.BackupError, match="refused"):
        backup.wait_for_database(backup.settings(base(tmp_path)), seconds=0, sleep=lambda _: None)
