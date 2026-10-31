"""Point-in-time recovery and the restore drill, against a real database (ADR-0174, UC-10.5, S-03).

A database runs from the backup image with its write-ahead log archived through the program
into a directory standing in for the store, as the chart runs it with
`backup.pointInTime.enabled`. Two tenants write a first batch of entries, a backup takes a dump
and a base backup, the tenants write a second batch — the heads after it are noted with the
moment — and a third. The drill then restores to the noted moment in a container with no network
at all, and every tenant's chain must verify and end exactly at the heads noted. The same restore
by hand, with the commands of `deploy/k8s/README.md` §11, ends at the same heads as Taktus's own
verification reads them. A moment the archive does not reach, and a ledger altered before the
backup, fail the drill.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import time
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fakes import FakeClock
from sqlalchemy import text

from taktus.adapters.driven.postgres import PostgresLedgerStore, PostgresPersistence
from taktus.components.ledger.application.service import ChainedLedger
from taktus.ports.ledger import Fact
from taktus.shared.v1 import LedgerRefs

TENANTS = ("t_pitr_one", "t_pitr_two")
PASSWORD = "drill-test-password"  # a test container's own, never a credential  # noqa: S105
ARCHIVE = "python3 /usr/local/bin/taktus-backup archive-wal %p %f"


@dataclass
class Source:
    container: str
    host_url: str
    inside_url: str
    store: Path


def docker(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    done = subprocess.run(["docker", *args], capture_output=True, text=True, check=False)  # noqa: S603, S607
    if check and done.returncode != 0:
        raise AssertionError(f"docker {args[:3]}… failed: {done.stdout}\n{done.stderr}")
    return done


def ready(url: str, seconds: float = 60) -> None:
    import psycopg

    deadline = time.monotonic() + seconds
    while True:
        try:
            with psycopg.connect(url, connect_timeout=2) as connection:
                connection.execute("SELECT 1")
                return
        except psycopg.OperationalError:
            if time.monotonic() > deadline:
                raise
            time.sleep(0.5)


def published(container: str) -> int:
    return int(
        docker("port", container, "5432/tcp").stdout.strip().splitlines()[0].rsplit(":", 1)[1]
    )


@pytest.fixture
def source(backup_image: str, tmp_path: Path) -> Iterator[Source]:
    """The instance's database with its log archived, as `backup.pointInTime.enabled` runs it."""
    from alembic import command

    from taktus.adapters.driven.postgres.migrate import configuration

    store = tmp_path / "store"
    store.mkdir()
    store.chmod(0o777)  # the database's own user writes the archive into it
    name = f"taktus-pitr-{os.urandom(4).hex()}"
    docker(
        "run", "-d", "--name", name, "-p", "127.0.0.1::5432",
        "--env", f"POSTGRES_PASSWORD={PASSWORD}", "--env", "POSTGRES_DB=taktus",
        "--env", "TAKTUS_BACKUP_STORE_DIRECTORY=/backups", "--env", "TAKTUS_BACKUP_WORK_DIR=/tmp",
        "--volume", f"{store}:/backups", "--entrypoint", "docker-entrypoint.sh", backup_image,
        "postgres", "-c", "archive_mode=on", "-c", f"archive_command={ARCHIVE}",
        "-c", "archive_timeout=60",
    )  # fmt: skip
    try:
        url = f"postgresql://postgres:{PASSWORD}@127.0.0.1:{published(name)}/taktus"
        ready(url)
        command.upgrade(configuration(url), "head")
        yield Source(name, url, f"postgresql://postgres:{PASSWORD}@localhost:5432/taktus", store)
    finally:
        docker("rm", "-f", "-v", name, check=False)  # the test's own container and its volume


@pytest.fixture
async def persistence(source: Source) -> AsyncIterator[PostgresPersistence]:
    postgres = PostgresPersistence(source.host_url, pool_size=2)
    try:
        yield postgres
    finally:
        await postgres.close()


async def record(postgres: PostgresPersistence, batch: str, count: int) -> None:
    for tenant in TENANTS:
        async with postgres.engine.begin() as connection:
            await connection.execute(
                text("INSERT INTO tenant (id, name, created_at) VALUES (:t, :t, now()) "
                     "ON CONFLICT DO NOTHING"),
                {"t": tenant},
            )  # fmt: skip
        ledger = ChainedLedger(PostgresLedgerStore(postgres), FakeClock(datetime.now(UTC)))
        async with postgres.transaction(tenant):
            for n in range(count):
                fact = Fact(kind="run.created", refs=LedgerRefs(run_id=f"run_{batch}_{n}"))
                await ledger.record(tenant, fact)


