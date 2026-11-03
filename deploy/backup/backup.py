"""The instance's database backup: dump, optionally encrypt, write off the node, keep the retention.

Runs as the backup image's entry point (`deploy/backup/Dockerfile`), started by the chart's
CronJob (`deploy/k8s/chart/templates/backup.yaml`) on its schedule (ADR-0087). Standard library
only; the work is done by three standard tools that a person restoring by hand uses too:
`pg_dump` and `psql` of the database's major version, `age` for encryption, `rclone` for the
store. Nothing here imports Taktus: a backup is taken while Taktus is faulty as well, and is
restored without it (ADR-0013 C, `deploy/k8s/README.md` §11).

One run writes up to three objects under one name, `taktus-<UTC time>`:

- `<name>.dump` — `pg_dump --format=custom` of the whole database, or `<name>.dump.age` when a
  recipient is configured;
- `<name>.objects.tar.gz` — the instance's object store: every artifact, block record and
  recording the database refers to by digest, archived after the dump, so that every object a
  row of the dump names is in it (an object is written before the row that names it). Written
  where `TAKTUS_BACKUP_OBJECTS_DIRECTORY` names the store's directory; `.age` when encrypted;
- `<name>.json` — the manifest: when, which objects, their SHA-256 and size, whether they are
  encrypted, the schema revision, and every tenant's ledger head (`seq`, `hash`) read before the
  dump. The ledger is append-only, so every head read before the dump is in it; a restore is
  checked against these heads. Encrypted as `<name>.json.age` when the dump is.

Then the retention: every backup whose time is older than the retention is deleted — its dump,
its objects and its manifest — and no younger one. The newest backup is never deleted, whatever the
retention says, so a retention of 0 keeps exactly one. An object whose name is not of this form
is never touched: the program deletes only what it wrote.

Configuration, all from the environment; a secret only from a file (CREDENTIALS.md):

| Variable | What |
|---|---|
| `TAKTUS_DATABASE_URL_FILE` | the database's URL; a login that reads every row (BYPASSRLS) |
| `TAKTUS_BACKUP_STORE_ENDPOINT` | the object store's address; empty with `..._DIRECTORY` |
| `TAKTUS_BACKUP_STORE_REGION` | its region, where it needs one |
| `TAKTUS_BACKUP_STORE_BUCKET` | the bucket |
| `TAKTUS_BACKUP_STORE_PREFIX` | a path inside it, may be empty |
| `TAKTUS_CREDENTIAL_BACKUP_STORE_ACCESS_KEY_ID_FILE` | the credential's identifier |
| `TAKTUS_CREDENTIAL_BACKUP_STORE_FILE` | the credential's secret |
| `TAKTUS_BACKUP_STORE_DIRECTORY` | instead of a store: a directory, mounted from off the node |
| `TAKTUS_BACKUP_RETENTION_DAYS` | days a backup is kept; 30 by default (DEC-0058) |
| `TAKTUS_BACKUP_RECIPIENT` | an age public key; empty: not encrypted (DEC-0058) |
| `TAKTUS_BACKUP_WORK_DIR` | where the dump waits before it leaves; the temporary directory |
| `TAKTUS_BACKUP_OBJECTS_DIRECTORY` | the object store, `<state dir>/objects`; empty: none |
| `TAKTUS_BACKUP_POINT_IN_TIME` | `true`: a base backup beside the dump, and the log kept for it |
| `TAKTUS_CREDENTIAL_BACKUP_IDENTITY_FILE` | the age private key: `drill`, `fetch-wal` |
| `TAKTUS_DRILL_RESTORE_SECONDS` | the drill fails when its restore took longer; empty: measured |

At the end of every run, its outcome is recorded in the database it backs up (ADR-0106): one
row of `backup_outcome` per tenant of the table `tenant`, with the run's time, its name, `ok` or
`failed`, and for a failure the step that failed as a token — `configuration`, `database`,
`encryption`, `objects`, `store` or `retention`. Never a message: no secret and no tool output
reaches the row. The instance reads the newest outcome and tells each tenant's owner of a failed
or missing backup. A recording that fails is printed and changes neither the backup nor the exit
code; a run that cannot reach the database records nothing.

**Point-in-time recovery** (ADR-0174). With `TAKTUS_BACKUP_POINT_IN_TIME`, a run writes a fourth
object, `<name>.base-<system identifier>-<first segment>.tar.gz`: `pg_basebackup` as one tar stream
that holds the write-ahead log it needs. The database archives every finished segment of its log
with `archive-wal %p %f` as its `archive_command`, under `wal/<system identifier>/` in the same
store; a segment already there is not written again. The retention then deletes every segment
older than the first one the oldest kept base backup of its cluster needs, and every segment of a
cluster no kept base backup names; a timeline's history file never. `fetch-wal <system identifier>
%f %p` is the matching `restore_command`.

**The drill** (S-03, ADR-0174). `drill` restores a backup into a server of its own, in its working
directory, that listens on no address and archives nothing: the newest backup's dump, or with
`--to <time>` (or `--to latest`) the newest base backup finished before that moment with the
archived log replayed up to it. It never connects to the instance's database. It then recomputes
every tenant's ledger chain by the ledger's published rule, checks that every head of the
manifest is in it with its hash, and with `--heads <file>` that every tenant's newest entry is the
file's. It writes its report to `drills/taktus-<time>.drill.json` and keeps the drills by the
retention.

Exit code 0: written and the retention kept, or the drill verified. 1: the run failed, and the
log says why.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

NAME = re.compile(
    r"^taktus-(\d{8}T\d{6}Z)\."
    r"(dump|json|objects\.tar\.gz|base-(\d{1,20})-([0-9A-F]{24})\.tar\.gz)(\.age)?$"
)
"""A backup's object: its time, its kind, and for a base backup its cluster and first segment."""
DRILL = re.compile(r"^taktus-(\d{8}T\d{6}Z)\.drill\.json(\.age)?$")
"""A drill's report, under `drills/`."""
SEGMENT = re.compile(r"^([0-9A-F]{24})(\.[0-9A-F]{8}\.backup|\.partial)?(\.age)?$")
"""A segment of the write-ahead log, or a base backup's history file, under `wal/<cluster>/`."""
WAL_NAME = re.compile(r"^([0-9A-F]{24}(\.[0-9A-F]{8}\.backup|\.partial)?|[0-9A-F]{8}\.history)$")
"""What the database hands `archive-wal` and asks `fetch-wal` for: a segment, a backup history
file, a partial segment, or a timeline's history file. Nothing else reaches a path."""
SYSTEM = re.compile(r"^\d{1,20}$")
TIME = "%Y%m%dT%H%M%SZ"
DEFAULT_RETENTION_DAYS = 30
WAIT_SECONDS = 60.0

