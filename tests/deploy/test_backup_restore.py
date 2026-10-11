"""The backup image against a real database, and the restore by hand (ADR-0013 C, ADR-0087).

A database of its own is migrated and given two tenants with ledger chains. The backup image
writes a backup into a directory standing in for the store, as the chart's CronJob would, and
keeps the retention there. The restore then runs the commands of `deploy/k8s/README.md` §11 in
the same image, against a fresh database, and every tenant's chain must verify and end at the
head it had before the backup. With a recipient configured, nothing written is readable without
the key, and with the key the restore is the same.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fakes import FakeClock
from sqlalchemy import text

from taktus.adapters.driven.postgres import PostgresLedgerStore, PostgresPersistence
from taktus.components.ledger.application.service import ChainedLedger
from taktus.ports.ledger import Fact
from taktus.shared.v1 import LedgerRefs

TENANTS = ("t_backup_one", "t_backup_two")
OLD = "taktus-20200101T000000Z"


@dataclass
class Database:
    container_id: str
    host_url: str
    inside_url: str
    password: str


def started(*, migrated: bool) -> Iterator[Database]:
    from alembic import command
    from testcontainers.community.postgres import PostgresContainer

    from taktus.adapters.driven.postgres.migrate import configuration

    with PostgresContainer("postgres:16-alpine", driver=None) as container:
        url = container.get_connection_url()
        if migrated:
            command.upgrade(configuration(url), "head")
        inside = (
            f"postgresql://{container.username}:{container.password}@localhost:5432/"
            f"{container.dbname}"
        )
        yield Database(container.get_wrapped_container().id, url, inside, container.password)


@pytest.fixture
def source(engine_socket: str) -> Iterator[Database]:
    yield from started(migrated=True)


@pytest.fixture
def target(engine_socket: str) -> Iterator[Database]:
    """A fresh, empty database, as a new install's or a new server's."""
    yield from started(migrated=False)


@pytest.fixture
async def persistence(source: Database) -> AsyncIterator[PostgresPersistence]:
    postgres = PostgresPersistence(source.host_url, pool_size=2)
    try:
        yield postgres
    finally:
        await postgres.close()


async def record(postgres: PostgresPersistence, tenant: str, count: int) -> None:
    async with postgres.engine.begin() as connection:
        await connection.execute(
            text("SELECT set_config('taktus.tenant', :t, true)"), {"t": tenant}
        )
        await connection.execute(
            text(
                "INSERT INTO tenant (id, name, created_at) VALUES (:t, :t, now()) "
                "ON CONFLICT DO NOTHING"
            ),
            {"t": tenant},
        )
    ledger = ChainedLedger(
        PostgresLedgerStore(postgres), FakeClock(datetime(2026, 10, 11, tzinfo=UTC))
    )
    async with postgres.transaction(tenant):
        for n in range(count):
            await ledger.record(
                tenant, Fact(kind="run.created", refs=LedgerRefs(run_id=f"run_{tenant}_{n}"))
            )


async def heads(url: str) -> dict[str, dict[str, object]]:
    """Every tenant's chain, verified, and its head: the digest a restore is checked against."""
    postgres = PostgresPersistence(url, pool_size=1)
    try:
        ledger = ChainedLedger(PostgresLedgerStore(postgres), FakeClock())
        found: dict[str, dict[str, object]] = {}
        for tenant in TENANTS:
            async with postgres.transaction(tenant):
                verification = await ledger.verify(tenant)
                entries = await ledger.entries(tenant)
            assert verification.intact, verification.findings
            found[tenant] = {"seq": entries[-1].seq, "hash": entries[-1].hash}
        return found
    finally:
        await postgres.close()


