"""The backup image against a real database, and the restore by hand (ADR-0013 C, ADR-0087).

A database of its own is migrated and given two tenants with ledger chains. The backup image
writes a backup into a directory standing in for the store, as the chart's CronJob would, and
keeps the retention there. The restore then runs the commands of `deploy/k8s/README.md` §11 in
the same image, against a fresh database, and every tenant's chain must verify and end at the
head it had before the backup. With a recipient configured, nothing written is readable without
the key, and with the key the restore is the same. With the object store given, a run's every
digest is readable after a restore into a fresh database and an empty state directory (#322).
Every run records its outcome for every tenant in the database it backed up, a failed one with
the step it failed at (ADR-0106).
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
from fakes import (
    FakeClock,
    FakeIdentifiers,
    FakeWorker,
)
from fakes.maturity import VERIFIED
from sqlalchemy import text

from taktus.adapters.driven.memory import MemoryObjectStore
from taktus.adapters.driven.postgres import (
    PostgresLedgerStore,
    PostgresPersistence,
    PostgresProvenanceStore,
    PostgresRepository,
)
from taktus.adapters.driven.telemetry import NoTelemetry
from taktus.adapters.driven.workers.pool import StaticWorkerPool
from taktus.components.ledger.application.service import ChainedLedger
from taktus.components.run.application.service import EngineOptions, RunEngine, StartRun
from taktus.components.run.domain.model import Run, RunState
from taktus.ports.ledger import Fact
from taktus.ports.worker import ComputeLimit, Limits
from taktus.shared.v1 import (
    Commissioned,
    ExactnessClass,
    Fallback,
    LedgerRefs,
    Method,
    Plan,
    PlanResult,
    PlanStatus,
    Step,
)

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


def restore(
    image: str,
    db: Database,
    store: Path,
    work: Path,
    name: str,
    key: bool,
    state: Path | None = None,
) -> None:
    """The commands of deploy/k8s/README.md §11, steps 2 to 6, with a directory as the store;
    with `state`, the object store's archive restored into it as well."""
    dump = f"{name}.dump"
    archive = f"{name}.objects.tar.gz"
    objects = (
        []
        if state is None
        else [
            f"rclone --config /dev/null copyto :local:/backups/{archive} /work/{archive}",
            "mkdir -p /state/objects",
            f"tar -xzf /work/{archive} -C /state/objects",
        ]
    )
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
        *objects,
    ]
    url, password = db.inside_url.replace(f":{db.password}@", "@"), db.password
    mounts = [] if state is None else [f"--volume={state}:/state"]
    docker(
        "run", "--rm", *as_me(), f"--network=container:{db.container_id}",
        f"--volume={store}:/backups:ro", f"--volume={work}:/work", *mounts,
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


RUN_TENANT = TENANTS[0]


async def run_a_process(postgres: PostgresPersistence, objects: Path) -> Run:
    """A run of a rule and a worker step, on the database and an object store in a directory, as
    an instance runs it."""
    async with postgres.engine.begin() as connection:
        await connection.execute(
            text("INSERT INTO tenant (id, name, created_at) VALUES (:t, :t, now()) "
                 "ON CONFLICT DO NOTHING"),
            {"t": RUN_TENANT},
        )  # fmt: skip
    clock = FakeClock(datetime(2026, 10, 18, tzinfo=UTC))
    engine = RunEngine(
        maturities=VERIFIED,
        runs=PostgresRepository(postgres, Run),
        work=postgres,
        objects=MemoryObjectStore(objects),
        ledger=ChainedLedger(PostgresLedgerStore(postgres), clock),
        provenance=PostgresProvenanceStore(postgres),
        workers=StaticWorkerPool([("worker.fake", FakeWorker())]),
        clock=clock,
        ids=FakeIdentifiers(),
        telemetry=NoTelemetry(),
        options=EngineOptions(uncalibrated_margin=0.0),
    )
    steps = (
        Step(id="a", method=Method.RULE, reason="r", rejected=(), exactness=ExactnessClass.EXACT),
        Step(
            id="b",
            method=Method.WORKER,
            reason="r",
            rejected=(),
            exactness=ExactnessClass.TOLERANT,
            fallback=Fallback(when="x", to=Method.HUMAN),
            requires=("shell.script",),
            depends_on=("a",),
        ),
    )
    plan = Plan(
        id="pln_backup",
        command_id="cmd_backup",
        goal="g",
        autonomy_level=3,
        steps=steps,
        results_in=PlanResult.RUN,
        status=PlanStatus.COMMISSIONED,
        commissioned=Commissioned(by="idn_t", at=clock.now()),
    )
    return await engine.start(
        StartRun(
            plan=plan,
            work={
                "a": {"rule": "constant", "value": 42},
                "b": {"task": {"goal": "g", "acceptance": ["a"]}},
            },
            budget=Limits(compute=ComputeLimit(seconds=10, resource_class="cpu.small")),
            process_version="p@1",
            actor="idn_t",
            tenant=RUN_TENANT,
        )
    )


async def digests_of(url: str, run_id: str) -> set[str]:
    """Every digest the database names for the run: its step runs' artifacts and checkpoints,
    and its ledger entries' content."""
    postgres = PostgresPersistence(url, pool_size=1)
    try:
        ledger = ChainedLedger(PostgresLedgerStore(postgres), FakeClock())
        async with postgres.transaction(RUN_TENANT):
            run = await PostgresRepository(postgres, Run).get(RUN_TENANT, run_id)
            entries = await ledger.entries(RUN_TENANT, run_id)
        assert run is not None
        found = {e.content_digest for e in entries if e.content_digest}
        for step_run in run.step_runs:
            found |= {a.digest for a in step_run.artifacts}
            if step_run.checkpoint is not None and step_run.checkpoint.result_digest:
                found.add(step_run.checkpoint.result_digest)
        return found
    finally:
        await postgres.close()


async def outcomes(postgres: PostgresPersistence) -> list[tuple[str, str, str, str | None]]:
    """Every recorded outcome, read by the database's own login, as an operator reads it."""
    async with postgres.engine.connect() as connection:
        rows = await connection.execute(
            text("SELECT tenant, name, outcome, reason FROM backup_outcome ORDER BY tenant, name")
        )
        return [(r.tenant, r.name, r.outcome, r.reason) for r in rows]


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
    # The run's outcome, for every tenant of the instance, the backup's own name and no reason.
    assert await outcomes(persistence) == [
        (tenant, name, "ok", None) for tenant in sorted(("default", *TENANTS))
    ]
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


async def test_a_restore_with_the_object_store_reads_every_digest_a_run_refers_to(
    backup_image: str,
    source: Database,
    target: Database,
    persistence: PostgresPersistence,
    tmp_path: Path,
) -> None:
    """Shown on 2026-10-12: after a restore of the database alone, none of the digests a finished
    run refers to was readable (#322). With the object store archived beside the dump, all are."""
    state = tmp_path / "state"
    (state / "objects").mkdir(parents=True)
    run = await run_a_process(persistence, state / "objects")
    assert run.state is RunState.FINISHED
    referred = await digests_of(source.host_url, run.id)
    assert referred, "the run refers to objects"
    store, secrets, work = directories(tmp_path, source)
    done = docker(
        "run", "--rm", *as_me(), f"--network=container:{source.container_id}",
        f"--volume={store}:/backups", f"--volume={secrets}:/run/secrets:ro",
        f"--volume={state / 'objects'}:/objects:ro",
        "--env=TAKTUS_DATABASE_URL_FILE=/run/secrets/url",
        "--env=TAKTUS_BACKUP_STORE_DIRECTORY=/backups",
        "--env=TAKTUS_BACKUP_OBJECTS_DIRECTORY=/objects",
        backup_image, check=False,
    )  # fmt: skip
    assert done.returncode == 0, done.stderr
    names = written(store)
    (archive,) = [n for n in names if n.endswith(".objects.tar.gz")]
    (manifest_file,) = [n for n in names if n.endswith(".json")]
    manifest = json.loads((store / manifest_file).read_text(encoding="utf-8"))
    assert manifest["objects"]["object"] == archive
    assert manifest["objects"]["count"] == len(list((state / "objects").iterdir()))

    restored = tmp_path / "restored"
    restored.mkdir()
    restore(backup_image, target, store, work, archive.removesuffix(".objects.tar.gz"), key=False,
            state=restored)  # fmt: skip

    assert await digests_of(target.host_url, run.id) == referred
    objects = MemoryObjectStore(restored / "objects")
    unreadable = [d for d in sorted(referred) if await objects.get(d) is None]
    assert unreadable == [], "every digest the run refers to is readable after the restore"


async def test_a_backup_names_a_missing_object_store_and_writes_nothing(
    backup_image: str, source: Database, persistence: PostgresPersistence, tmp_path: Path
) -> None:
    store, secrets, _ = directories(tmp_path, source)
    done = run_backup(
        backup_image, source, store, secrets, TAKTUS_BACKUP_OBJECTS_DIRECTORY="/nowhere"
    )
    assert done.returncode == 1
    assert "TAKTUS_BACKUP_OBJECTS_DIRECTORY names no directory" in done.stderr
    assert written(store) == []
    # The failure is recorded with the step it failed at, a token and never the message.
    ((tenant, name, outcome, reason),) = await outcomes(persistence)
    assert (tenant, outcome, reason) == ("default", "failed", "configuration")
    assert name.startswith("taktus-2")