HEADS = (
    "SELECT coalesce(json_object_agg(tenant, json_build_object('seq', seq, 'hash', hash)), '{}') "
    "FROM (SELECT DISTINCT ON (tenant) tenant, seq, hash FROM ledger_entry "
    "ORDER BY tenant, seq DESC) AS head"
)
REVISION = "SELECT coalesce(max(version_num), '') FROM alembic_version"


STEPS = frozenset({"configuration", "database", "encryption", "objects", "store", "retention"})
"""The steps a run can fail at: the token a failed outcome records."""
RECORD_SECONDS = "10"
"""How long the recording of an outcome waits for the database to answer."""


class BackupError(Exception):
    """A step failed; the message says which, never with a secret in it. `step` is the token
    the outcome records."""

    def __init__(self, message: str, *, step: str = "configuration") -> None:
        super().__init__(message)
        self.step = step


# --- names and the retention ----------------------------------------------------------------------


def name_at(at: datetime) -> str:
    return "taktus-" + at.astimezone(UTC).strftime(TIME)


def time_of(name: str, pattern: re.Pattern[str] = NAME) -> datetime | None:
    """The time a backup object's name carries; None for an object this program did not write."""
    match = pattern.match(name)
    if match is None:
        return None
    return datetime.strptime(match[1], TIME).replace(tzinfo=UTC)


def expired(
    objects: Iterable[str],
    *,
    now: datetime,
    retention_days: int,
    pattern: re.Pattern[str] = NAME,
) -> list[str]:
    """The objects to delete: those of every backup older than the retention, never the newest
    backup's, never an object of another form. Sorted, so that a log reads in order. With
    `pattern`, the same for the drills' reports."""
    if retention_days < 0:
        raise BackupError(f"the retention is {retention_days} days; it cannot be negative")
    times = {name: at for name in objects if (at := time_of(name, pattern)) is not None}
    if not times:
        return []
    newest = max(times.values())
    limit = now - timedelta(days=retention_days)
    return sorted(name for name, at in times.items() if at < limit and at != newest)


def wal_expired(objects: Iterable[str], wal: Iterable[str]) -> list[str]:
    """The archived segments to delete, as `<cluster>/<file>`, given the backups kept: in a
    cluster with a kept base backup, every segment before the first one its oldest kept base
    backup needs; in a cluster no kept base backup names, every segment. A timeline's history
    file and an object of another form are never named. With no base backup kept at all, nothing
    is: the archive is then not this program's to judge (ADR-0174 §2)."""
    oldest: dict[str, tuple[datetime, str]] = {}
    for name in objects:
        match = NAME.match(name)
        if match is None or match[3] is None:
            continue
        at = datetime.strptime(match[1], TIME).replace(tzinfo=UTC)
        cluster, first = match[3], match[4]
        if cluster not in oldest or at < oldest[cluster][0]:
            oldest[cluster] = (at, first)
    if not oldest:
        return []
    doomed = []
    for path in wal:
        cluster, _, file = path.partition("/")
        match = SEGMENT.match(file)
        if match is None or not SYSTEM.match(cluster):
            continue
        # The timeline is the first eight digits; the place in the log the sixteen after them.
        if cluster not in oldest or match[1][8:] < oldest[cluster][1][8:]:
            doomed.append(path)
    return sorted(doomed)


# --- configuration --------------------------------------------------------------------------------


@dataclass(frozen=True)
class Settings:
    database_url: str
    database_env: Mapping[str, str]
    remote: str
    store_env: Mapping[str, str]
    retention_days: int
    recipient: str
    work_dir: Path
    objects_dir: Path | None = None
    point_in_time: bool = False
    identity: Path | None = None
    restore_seconds: int | None = None


def read_secret(env: Mapping[str, str], variable: str) -> str:
    path = env.get(variable, "")
    if not path:
        raise BackupError(f"{variable} is not set")
    try:
        return Path(path).read_text(encoding="utf-8").strip()
    except OSError as error:
        reason = f"{variable} names a file that cannot be read: {error.strerror}"
        raise BackupError(reason) from None


def without_password(url: str) -> tuple[str, dict[str, str]]:
    """The URL without its password, and the password as libpq's variable for the child process
    alone: a command line is visible to every process of the container, a child's environment is
    not. A driver named in the scheme (`postgresql+psycopg://`) is dropped."""
    parts = urlsplit(re.sub(r"^postgres(ql)?(\+[a-z0-9]+)?://", "postgresql://", url))
    if parts.password is None:
        return parts.geturl(), {}
    host = parts.hostname or ""
    if ":" in host:
        host = f"[{host}]"
    netloc = (quote(unquote(parts.username or ""), safe="") + "@" if parts.username else "") + host
    if parts.port is not None:
        netloc += f":{parts.port}"
    return parts._replace(netloc=netloc).geturl(), {"PGPASSWORD": unquote(parts.password)}


def flag(env: Mapping[str, str], variable: str) -> bool:
    raw = env.get(variable, "").strip().lower()
    if raw not in ("", "true", "false"):
        raise BackupError(f"{variable} is {raw!r}; it is true or false")
    return raw == "true"