async def heads(url: str) -> dict[str, dict[str, object]]:
    """Every tenant's chain verified by Taktus itself, and its newest entry: the digest."""
    postgres = PostgresPersistence(url, pool_size=1)
    try:
        ledger = ChainedLedger(PostgresLedgerStore(postgres), FakeClock())
        found: dict[str, dict[str, object]] = {}
        for tenant in TENANTS:
            async with postgres.transaction(tenant):
                verification = await ledger.verify(tenant, full=True)
                entries = await ledger.entries(tenant)
            assert verification.intact, verification.findings
            found[tenant] = {"seq": entries[-1].seq, "hash": entries[-1].hash}
        return found
    finally:
        await postgres.close()


async def scalar(postgres: PostgresPersistence, sql: str) -> str:
    async with postgres.engine.connect() as connection:
        return str((await connection.execute(text(sql))).scalar_one())


async def archived(postgres: PostgresPersistence) -> None:
    """Close the current segment and wait until the database has archived it."""
    segment = await scalar(postgres, "SELECT pg_walfile_name(pg_current_wal_lsn())")
    await scalar(postgres, "SELECT pg_switch_wal()::text")
    deadline = time.monotonic() + 60
    while (
        await scalar(postgres, "SELECT coalesce(last_archived_wal, '') FROM pg_stat_archiver")
        < segment
    ):
        assert time.monotonic() < deadline, f"segment {segment} was not archived"
        await asyncio.sleep(0.5)


def backup_now(image: str, source: Source, tmp_path: Path) -> subprocess.CompletedProcess[str]:
    secrets = tmp_path / "secrets"
    secrets.mkdir(exist_ok=True)
    (secrets / "url").write_text(source.inside_url + "\n", encoding="utf-8")
    (secrets / "url").chmod(0o644)
    return docker(
        "run", "--rm", f"--network=container:{source.container}",
        f"--volume={source.store}:/backups", f"--volume={secrets}:/run/secrets:ro",
        "--env=TAKTUS_DATABASE_URL_FILE=/run/secrets/url",
        "--env=TAKTUS_BACKUP_STORE_DIRECTORY=/backups", "--env=TAKTUS_BACKUP_POINT_IN_TIME=true",
        image, check=False,
    )  # fmt: skip


def run_drill(
    image: str, source: Source, work: Path, *args: str
) -> tuple[subprocess.CompletedProcess[str], dict[str, object]]:
    """The drill with no network at all: it cannot reach the instance's database."""
    before = (
        set((source.store / "drills").glob("*")) if (source.store / "drills").exists() else set()
    )
    done = docker(
        "run", "--rm", "--network=none", f"--volume={source.store}:/backups",
        f"--volume={work}:/work", "--env=TAKTUS_BACKUP_STORE_DIRECTORY=/backups",
        "--env=TAKTUS_BACKUP_WORK_DIR=/tmp", image, "drill", *args, check=False,
    )  # fmt: skip
    [report] = set((source.store / "drills").glob("*.drill.json")) - before
    return done, json.loads(report.read_text(encoding="utf-8"))


def work_dir(tmp_path: Path) -> Path:
    work = tmp_path / "work"
    work.mkdir(exist_ok=True)
    work.chmod(0o777)
    return work


def segments(source: Source) -> list[str]:
    return sorted(p.name for p in source.store.glob("wal/*/*"))


async def test_the_drill_restores_to_a_chosen_moment_and_every_chain_ends_at_the_heads_noted(
    backup_image: str, source: Source, persistence: PostgresPersistence, tmp_path: Path
) -> None:
    await record(persistence, "first", 4)
    done = backup_now(backup_image, source, tmp_path)
    assert done.returncode == 0, done.stderr
    [manifest_file] = source.store.glob("taktus-*.json")
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    base = manifest["base"]
    assert base["object"].startswith(manifest["name"] + ".base-" + base["system_identifier"])
    assert (source.store / base["object"]).exists()

    await record(persistence, "second", 3)
    noted = await heads(source.host_url)
    moment = await scalar(persistence, "SELECT to_char(now() AT TIME ZONE 'UTC', "
                                       "'YYYY-MM-DD\"T\"HH24:MI:SS.US\"Z\"')")  # fmt: skip
    await asyncio.sleep(1.1)
    await record(persistence, "third", 2)
    later = await heads(source.host_url)
    await archived(persistence)
    assert segments(source), "the log was archived into the store"
    work = work_dir(tmp_path)
    (work / "heads.json").write_text(json.dumps(noted), encoding="utf-8")
    archive = segments(source)

    done, report = run_drill(
        backup_image, source, work, "--to", moment, "--heads", "/work/heads.json"
    )

    assert done.returncode == 0, done.stderr
    assert report["outcome"] == "ok" and report["mode"] == "point-in-time"
    assert report["backup"] == manifest["name"]
    tenants = report["tenants"]
    assert isinstance(tenants, dict)
    for tenant in TENANTS:
        assert tenants[tenant]["intact"] is True
        assert tenants[tenant]["head"] == noted[tenant] != later[tenant]
        assert tenants[tenant]["entries"] == 7, "the third batch is not in it"
    assert isinstance(report["restore_seconds"], float)
    assert segments(source) == archive, "the drill archived nothing"

    # To the latest moment the archive reaches: the third batch is there.
    done, report = run_drill(backup_image, source, work, "--to", "latest")
    assert done.returncode == 0, done.stderr
    assert {t: r["head"] for t, r in report["tenants"].items() if t in TENANTS} == later  # type: ignore[union-attr]

    # Without a moment, the newest backup's dump: the heads of the manifest, nothing after.
    done, report = run_drill(backup_image, source, work)
    assert done.returncode == 0, done.stderr
    assert report["mode"] == "dump"
    assert {t: r["head"] for t, r in report["tenants"].items() if t in TENANTS} == manifest[
        "ledger_heads"
    ]  # type: ignore[union-attr]


