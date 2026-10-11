"""The instance's database backup: dump, optionally encrypt, write off the node, keep the retention.

Runs as the backup image's entry point (`deploy/backup/Dockerfile`), started by the chart's
CronJob (`deploy/k8s/chart/templates/backup.yaml`) on its schedule (ADR-0087). Standard library
only; the work is done by three standard tools that a person restoring by hand uses too:
`pg_dump` and `psql` of the database's major version, `age` for encryption, `rclone` for the
store. Nothing here imports Taktus: a backup is taken while Taktus is faulty as well, and is
restored without it (ADR-0013 C, `deploy/k8s/README.md` §11).

One run writes two objects under one name, `taktus-<UTC time>`:

- `<name>.dump` — `pg_dump --format=custom` of the whole database, or `<name>.dump.age` when a
  recipient is configured;
- `<name>.json` — the manifest: when, which object, its SHA-256, whether it is encrypted, the
  schema revision, and every tenant's ledger head (`seq`, `hash`) read before the dump. The
  ledger is append-only, so every head read before the dump is in it; a restore is checked
  against these heads. Encrypted as `<name>.json.age` when the dump is.

Then the retention: every backup whose time is older than the retention is deleted — its dump
and its manifest — and no younger one. The newest backup is never deleted, whatever the
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

Exit code 0: written and the retention kept. 1: nothing was deleted, and the log says why.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

NAME = re.compile(r"^taktus-(\d{8}T\d{6}Z)\.(dump|json)(\.age)?$")
TIME = "%Y%m%dT%H%M%SZ"
DEFAULT_RETENTION_DAYS = 30

HEADS = (
    "SELECT coalesce(json_object_agg(tenant, json_build_object('seq', seq, 'hash', hash)), '{}') "
    "FROM (SELECT DISTINCT ON (tenant) tenant, seq, hash FROM ledger_entry "
    "ORDER BY tenant, seq DESC) AS head"
)
REVISION = "SELECT coalesce(max(version_num), '') FROM alembic_version"


class BackupError(Exception):
    """A step failed; the message says which, never with a secret in it."""


# --- names and the retention ---------------------------------------------------------------


def name_at(at: datetime) -> str:
    return "taktus-" + at.astimezone(UTC).strftime(TIME)


def time_of(name: str) -> datetime | None:
    """The time a backup object's name carries; None for an object this program did not write."""
    match = NAME.match(name)
    if match is None:
        return None
    return datetime.strptime(match[1], TIME).replace(tzinfo=UTC)


def expired(objects: Iterable[str], *, now: datetime, retention_days: int) -> list[str]:
    """The objects to delete: those of every backup older than the retention, never the newest
    backup's, never an object of another form. Sorted, so that a log reads in order."""
    if retention_days < 0:
        raise BackupError(f"the retention is {retention_days} days; it cannot be negative")
    times = {name: at for name in objects if (at := time_of(name)) is not None}
    if not times:
        return []
    newest = max(times.values())
    limit = now - timedelta(days=retention_days)
    return sorted(name for name, at in times.items() if at < limit and at != newest)


# --- configuration ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Settings:
    database_url: str
    database_env: Mapping[str, str]
    remote: str
    store_env: Mapping[str, str]
    retention_days: int
    recipient: str
    work_dir: Path


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


def settings(env: Mapping[str, str]) -> Settings:
    """Read and check the configuration before anything is done."""
    url, database_env = without_password(read_secret(env, "TAKTUS_DATABASE_URL_FILE"))
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
    return Settings(url, database_env, remote, store_env, int(raw), recipient, work_dir)


# --- the tools -------------------------------------------------------------------------------


def run(command: Sequence[str], *, env: Mapping[str, str] | None = None, what: str) -> str:
    """Run one tool; on failure, raise with its last lines of error output. The command line
    never carries a secret, so it may be named."""
    merged = {**os.environ, **(env or {})}
    done = subprocess.run(command, env=merged, capture_output=True, text=True, check=False)  # noqa: S603
    if done.returncode != 0:
        tail = "\n".join(done.stderr.strip().splitlines()[-5:])
        raise BackupError(f"{what} failed ({done.returncode}): {tail}")
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


# --- one run -----------------------------------------------------------------------------------


def backup(s: Settings, *, now: datetime) -> str:
    """Write one backup; return its name. Nothing is deleted here."""
    name = name_at(now)
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
        manifest = {
            "name": name,
            "created": now.astimezone(UTC).isoformat(),
            "object": dump.name,
            "sha256": sha256(dump),
            "bytes": dump.stat().st_size,
            "encrypted": bool(s.recipient),
            "recipient": s.recipient or None,
            "schema_revision": revision,
            "ledger_heads": heads,
        }
        manifest_path = Path(work) / f"{name}.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", "utf-8")
        manifest_path = encrypt(s, manifest_path)
        for path in (dump, manifest_path):
            store(s, "copyto", str(path), f"{s.remote}/{path.name}", what=f"writing {path.name}")
        written = set(listing(s))
        missing = {dump.name, manifest_path.name} - written
        if missing:
            raise BackupError(f"written but not listed in the store: {sorted(missing)}")
        print(f"backup {name}: {dump.name} ({manifest['bytes']} bytes), {len(heads)} tenant(s)")
    return name


def keep_retention(s: Settings, *, now: datetime) -> list[str]:
    doomed = expired(listing(s), now=now, retention_days=s.retention_days)
    for name in doomed:
        store(s, "deletefile", f"{s.remote}/{name}", what=f"deleting {name}")
        print(f"deleted {name}: older than {s.retention_days} day(s)")
    return doomed


def main(argv: Sequence[str] | None = None, env: Mapping[str, str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    command = args[0] if args else "backup"
    try:
        s = settings(os.environ if env is None else env)
        now = datetime.now(UTC)
        if command == "backup":
            backup(s, now=now)
            keep_retention(s, now=now)
        elif command == "list":
            for name in sorted(listing(s)):
                print(name)
        else:
            raise BackupError(f"unknown command {command!r}: backup or list")
    except BackupError as error:
        print(f"backup: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