def settings(env: Mapping[str, str], *, database: bool = True) -> Settings:
    """Read and check the configuration before anything is done. Without `database`, for the
    commands that never connect to the instance's database — `archive-wal`, `fetch-wal`,
    `drill` — no database URL is read."""
    if database:
        url, database_env = without_password(read_secret(env, "TAKTUS_DATABASE_URL_FILE"))
    else:
        url, database_env = "", {}
    raw = env.get("TAKTUS_BACKUP_RETENTION_DAYS", "") or str(DEFAULT_RETENTION_DAYS)
    if not raw.isdigit():
        raise BackupError(f"TAKTUS_BACKUP_RETENTION_DAYS is {raw!r}; it is a whole number of days")
    recipient = env.get("TAKTUS_BACKUP_RECIPIENT", "").strip()
    if recipient and not recipient.startswith("age1"):
        raise BackupError("TAKTUS_BACKUP_RECIPIENT is not an age public key (age1…)")
    directory = env.get("TAKTUS_BACKUP_STORE_DIRECTORY", "")
    endpoint = env.get("TAKTUS_BACKUP_STORE_ENDPOINT", "")
    if bool(directory) == bool(endpoint):
        raise BackupError(
            "set exactly one of TAKTUS_BACKUP_STORE_ENDPOINT and TAKTUS_BACKUP_STORE_DIRECTORY"
        )
    store_env: dict[str, str] = {}
    if directory:
        remote = f":local:{directory.rstrip('/')}"
    else:
        bucket = env.get("TAKTUS_BACKUP_STORE_BUCKET", "")
        if not bucket:
            raise BackupError("TAKTUS_BACKUP_STORE_BUCKET is not set")
        prefix = env.get("TAKTUS_BACKUP_STORE_PREFIX", "").strip("/")
        remote = f":s3:{bucket}" + (f"/{prefix}" if prefix else "")
        # rclone reads a backend's options from variables of its own; they reach the child
        # process only, never this container's specification.
        store_env = {
            "RCLONE_S3_PROVIDER": "Other",
            "RCLONE_S3_ENDPOINT": endpoint,
            "RCLONE_S3_REGION": env.get("TAKTUS_BACKUP_STORE_REGION", ""),
            "RCLONE_S3_ACCESS_KEY_ID": read_secret(
                env, "TAKTUS_CREDENTIAL_BACKUP_STORE_ACCESS_KEY_ID_FILE"
            ),
            "RCLONE_S3_SECRET_ACCESS_KEY": read_secret(env, "TAKTUS_CREDENTIAL_BACKUP_STORE_FILE"),
            "RCLONE_S3_NO_CHECK_BUCKET": "true",
        }
    work_dir = Path(env.get("TAKTUS_BACKUP_WORK_DIR", "") or tempfile.gettempdir())
    objects = env.get("TAKTUS_BACKUP_OBJECTS_DIRECTORY", "").strip()
    objects_dir = Path(objects) if objects else None
    if objects_dir is not None and not objects_dir.is_dir():
        raise BackupError(f"TAKTUS_BACKUP_OBJECTS_DIRECTORY names no directory: {objects}")
    identity_file = env.get("TAKTUS_CREDENTIAL_BACKUP_IDENTITY_FILE", "").strip()
    identity = Path(identity_file) if identity_file else None
    if identity is not None and not identity.is_file():
        raise BackupError("TAKTUS_CREDENTIAL_BACKUP_IDENTITY_FILE names a file that cannot be read")
    seconds = env.get("TAKTUS_DRILL_RESTORE_SECONDS", "").strip()
    if seconds and not seconds.isdigit():
        raise BackupError(f"TAKTUS_DRILL_RESTORE_SECONDS is {seconds!r}; it is a whole number")
    return Settings(
        url,
        database_env,
        remote,
        store_env,
        int(raw),
        recipient,
        work_dir,
        objects_dir,
        point_in_time=flag(env, "TAKTUS_BACKUP_POINT_IN_TIME"),
        identity=identity,
        restore_seconds=int(seconds) if seconds else None,
    )


# --- the tools ------------------------------------------------------------------------------------


TOOL_STEPS = {"pg_isready": "database", "psql": "database", "pg_dump": "database"}
TOOL_STEPS |= {"pg_basebackup": "database"}
TOOL_STEPS |= {"age": "encryption", "rclone": "store"}


def run(command: Sequence[str], *, env: Mapping[str, str] | None = None, what: str) -> str:
    """Run one tool; on failure, raise with its last lines of error output. The command line
    never carries a secret, so it may be named."""
    merged = {**os.environ, **(env or {})}
    step = TOOL_STEPS.get(Path(command[0]).name, "configuration")
    try:
        done = subprocess.run(command, env=merged, capture_output=True, text=True, check=False)  # noqa: S603
    except OSError as error:
        raise BackupError(f"{what} failed: {command[0]}: {error.strerror}", step=step) from None
    if done.returncode != 0:
        tail = "\n".join(done.stderr.strip().splitlines()[-5:])
        raise BackupError(f"{what} failed ({done.returncode}): {tail}", step=step)
    return done.stdout


def query(s: Settings, sql: str) -> str:
    command = ["psql", "--no-psqlrc", "--tuples-only", "--no-align", "--dbname", s.database_url]
    return run([*command, "-c", sql], env=s.database_env, what="psql").strip()


def store(s: Settings, *args: str, what: str) -> str:
    return run(["rclone", "--config", "/dev/null", *args], env=s.store_env, what=what)


def listing(s: Settings) -> list[str]:
    out = store(s, "lsf", "--files-only", s.remote, what="listing the store")
    return [line for line in out.splitlines() if line]


def encrypt(s: Settings, path: Path) -> Path:
    if not s.recipient:
        return path
    target = path.with_name(path.name + ".age")
    run(["age", "--recipient", s.recipient, "--output", str(target), str(path)], what="age")
    path.unlink()
    return target


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def archive(directory: Path, target: Path) -> int:
    """Every file of the object store, flat, as the store keeps them; return how many. A file
    written while the archive is made may be in it or not: it is named by no row of the dump."""
    count = 0
    with tarfile.open(target, "w:gz") as tar:
        for path in sorted(p for p in directory.iterdir() if p.is_file()):
            tar.add(path, arcname=path.name, recursive=False)
            count += 1
    return count


def described(path: Path) -> dict[str, object]:
    return {"object": path.name, "sha256": sha256(path), "bytes": path.stat().st_size}


def run_to_file(
    command: Sequence[str], target: Path, *, env: Mapping[str, str] | None = None, what: str
) -> None:
    """Run one tool whose output is the object itself, written to `target` as it comes."""
    merged = {**os.environ, **(env or {})}
    step = TOOL_STEPS.get(Path(command[0]).name, "configuration")
    try:
        with target.open("wb") as handle:
            done = subprocess.run(  # noqa: S603
                command, env=merged, stdout=handle, stderr=subprocess.PIPE, check=False
            )
    except OSError as error:
        raise BackupError(f"{what} failed: {command[0]}: {error.strerror}", step=step) from None
    if done.returncode != 0:
        tail = "\n".join(done.stderr.decode(errors="replace").strip().splitlines()[-5:])
        raise BackupError(f"{what} failed ({done.returncode}): {tail}", step=step)


def listed(s: Settings, path: str, *, recursive: bool = False) -> list[str]:
    """The files under `path` in the store; none where the path does not exist yet — rclone's
    exit code 3, *directory not found*, which a directory store answers before the first write."""
    command = ["rclone", "--config", "/dev/null", "lsf", "--files-only"]
    command += [*(["--recursive"] if recursive else []), f"{s.remote}/{path}"]
    try:
        done = subprocess.run(  # noqa: S603
            command, env={**os.environ, **s.store_env}, capture_output=True, text=True, check=False
        )
    except OSError as error:
        raise BackupError(
            f"listing {path} failed: rclone: {error.strerror}", step="store"
        ) from None
    if done.returncode == 3:
        return []
    if done.returncode != 0:
        tail = "\n".join(done.stderr.strip().splitlines()[-5:])
        raise BackupError(f"listing {path} failed ({done.returncode}): {tail}", step="store")
    return [line for line in done.stdout.splitlines() if line]


def encrypted_copy(s: Settings, source: Path, target: Path) -> Path:
    """`source` encrypted to the recipient as `target`, the source left as it is; the source
    itself without a recipient."""
    if not s.recipient:
        return source
    run(["age", "--recipient", s.recipient, "--output", str(target), str(source)], what="age")
    return target