async def test_the_restore_to_a_moment_by_hand_ends_where_taktus_verifies_the_heads_noted(
    backup_image: str, source: Source, persistence: PostgresPersistence, tmp_path: Path
) -> None:
    """The steps of deploy/k8s/README.md §11, *To a chosen moment*, with rclone, tar and the
    database's own server, and nothing of Taktus; Taktus then reads the restored database."""
    await record(persistence, "first", 2)
    assert backup_now(backup_image, source, tmp_path).returncode == 0
    await record(persistence, "second", 2)
    noted = await heads(source.host_url)
    moment = await scalar(persistence, "SELECT now()::text")
    await asyncio.sleep(1.1)
    await record(persistence, "third", 2)
    await archived(persistence)
    manifest = json.loads(next(source.store.glob("taktus-*.json")).read_text(encoding="utf-8"))
    base, cluster = manifest["base"]["object"], manifest["base"]["system_identifier"]
    restore = (
        "set -eu; D=/tmp/restored; mkdir -m 700 $D; "
        f"rclone --config /dev/null copyto :local:/backups/{base} /tmp/{base}; "
        f"tar -xzf /tmp/{base} -C $D; touch $D/recovery.signal; "
        f'printf "%s\\n" "restore_command = \'rclone --config /dev/null copyto '
        f":local:/backups/wal/{cluster}/%f %p'\" \"recovery_target_time = '{moment}'\" "
        "\"recovery_target_action = 'promote'\" >> $D/postgresql.auto.conf; "
        "exec postgres -D $D -c listen_addresses='*' -c archive_mode=off"
    )
    name = f"taktus-pitr-hand-{os.urandom(4).hex()}"
    docker(
        "run", "-d", "--name", name, "-p", "127.0.0.1::5432",
        f"--volume={source.store}:/backups:ro", "--entrypoint=sh", backup_image, "-c", restore,
    )  # fmt: skip
    try:
        url = f"postgresql://postgres:{PASSWORD}@127.0.0.1:{published(name)}/taktus"
        deadline = time.monotonic() + 60
        while True:
            try:
                ready(url, seconds=5)
                restored = PostgresPersistence(url, pool_size=1)
                try:
                    if await scalar(restored, "SELECT pg_is_in_recovery()::text") == "false":
                        break
                finally:
                    await restored.close()
            except Exception:
                if time.monotonic() > deadline:
                    raise AssertionError(docker("logs", name, check=False).stderr) from None
            await asyncio.sleep(0.5)
        assert await heads(url) == noted
    finally:
        docker("rm", "-f", "-v", name, check=False)


async def test_a_moment_beyond_the_archive_and_an_altered_ledger_fail_the_drill(
    backup_image: str, source: Source, persistence: PostgresPersistence, tmp_path: Path
) -> None:
    await record(persistence, "first", 3)
    assert backup_now(backup_image, source, tmp_path).returncode == 0
    work = work_dir(tmp_path)
    beyond = (datetime.now(UTC) + timedelta(days=1)).isoformat()

    done, report = run_drill(backup_image, source, work, "--to", beyond)

    assert done.returncode == 1
    assert report["outcome"] == "failed"
    assert "does not reach the moment" in json.dumps(report["failures"])

    # An entry altered in the database, past its append-only trigger, as only a superuser can.
    async with persistence.engine.begin() as connection:
        await connection.execute(text("SET LOCAL session_replication_role = replica"))
        await connection.execute(
            text("UPDATE ledger_entry SET outcome = 'tampered' WHERE tenant = :t AND seq = "
                 "(SELECT min(seq) FROM ledger_entry WHERE tenant = :t)"),
            {"t": TENANTS[1]},
        )  # fmt: skip
    await asyncio.sleep(1.1)  # a backup's name is its second
    assert backup_now(backup_image, source, tmp_path).returncode == 0

    done, report = run_drill(backup_image, source, work)

    assert done.returncode == 1
    tenants = report["tenants"]
    assert isinstance(tenants, dict)
    assert tenants[TENANTS[0]]["intact"] is True
    assert tenants[TENANTS[1]]["intact"] is False
    assert "hash does not match its content" in tenants[TENANTS[1]]["findings"][0]