def docker(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    done = subprocess.run(["docker", *args], capture_output=True, text=True, check=False)  # noqa: S603, S607
    if check and done.returncode != 0:
        raise AssertionError(f"docker {args[:3]}… failed: {done.stdout}\n{done.stderr}")
    return done


def as_me() -> list[str]:
    return ["--user", f"{os.getuid()}:{os.getgid()}"]


def run_backup(
    image: str, db: Database, store: Path, secrets: Path, **env: str
) -> subprocess.CompletedProcess[str]:
    """The image as the chart's CronJob runs it, the store a mounted directory."""
    variables = {
        "TAKTUS_DATABASE_URL_FILE": "/run/secrets/url",
        "TAKTUS_BACKUP_STORE_DIRECTORY": "/backups",
        **env,
    }
    flags = [f"--env={key}={value}" for key, value in variables.items()]
    return docker(
        "run", "--rm", *as_me(), f"--network=container:{db.container_id}",
        f"--volume={store}:/backups", f"--volume={secrets}:/run/secrets:ro",
        *flags, image, check=False,
    )  # fmt: skip


def restore(image: str, db: Database, store: Path, work: Path, name: str, key: bool) -> None:
    """The commands of deploy/k8s/README.md §11, steps 2 to 5, with a directory as the store."""
    dump = f"{name}.dump"
    steps = [
        f"rclone --config /dev/null copyto :local:/backups/{dump}{'.age' if key else ''} "
        f"/work/{dump}{'.age' if key else ''}",
        *(
            [f"age --decrypt --identity /work/key.txt --output /work/{dump} /work/{dump}.age"]
            if key
            else []
        ),
        'psql --no-psqlrc -v ON_ERROR_STOP=1 --dbname "$URL" '
        "-c \"DO \\$\\$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'taktus_app') "
        'THEN CREATE ROLE taktus_app NOLOGIN; END IF; END \\$\\$" '
        '-c "GRANT taktus_app TO CURRENT_USER"',
        f'pg_restore --no-owner --exit-on-error --single-transaction --dbname "$URL" /work/{dump}',
    ]
    url, password = db.inside_url.replace(f":{db.password}@", "@"), db.password
    docker(
        "run", "--rm", *as_me(), f"--network=container:{db.container_id}",
        f"--volume={store}:/backups:ro", f"--volume={work}:/work",
        f"--env=URL={url}", f"--env=PGPASSWORD={password}",
        "--entrypoint=sh", image, "-euc", " && ".join(steps),
    )  # fmt: skip


def directories(tmp_path: Path, db: Database) -> tuple[Path, Path, Path]:
    store, secrets, work = (tmp_path / "store", tmp_path / "secrets", tmp_path / "work")
    for directory in (store, secrets, work):
        directory.mkdir()
    (secrets / "url").write_text(db.inside_url + "\n", encoding="utf-8")
    (secrets / "url").chmod(0o600)
    return store, secrets, work


def written(store: Path) -> list[str]:
    return sorted(
        p.name for p in store.iterdir() if p.name.startswith("taktus-2") and OLD not in p.name
    )


async def test_a_backup_restores_onto_a_fresh_database_with_every_chain_intact(
    backup_image: str,
    source: Database,
    target: Database,
    persistence: PostgresPersistence,
    tmp_path: Path,
) -> None:
    for tenant, count in zip(TENANTS, (5, 3), strict=True):
        await record(persistence, tenant, count)
    before = await heads(source.host_url)
    store, secrets, work = directories(tmp_path, source)
    for leftover in (f"{OLD}.dump", f"{OLD}.json", "notes.txt"):
        (store / leftover).write_text("an earlier object\n", encoding="utf-8")

    done = run_backup(backup_image, source, store, secrets)

    assert done.returncode == 0, done.stderr
    assert source.password not in done.stdout + done.stderr
    # The retention: the backup of 2020 is gone, the foreign object stays.
    assert not (store / f"{OLD}.dump").exists() and not (store / f"{OLD}.json").exists()
    assert (store / "notes.txt").exists()
    dump, manifest_file = written(store)
    name = dump.removesuffix(".dump")
    manifest = json.loads((store / manifest_file).read_text(encoding="utf-8"))
    assert manifest["object"] == dump and manifest["encrypted"] is False
    assert manifest["ledger_heads"] == before
    assert manifest["schema_revision"]

    # Work after the backup is not in it: the restore ends where the backup was taken.
    await record(persistence, TENANTS[0], 2)

    restore(backup_image, target, store, work, name, key=False)

    assert await heads(target.host_url) == before


async def test_an_encrypted_backup_cannot_be_read_without_its_key(
    backup_image: str,
    source: Database,
    target: Database,
    persistence: PostgresPersistence,
    tmp_path: Path,
) -> None:
    for tenant in TENANTS:
        await record(persistence, tenant, 2)
    before = await heads(source.host_url)
    store, secrets, work = directories(tmp_path, source)
    plain = run_backup(backup_image, source, store, secrets)
    assert plain.returncode == 0, plain.stderr
    keygen = docker("run", "--rm", *as_me(), f"--volume={work}:/work", "--entrypoint=age-keygen",
                    backup_image, "-o", "/work/key.txt")  # fmt: skip
    recipient = keygen.stderr.split("Public key:")[1].strip()
    await asyncio.sleep(1.1)  # a backup's name is its second; two in one second would share it

    # Retention 0: the plain backup taken a moment ago goes, the encrypted one is the newest.
    done = run_backup(
        backup_image, source, store, secrets,
        TAKTUS_BACKUP_RECIPIENT=recipient, TAKTUS_BACKUP_RETENTION_DAYS="0",
    )  # fmt: skip

    assert done.returncode == 0, done.stderr
    dump, manifest_file = written(store)
    assert dump.endswith(".dump.age") and manifest_file.endswith(".json.age")
    for path in (store / dump, store / manifest_file):
        content = path.read_bytes()
        assert content.startswith(b"age-encryption.org/v1\n")
        assert b"ledger_heads" not in content and b"PGDMP" not in content
    unreadable = docker(
        "run", "--rm", *as_me(), f"--volume={store}:/backups:ro", "--entrypoint=pg_restore",
        backup_image, "--list", f"/backups/{dump}", check=False,
    )  # fmt: skip
    assert unreadable.returncode != 0
    without_key = docker(
        "run", "--rm", *as_me(), f"--volume={store}:/backups:ro", "--entrypoint=age",
        backup_image, "--decrypt", f"/backups/{manifest_file}", check=False,
    )  # fmt: skip
    assert without_key.returncode != 0

    restore(backup_image, target, store, work, dump.removesuffix(".dump.age"), key=True)

    assert await heads(target.host_url) == before


async def test_against_an_object_store_with_its_credential_read_from_files(
    backup_image: str,
    source: Database,
    persistence: PostgresPersistence,
    tmp_path: Path,
) -> None:
    """The store mode the chart runs: an S3 interface, here rclone's own server, its credential
    two mounted files, a prefix inside the bucket, the retention kept through the interface."""
    await record(persistence, TENANTS[0], 1)
    store, secrets, _ = directories(tmp_path, source)
    identifier, key = "backup-test-identifier", os.urandom(12).hex()
    (secrets / "id").write_text(identifier, encoding="utf-8")
    (secrets / "key").write_text(key, encoding="utf-8")
    place = store / "bucket" / "instance"
    place.mkdir(parents=True)
    (place / f"{OLD}.dump").write_text("an earlier dump\n", encoding="utf-8")
    server = docker(
        "run", "--detach", "--rm", *as_me(), f"--network=container:{source.container_id}",
        f"--volume={store}:/data", "--entrypoint=rclone", backup_image,
        "serve", "s3", "--config", "/dev/null", "--addr", "127.0.0.1:8333",
        "--auth-key", f"{identifier},{key}", "/data",
    ).stdout.strip()  # fmt: skip
    try:
        done = run_backup(
            backup_image, source, store, secrets,
            TAKTUS_BACKUP_STORE_DIRECTORY="",
            TAKTUS_BACKUP_STORE_ENDPOINT="http://127.0.0.1:8333",
            TAKTUS_BACKUP_STORE_BUCKET="bucket",
            TAKTUS_BACKUP_STORE_PREFIX="instance",
            TAKTUS_CREDENTIAL_BACKUP_STORE_ACCESS_KEY_ID_FILE="/run/secrets/id",
            TAKTUS_CREDENTIAL_BACKUP_STORE_FILE="/run/secrets/key",
        )  # fmt: skip
        wrong = run_backup(
            backup_image, source, store, secrets,
            TAKTUS_BACKUP_STORE_DIRECTORY="",
            TAKTUS_BACKUP_STORE_ENDPOINT="http://127.0.0.1:8333",
            TAKTUS_BACKUP_STORE_BUCKET="bucket",
            TAKTUS_CREDENTIAL_BACKUP_STORE_ACCESS_KEY_ID_FILE="/run/secrets/id",
            TAKTUS_CREDENTIAL_BACKUP_STORE_FILE="/run/secrets/url",
        )  # fmt: skip
    finally:
        docker("stop", server, check=False)

    assert done.returncode == 0, done.stderr
    assert key not in done.stdout + done.stderr
    names = sorted(p.name for p in place.iterdir())
    assert f"{OLD}.dump" not in names
    assert [n.rsplit(".", 1)[1] for n in names] == ["dump", "json"], names
    assert wrong.returncode == 1, "a credential the store refuses fails the run"
    assert source.password not in wrong.stdout + wrong.stderr