def decrypt(s: Settings, path: Path) -> Path:
    """An object fetched from the store, decrypted beside it where its name ends in `.age`."""
    if not path.name.endswith(".age"):
        return path
    if s.identity is None:
        raise BackupError(
            f"{path.name} is encrypted: TAKTUS_CREDENTIAL_BACKUP_IDENTITY_FILE names no key",
            step="encryption",
        )
    target = path.with_name(path.name.removesuffix(".age"))
    command = ["age", "--decrypt", "--identity", str(s.identity), "--output", str(target)]
    run([*command, str(path)], what="age")
    path.unlink()
    return target


def fetch(s: Settings, name: str, directory: Path) -> Path:
    """One object of the store, copied into `directory` under its own name."""
    target = directory / Path(name).name
    store(s, "copyto", f"{s.remote}/{name}", str(target), what=f"fetching {name}")
    return target


FIRST_SEGMENT = re.compile(r"^START WAL LOCATION: \S+ \(file ([0-9A-F]{24})\)$", re.MULTILINE)


def first_segment(base: Path) -> str:
    """The segment a base backup's replay starts at, from its `backup_label`."""
    try:
        with tarfile.open(base, "r:gz") as tar:
            member = tar.extractfile("backup_label")
            label = b"" if member is None else member.read()
    except (OSError, KeyError, tarfile.TarError) as error:
        reason = f"the base backup holds no readable backup_label: {type(error).__name__}"
        raise BackupError(reason, step="database") from None
    match = FIRST_SEGMENT.search(label.decode("ascii", errors="replace"))
    if match is None:
        raise BackupError("the base backup's backup_label names no first segment", step="database")
    return match[1]


def base_backup(s: Settings, work: Path, name: str) -> tuple[Path, dict[str, object]]:
    """A base backup of the database as one compressed tar stream that holds the segments it
    needs itself (ADR-0174 §1), named with its cluster and its first segment."""
    cluster = query(s, "SELECT system_identifier FROM pg_control_system()")
    if not SYSTEM.match(cluster):
        raise BackupError("the database named no system identifier", step="database")
    raw = work / f"{name}.base.tar.gz"
    command = ["pg_basebackup", "--dbname", s.database_url, "--pgdata=-", "--format=tar"]
    command += ["--wal-method=fetch", "--gzip", "--checkpoint=fast", "--no-password"]
    run_to_file(command, raw, env=s.database_env, what="pg_basebackup")
    first = first_segment(raw)
    finished = datetime.now(UTC)
    target = raw.rename(raw.with_name(f"{name}.base-{cluster}-{first}.tar.gz"))
    target = encrypt(s, target)
    parts = urlsplit(s.database_url)
    return target, {
        **described(target),
        "system_identifier": cluster,
        "first_segment": first,
        "finished": finished.isoformat(),
        # Who restores it connects as the login that took it, to the database it was taken of.
        "user": unquote(parts.username or ""),
        "database": parts.path.lstrip("/"),
    }


# --- one run --------------------------------------------------------------------------------------


def wait_for_database(
    s: Settings, *, seconds: float = WAIT_SECONDS, sleep: Callable[[float], None] = time.sleep
) -> None:
    """Wait until the database accepts connections, for at most `seconds`. A pod that has just
    started may be refused for a few seconds while the cluster applies its network policy to it
    (#67, observed on the instance on 2026-10-12): the first connection of a scheduled backup
    must not fail for that."""
    deadline = time.monotonic() + seconds
    while True:
        try:
            run(["pg_isready", "--dbname", s.database_url], env=s.database_env, what="pg_isready")
            return
        except BackupError:
            if time.monotonic() >= deadline:
                raise
        sleep(2.0)


def backup(s: Settings, *, now: datetime) -> str:
    """Write one backup; return its name. Nothing is deleted here."""
    name = name_at(now)
    wait_for_database(s)
    heads = json.loads(query(s, HEADS) or "{}")
    revision = query(s, REVISION)
    with tempfile.TemporaryDirectory(dir=s.work_dir) as work:
        dump = Path(work) / f"{name}.dump"
        run(
            ["pg_dump", "--format=custom", "--file", str(dump), "--dbname", s.database_url],
            env=s.database_env,
            what="pg_dump",
        )
        dump = encrypt(s, dump)
        written = [dump]
        base: dict[str, object] | None = None
        if s.point_in_time:
            # Before the object store's archive, so that it holds every object the base names.
            base_path, base = base_backup(s, Path(work), name)
            written.append(base_path)
        objects: dict[str, object] | None = None
        if s.objects_dir is not None:
            # After the dump: every object a row of it names was written before that row.
            archived = Path(work) / f"{name}.objects.tar.gz"
            try:
                count = archive(s.objects_dir, archived)
            except (OSError, tarfile.TarError) as error:
                reason = f"archiving the object store failed: {type(error).__name__}"
                raise BackupError(reason, step="objects") from None
            archived = encrypt(s, archived)
            objects = {**described(archived), "count": count}
            written.append(archived)
        manifest = {
            "name": name,
            "created": now.astimezone(UTC).isoformat(),
            "object": dump.name,
            "sha256": sha256(dump),
            "bytes": dump.stat().st_size,
            "objects": objects,
            "base": base,
            "encrypted": bool(s.recipient),
            "recipient": s.recipient or None,
            "schema_revision": revision,
            "ledger_heads": heads,
        }
        manifest_path = Path(work) / f"{name}.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", "utf-8")
        manifest_path = encrypt(s, manifest_path)
        # The manifest last: a backup without it is incomplete, and a restore starts from it.
        written.append(manifest_path)
        for path in written:
            store(s, "copyto", str(path), f"{s.remote}/{path.name}", what=f"writing {path.name}")
        listed = set(listing(s))
        missing = {path.name for path in written} - listed
        if missing:
            reason = f"written but not listed in the store: {sorted(missing)}"
            raise BackupError(reason, step="store")
        stored = (
            "the database alone"
            if objects is None
            else f"{objects['count']} object(s) in {objects['object']}"
        )
        if base is not None:
            stored += f", a base backup from segment {base['first_segment']}"
        print(
            f"backup {name}: {dump.name} ({manifest['bytes']} bytes), {stored}, "
            f"{len(heads)} tenant(s)"
        )
    return name


def keep_retention(s: Settings, *, now: datetime) -> list[str]:
    """The backups older than the retention, then the archived segments no kept base backup
    needs, then the drills' reports older than the retention (ADR-0087 §4, ADR-0174 §2)."""
    try:
        names = listing(s)
        doomed = expired(names, now=now, retention_days=s.retention_days)
        for name in doomed:
            store(s, "deletefile", f"{s.remote}/{name}", what=f"deleting {name}")
            print(f"deleted {name}: older than {s.retention_days} day(s)")
        kept = sorted(set(names) - set(doomed))
        if s.point_in_time or any((m := NAME.match(n)) and m[3] for n in kept):
            segments = wal_expired(kept, listed(s, "wal", recursive=True))
            for path in segments:
                store(s, "deletefile", f"{s.remote}/wal/{path}", what=f"deleting wal/{path}")
            if segments:
                print(f"deleted {len(segments)} archived segment(s) no kept base backup needs")
        drills = expired(
            listed(s, "drills"), now=now, retention_days=s.retention_days, pattern=DRILL
        )
        for name in drills:
            store(s, "deletefile", f"{s.remote}/drills/{name}", what=f"deleting drills/{name}")
    except BackupError as error:
        raise BackupError(str(error), step="retention") from None
    return doomed


# --- the archive of the write-ahead log -----------------------------------------------------------


def system_identifier(data_dir: Path) -> str:
    """The cluster's system identifier, from its control file: a database restored from a dump
    is a new cluster and has a new one, so its segments never overwrite an earlier cluster's."""
    out = run(["pg_controldata", str(data_dir)], what="pg_controldata")
    for line in out.splitlines():
        label, _, value = line.partition(":")
        if label.strip() == "Database system identifier" and SYSTEM.match(value.strip()):
            return value.strip()
    raise BackupError("pg_controldata named no system identifier", step="database")


def archive_wal(s: Settings, source: Path, file: str, *, data_dir: Path) -> str:
    """One finished file of the write-ahead log into the store, as the database's
    `archive_command`; a file already there is not written again. Returns where it is."""
    if WAL_NAME.match(file) is None:
        raise BackupError(f"{file!r} is not a file of the write-ahead log")
    cluster = system_identifier(data_dir)
    stored = file + (".age" if s.recipient else "")
    path = f"wal/{cluster}/{stored}"
    if stored in listed(s, path):
        print(f"archive-wal: {path} is in the store already")
        return path
    with tempfile.TemporaryDirectory(dir=s.work_dir) as work:
        upload = encrypted_copy(s, source, Path(work) / stored)
        store(s, "copyto", str(upload), f"{s.remote}/{path}", what=f"writing {path}")
    return path


def fetch_wal(s: Settings, cluster: str, file: str, target: Path) -> None:
    """One file of the archived write-ahead log out of the store, as a `restore_command`. A file
    the store does not hold fails, which is how the database learns where the archive ends."""
    if WAL_NAME.match(file) is None or SYSTEM.match(cluster) is None:
        raise BackupError(f"{cluster}/{file} is not a file of the write-ahead log")
    path = f"wal/{cluster}/{file}"
    if s.identity is None:
        store(s, "copyto", f"{s.remote}/{path}", str(target), what=f"fetching {path}")
        return
    with tempfile.TemporaryDirectory(dir=s.work_dir) as work:
        fetched = fetch(s, f"{path}.age", Path(work))
        command = ["age", "--decrypt", "--identity", str(s.identity), "--output", str(target)]
        run([*command, str(fetched)], what="age")


# --- the ledger's chains, recomputed by their published rule (ADR-0006, ADR-0164) -----------------


LEDGER_FIELDS = (
    "seq", "ts", "kind", "prev_hash", "hash", "refs", "method", "model", "adapter",
    "consumption", "outcome", "duration_seconds", "content_digest", "rehearsal", "chain_seq",
    "chain", "through",
)  # fmt: skip
"""The fields of an entry's document, as `LedgerEntry.json` names them: a test holds this list
to the schema, so that a field added there is added here."""
ANCHORED = "ledger.anchored"


def entry_document(row: Mapping[str, object]) -> dict[str, object]:
    """An entry as the JSON document its hash covers, from its row: absent fields left out,
    `prev_hash` kept as null, the time in UTC written as the schema's binding writes it."""
    document = {key: row[key] for key in LEDGER_FIELDS if row.get(key) is not None}
    document["prev_hash"] = row.get("prev_hash")
    if "duration_seconds" in document:
        # A column of floating point: PostgreSQL writes 32 where the schema's binding writes 32.0.
        document["duration_seconds"] = float(str(document["duration_seconds"]))
    at = datetime.fromisoformat(str(row["ts"])).astimezone(UTC)
    text = at.strftime("%Y-%m-%dT%H:%M:%S")
    document["ts"] = text + (f".{at.microsecond:06d}" if at.microsecond else "") + "Z"
    return document


def canonical(document: Mapping[str, object]) -> bytes:
    without_hash = {key: value for key, value in document.items() if key != "hash"}
    return json.dumps(
        without_hash, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def hash_of(document: Mapping[str, object]) -> str:
    return "sha256:" + hashlib.sha256(canonical(document)).hexdigest()


def chain_name(document: Mapping[str, object]) -> str:
    """The chain an entry is on: its run's, or "" for the tenant's."""
    refs = document.get("refs")
    run_id = refs.get("run_id") if isinstance(refs, dict) else None
    if document.get("chain_seq") is None or document.get("chain") == "tenant" or run_id is None:
        return ""
    return str(run_id)


def merkle_root(heads: Iterable[tuple[str, int, str]]) -> str | None:
    """The anchor's tree over the run chains' heads, ordered by chain (ADR-0164)."""
    level = [
        hash_of({"chain": chain, "chain_seq": place, "digest": digest})
        for chain, place, digest in sorted(heads)
    ]
    if not level:
        return None
    while len(level) > 1:
        paired = [
            "sha256:" + hashlib.sha256((level[i] + level[i + 1]).encode("ascii")).hexdigest()
            for i in range(0, len(level) - 1, 2)
        ]
        if len(level) % 2:
            paired.append(level[-1])
        level = paired
    return level[0]


@dataclass
class Chains:
    """What a walk of one tenant's entries found."""

    entries: int = 0
    findings: list[str] = field(default_factory=list)
    head: tuple[int, str] | None = None
    """The newest entry by sequence number: its seq and hash."""
    hashes: dict[int, str] = field(default_factory=dict)
    """The hash at each sequence number asked for in `wanted`."""


def verify_ledger(rows: Iterable[Mapping[str, object]], wanted: Iterable[int] = ()) -> Chains:
    """Walk one tenant's entries in sequence order, every chain at once, as Taktus's own
    verification walks them from the first entry: sequence numbers rise; each entry follows the
    newest of its chain by place and by `prev_hash`; its hash matches its content; no entry of the
    rule before ADR-0164 follows one after it; each anchor's root matches the heads of the run
    chains it covers. Every finding names the sequence number."""
    found = Chains()
    asked = set(wanted)
    reached, anchored, ruled = 0, 0, False
    chains: dict[str, tuple[int, str, int]] = {}
    pending: dict[str, list[tuple[int, int, str]]] = {}
    for row in rows:
        document = entry_document(row)
        seq = int(str(document["seq"]))
        digest = str(document["hash"])
        if seq <= reached:
            found.findings.append(f"entry {seq}: sequence number does not rise")
        chain_seq = document.get("chain_seq")
        if chain_seq is None:
            if ruled:
                found.findings.append(f"entry {seq}: written by the rule before ADR-0164")
        else:
            ruled = True
        name = chain_name(document)
        place = seq if chain_seq is None else int(str(chain_seq))
        previous = chains.get(name)
        expected = 1 if previous is None else previous[0] + 1
        if place != expected:
            found.findings.append(f"entry {seq}: expected place {expected} in its chain")
        if document["prev_hash"] != (None if previous is None else previous[1]):
            named = "its predecessor" if previous is None else f"entry {previous[2]}"
            found.findings.append(f"entry {seq}: prev_hash does not match {named}")
        if hash_of(document) != digest:
            found.findings.append(f"entry {seq}: hash does not match its content")
        if document.get("kind") == ANCHORED and name == "":
            through = document.get("through")
            if not isinstance(through, int) or through < anchored or through >= seq:
                found.findings.append(f"entry {seq}: an anchor without a bound before it")
            else:
                heads = []
                for chain, items in pending.items():
                    covered = [item for item in items if anchored < item[0] <= through]
                    if covered:
                        newest = max(covered)
                        heads.append((chain, newest[1], newest[2]))
                if merkle_root(heads) != document.get("content_digest"):
                    found.findings.append(
                        f"entry {seq}: the anchor does not match the heads of the run "
                        "chains it covers"
                    )
                pending = {
                    chain: kept
                    for chain, items in pending.items()
                    if (kept := [item for item in items if item[0] > through])
                }
                anchored = through
        if name:
            pending.setdefault(name, []).append((seq, place, digest))
        chains[name] = (place, digest, seq)
        if seq in asked:
            found.hashes[seq] = digest
        if found.head is None or seq > found.head[0]:
            found.head = (seq, digest)
        reached = max(reached, seq)
        found.entries += 1
    return found


def held_to(chains: Chains, before: object, exact: object) -> list[str]:
    """Where a tenant's restored chain fails the digest taken before: the manifest's head must
    be in it with its hash; a head noted at the moment restored to must be its newest entry."""
    failures = []
    if isinstance(before, dict):
        seq, digest = int(str(before["seq"])), str(before["hash"])
        if chains.hashes.get(seq) != digest:
            failures.append(f"the head taken before, entry {seq}, is not in the chain as it was")
    if isinstance(exact, dict):
        newest = (int(str(exact["seq"])), str(exact["hash"]))
        if chains.head != newest:
            failures.append(f"the newest entry is not entry {newest[0]} with the hash noted")
    return failures


# --- the drill (S-03) -----------------------------------------------------------------------------


LEDGER_ROWS = "SELECT to_jsonb(l)::text FROM ledger_entry AS l ORDER BY tenant, seq"
TENANTS = "SELECT id FROM tenant ORDER BY id"
RECOVERY_SECONDS = 3600


@dataclass
class Scratch:
    """A server of the drill's own in its working directory: it listens on no address, takes
    connections from its own socket alone, and archives nothing."""

    directory: Path
    user: str = "postgres"
    database: str = "postgres"
    env: Mapping[str, str] = field(default_factory=dict)

    @property
    def data(self) -> Path:
        return self.directory / "data"

    def start(self) -> None:
        hba = self.directory / "pg_hba.conf"
        hba.write_text("local all all trust\n", encoding="utf-8")
        options = (
            f"-c listen_addresses='' -c unix_socket_directories={self.directory} "
            f"-c hba_file={hba} -c archive_mode=off -c port=5432"
        )
        command = ["pg_ctl", "--pgdata", str(self.data), "--log", str(self.log), "--wait"]
        command += ["--timeout", str(RECOVERY_SECONDS), "--options", options, "start"]
        try:
            run(command, env=self.env, what="starting the scratch server")
        except BackupError as error:
            raise BackupError(f"{error}\n{self.tail()}", step="database") from None

    @property
    def log(self) -> Path:
        return self.directory / "server.log"

    def tail(self) -> str:
        try:
            lines = self.log.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return ""
        return "\n".join(line for line in lines[-12:] if "FATAL" in line or "LOG" in line)

    def running(self) -> bool:
        done = subprocess.run(  # noqa: S603
            ["pg_ctl", "--pgdata", str(self.data), "status"],  # noqa: S607
            capture_output=True, check=False,
        )  # fmt: skip
        return done.returncode == 0

    def stop(self) -> None:
        subprocess.run(  # noqa: S603
            ["pg_ctl", "--pgdata", str(self.data), "--mode", "fast", "--wait", "stop"],  # noqa: S607
            capture_output=True, check=False,
        )  # fmt: skip

    def psql(self) -> list[str]:
        return [
            "psql", "--no-psqlrc", "--tuples-only", "--no-align", "-v", "ON_ERROR_STOP=1",
            "--host", str(self.directory), "--username", self.user, "--dbname", self.database,
        ]  # fmt: skip

    def query(self, sql: str) -> str:
        return run([*self.psql(), "-c", sql], env=self.env, what="psql").strip()

    def promoted(self, *, sleep: Callable[[float], None] = time.sleep) -> None:
        """Wait until recovery has ended and the server was promoted; fail when it stopped,
        which is what it does when the moment asked for lies beyond the archive."""
        deadline = time.monotonic() + RECOVERY_SECONDS
        while True:
            try:
                if self.query("SELECT pg_is_in_recovery()") == "f":
                    return
            except BackupError:
                if not self.running():
                    reason = "the archive does not reach the moment asked for, or recovery failed"
                    raise BackupError(f"{reason}:\n{self.tail()}", step="database") from None
            if time.monotonic() >= deadline:
                raise BackupError("recovery did not end in time", step="database")
            sleep(1.0)

    def rows(self) -> Iterable[dict[str, object]]:
        """Every ledger entry, tenant by tenant in sequence order, one at a time."""
        command = [*self.psql(), "-c", LEDGER_ROWS]
        env = {**os.environ, **self.env, "PGTZ": "UTC"}
        with subprocess.Popen(  # noqa: S603
            command, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        ) as process:
            for line in process.stdout or ():
                if line.strip():
                    yield json.loads(line)
            error = process.stderr.read() if process.stderr else ""
        if process.returncode != 0:
            raise BackupError(f"reading the ledger failed: {error.strip()[-500:]}", step="database")


def manifests(s: Settings, names: Iterable[str], chosen: str | None) -> list[str]:
    """The manifests of the store, newest first; only the chosen backup's with `chosen`."""
    found = [n for n in names if (m := NAME.match(n)) is not None and m[2] == "json"]
    if chosen is not None:
        found = [n for n in found if n.split(".", 1)[0] == chosen]
    return sorted(found, reverse=True)


def chosen_backup(
    s: Settings, work: Path, *, chosen: str | None, to: datetime | str | None
) -> tuple[str, dict[str, object]]:
    """The backup to restore and its manifest: the newest, or the chosen one; for a moment, the
    newest whose base backup finished before it."""
    for name in manifests(s, listing(s), chosen):
        manifest_path = decrypt(s, fetch(s, name, work))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if to is None:
            return name, manifest
        base = manifest.get("base")
        if not isinstance(base, dict):
            continue
        if to == "latest" or (
            isinstance(to, datetime) and datetime.fromisoformat(str(base["finished"])) <= to
        ):
            return name, manifest
    wanted = "a backup" if to is None else "a base backup finished before the moment asked for"
    raise BackupError(f"the store holds no {wanted}", step="store")


def fetched_object(s: Settings, described_object: Mapping[str, object], work: Path) -> Path:
    """An object the manifest names, fetched, its SHA-256 compared, and decrypted."""
    name = str(described_object["object"])
    path = fetch(s, name, work)
    if sha256(path) != described_object["sha256"]:
        raise BackupError(f"{name} does not have the SHA-256 its manifest names", step="store")
    return decrypt(s, path)


def restore_dump(s: Settings, scratch: Scratch, dump: Path) -> None:
    """ADR-0087 §5 in the scratch server: a new cluster, the application role, `pg_restore`."""
    command = ["initdb", "--pgdata", str(scratch.data), "--username", scratch.user]
    run([*command, "--auth=trust", "--no-sync", "--encoding=UTF8"], what="initdb")
    scratch.start()
    scratch.query(
        "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'taktus_app') "
        "THEN CREATE ROLE taktus_app NOLOGIN; END IF; END $$"
    )
    command = ["pg_restore", "--no-owner", "--exit-on-error", "--single-transaction"]
    command += ["--host", str(scratch.directory), "--username", scratch.user]
    run([*command, "--dbname", scratch.database, str(dump)], env=scratch.env, what="pg_restore")


def restore_to(s: Settings, scratch: Scratch, base: Path, cluster: str, to: datetime | str) -> None:
    """A base backup and the archived log replayed to the moment, in the scratch server: the
    steps of `deploy/k8s/README.md` §11, *To a chosen moment*."""
    scratch.data.mkdir(mode=0o700)
    run(["tar", "-xzf", str(base), "-C", str(scratch.data)], what="tar")
    (scratch.data / "recovery.signal").write_text("", encoding="utf-8")
    program = Path(__file__).resolve()
    lines = [
        f"restore_command = '{sys.executable} {program} fetch-wal {cluster} %f %p'",
        "recovery_target_action = 'promote'",
        "recovery_target_timeline = 'latest'",
    ]
    if isinstance(to, datetime):
        lines.append(f"recovery_target_time = '{to.astimezone(UTC).isoformat()}'")
    with (scratch.data / "postgresql.auto.conf").open("a", encoding="utf-8") as handle:
        handle.write("\n# The drill (ADR-0174)\n" + "\n".join(lines) + "\n")
    try:
        # The server may stop before it accepts a connection, or while it replays: either way
        # the moment asked for was not reached.
        scratch.start()
    except BackupError:
        reason = "the archive does not reach the moment asked for, or recovery failed"
        raise BackupError(f"{reason}:\n{scratch.tail()}", step="database") from None
    scratch.promoted()


def verified(
    scratch: Scratch, manifest: Mapping[str, object], exact: Mapping[str, object] | None
) -> dict[str, dict[str, object]]:
    """Every tenant's chain in the restored database, recomputed and held to the digest taken
    before: the manifest's heads, and with `exact` the heads noted at the moment."""
    before = manifest.get("ledger_heads")
    before = before if isinstance(before, dict) else {}
    exact = exact or {}
    tenants = set(scratch.query(TENANTS).splitlines()) | set(before) | set(exact)
    rows_by_tenant: dict[str, list[dict[str, object]]] = {}
    report: dict[str, dict[str, object]] = {}

    def close(tenant: str, rows: list[dict[str, object]]) -> None:
        wanted = [int(str(before[tenant]["seq"]))] if tenant in before else []
        chains = verify_ledger(rows, wanted)
        failures = held_to(chains, before.get(tenant), exact.get(tenant))
        report[tenant] = {
            "entries": chains.entries,
            "head": None
            if chains.head is None
            else {"seq": chains.head[0], "hash": chains.head[1]},
            "findings": chains.findings[:20],
            "held_to": failures,
            "intact": not chains.findings and not failures,
        }

    current: str | None = None
    for row in scratch.rows():
        tenant = str(row["tenant"])
        if tenant != current:
            if current is not None:
                close(current, rows_by_tenant.pop(current))
            current = tenant
        rows_by_tenant.setdefault(tenant, []).append(row)
    if current is not None:
        close(current, rows_by_tenant.pop(current))
    for tenant in sorted(tenants - set(report)):
        close(tenant, [])
    return dict(sorted(report.items()))


def tenants_of(report: Mapping[str, object]) -> list[str]:
    tenants = report["tenants"]
    return sorted(tenants) if isinstance(tenants, dict) else []


def as_list(value: object) -> list[str]:
    return [str(item) for item in value] if isinstance(value, list) else []


def drill(
    s: Settings,
    env: Mapping[str, str],
    *,
    now: datetime,
    chosen: str | None = None,
    to: datetime | str | None = None,
    heads: Path | None = None,
) -> dict[str, object]:
    """Restore a backup into a scratch server, verify every chain, and say what was found
    (S-03, ADR-0174 §3). Never connects to the instance's database. A restore that fails is a
    failed drill, never an error without a report."""
    exact = None if heads is None else json.loads(heads.read_text(encoding="utf-8"))
    name: str | None = None
    tenants: dict[str, dict[str, object]] = {}
    failures: list[str] = []
    reached: str | None = None
    seconds: float | None = None
    with tempfile.TemporaryDirectory(dir=s.work_dir) as work_dir:
        work = Path(work_dir)
        scratch = Scratch(work / "server", env={**env, **s.store_env})
        scratch.directory.mkdir()
        try:
            name, manifest = chosen_backup(s, work, chosen=chosen, to=to)
            started = time.monotonic()
            base = manifest.get("base")
            if to is None:
                restore_dump(s, scratch, fetched_object(s, manifest, work))
            elif isinstance(base, dict):
                scratch.user, scratch.database = str(base["user"]), str(base["database"])
                cluster = str(base["system_identifier"])
                restore_to(s, scratch, fetched_object(s, base, work), cluster, to)
            tenants = verified(scratch, manifest, exact)
            reached = scratch.query("SELECT max(ts)::text FROM ledger_entry") or None
            seconds = round(time.monotonic() - started, 1)
        except BackupError as error:
            failures.append(str(error))
        finally:
            scratch.stop()
    for tenant, found in tenants.items():
        if not found["intact"]:
            named = [*as_list(found["held_to"]), *as_list(found["findings"])]
            failures.append(f"{tenant}: " + "; ".join(named))
    if s.restore_seconds is not None and seconds is not None and seconds > s.restore_seconds:
        failures.append(f"the restore took {seconds} s, more than {s.restore_seconds} s")
    return {
        "drill": name_at(now),
        "at": now.astimezone(UTC).isoformat(),
        "backup": None if name is None else name.split(".", 1)[0],
        "mode": "dump" if to is None else "point-in-time",
        "to": None if to is None else (to if isinstance(to, str) else to.isoformat()),
        "restore_seconds": seconds,
        "restore_seconds_allowed": s.restore_seconds,
        "newest_entry_at": reached,
        "tenants": tenants,
        "outcome": "failed" if failures else "ok",
        "failures": failures,
    }


def write_report(s: Settings, report: Mapping[str, object]) -> str:
    """The drill's report into the store, encrypted where the backups are."""
    with tempfile.TemporaryDirectory(dir=s.work_dir) as work:
        path = Path(work) / f"{report['drill']}.drill.json"
        path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        path = encrypt(s, path)
        store(s, "copyto", str(path), f"{s.remote}/drills/{path.name}", what="writing the drill")
        return f"drills/{path.name}"


# --- the outcome ----------------------------------------------------------------------------------


def outcome_sql(name: str, at: datetime, step: str | None) -> str:
    """The statement that records one run's outcome for every tenant. Every value is the
    program's own — a name of its form, a time, a token of `STEPS` — and is checked again here,
    so nothing from outside reaches the statement."""
    if NAME.match(f"{name}.json") is None:
        raise BackupError(f"{name!r} is not a backup's name")
    if step is not None and step not in STEPS:
        raise BackupError(f"{step!r} is not a step of the backup")
    outcome = "'ok'" if step is None else "'failed'"
    reason = "NULL" if step is None else f"'{step}'"
    when = at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    # Every value was checked against the program's own forms above; none comes from outside.
    return (
        "INSERT INTO backup_outcome (tenant, name, at, outcome, reason) "  # noqa: S608
        f"SELECT id, '{name}', '{when}'::timestamptz, {outcome}, {reason} FROM tenant "
        "ON CONFLICT DO NOTHING"
    )


def record_outcome(
    database_url: str,
    database_env: Mapping[str, str],
    *,
    name: str,
    at: datetime,
    step: str | None,
) -> bool:
    """Record the run's outcome; True when it was. A failure is printed and goes no further:
    the backup is what it is whether or not the instance hears of it (ADR-0106)."""
    command = ["psql", "--no-psqlrc", "--tuples-only", "--no-align", "--dbname", database_url]
    try:
        run(
            [*command, "-c", outcome_sql(name, at, step)],
            env={**database_env, "PGCONNECT_TIMEOUT": RECORD_SECONDS},
            what="recording the outcome",
        )
    except BackupError as error:
        print(f"backup: the outcome of {name} was not recorded: {error}", file=sys.stderr)
        return False
    print(f"recorded {name}: {'ok' if step is None else f'failed at {step}'}")
    return True


def database_of(env: Mapping[str, str]) -> tuple[str, Mapping[str, str]] | None:
    """The database to record a failure in, when its URL can be read at all."""
    try:
        return without_password(read_secret(env, "TAKTUS_DATABASE_URL_FILE"))
    except BackupError:
        return None


COMMANDS = ("backup", "list", "archive-wal", "fetch-wal", "drill")


def moment(value: str) -> datetime | str:
    """`latest`, or a moment with its offset; a moment without one is refused rather than read
    in some time zone."""
    if value == "latest":
        return value
    try:
        at = datetime.fromisoformat(value)
    except ValueError:
        raise BackupError(f"--to {value!r} is neither latest nor a moment") from None
    if at.tzinfo is None:
        raise BackupError(f"--to {value!r} names no offset; write it as 2026-10-31T12:00:00Z")
    return at


def run_drill(environment: Mapping[str, str], args: Sequence[str], now: datetime) -> int:
    parser = argparse.ArgumentParser(prog="taktus-backup drill", exit_on_error=False)
    parser.add_argument("--backup", default=None, help="the backup's name, taktus-<time>")
    parser.add_argument("--to", default=None, help="a moment with its offset, or latest")
    parser.add_argument("--heads", default=None, help="the heads noted at the moment, as JSON")
    try:
        options = parser.parse_args(list(args))
    except (argparse.ArgumentError, SystemExit):
        raise BackupError("drill takes --backup NAME, --to MOMENT|latest, --heads FILE") from None
    s = settings(environment, database=False)
    to = None if options.to is None else moment(options.to)
    heads = None if options.heads is None else Path(options.heads)
    report = drill(s, environment, now=now, chosen=options.backup, to=to, heads=heads)
    where = write_report(s, report)
    drills = expired(listed(s, "drills"), now=now, retention_days=s.retention_days, pattern=DRILL)
    for name in drills:
        store(s, "deletefile", f"{s.remote}/drills/{name}", what=f"deleting drills/{name}")
    print(
        f"drill {report['drill']}: {report['outcome']}, backup {report['backup']}, "
        f"{report['mode']}, {len(tenants_of(report))} tenant(s), "
        f"{report['restore_seconds']} s; report {where}"
    )
    for failure in as_list(report["failures"]):
        print(f"drill: {failure}", file=sys.stderr)
    return 0 if report["outcome"] == "ok" else 1


def main(argv: Sequence[str] | None = None, env: Mapping[str, str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    command = args[0] if args else "backup"
    environment = os.environ if env is None else env
    now = datetime.now(UTC)
    try:
        if command not in COMMANDS:
            raise BackupError(f"unknown command {command!r}: one of {', '.join(COMMANDS)}")
        if command == "archive-wal":
            if len(args) != 3:
                raise BackupError("archive-wal takes the path and the file name: %p %f")
            archive_wal(
                settings(environment, database=False), Path(args[1]), args[2], data_dir=Path.cwd()
            )
            return 0
        if command == "fetch-wal":
            if len(args) != 4:
                raise BackupError("fetch-wal takes the cluster, the file name and the path")
            fetch_wal(settings(environment, database=False), args[1], args[2], Path(args[3]))
            return 0
        if command == "drill":
            return run_drill(environment, args[1:], now)
        s = settings(environment)
        if command == "list":
            for name in sorted(listing(s)):
                print(name)
            return 0
        backup(s, now=now)
        keep_retention(s, now=now)
    except BackupError as error:
        print(f"backup: {error}", file=sys.stderr)
        database = database_of(environment) if command == "backup" else None
        if database is not None:
            record_outcome(*database, name=name_at(now), at=now, step=error.step)
        return 1
    record_outcome(s.database_url, s.database_env, name=name_at(now), at=now, step=None)
    return 0


if __name__ == "__main__":
    sys.exit(main())
