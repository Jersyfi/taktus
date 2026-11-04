#!/usr/bin/env python3
"""The secret files of a one-server install, filled from a secret store the operator chooses
(ADR-0187, deploy/docker/README.md).

Taktus reads every secret from a file. This program reads the operator's `secret-store.json`
beside it and writes each file it names under `secrets/` from the store:

    {"command": ["store-cli", "read", "{reference}"],
     "secrets": [{"file": "payments_token", "reference": "vault/payments/token"}]}

`command` is the store's own command-line tool, run without a shell, `{reference}` replaced in
its arguments by each secret's reference. What it prints, without the final line break, is the
value. A file is written only when its value changed, and in place, so that a container whose
compose secret is that file reads the new value at its next read. A command that fails, times
out or prints nothing leaves its file as it was. No value is ever printed or logged: a line names
the file and what happened to it.

Without `secret-store.json` nothing is done, and the files stay what the operator wrote.
`--interval SECONDS` repeats the pass until stopped, so that a rotation in the store reaches the
files without a person. Standard library only. Exit code 0 when every secret was read or nothing
is configured, 1 when one could not be read, 2 when the configuration is refused.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
CONFIGURATION = HERE / "secret-store.json"
DIRECTORY = HERE / "secrets"
PLACEHOLDER = "{reference}"
FILE = re.compile(r"^[a-z0-9][a-z0-9_.-]*$")
TIMEOUT = 30.0
"""Seconds one read of the store may take."""


class Refused(ValueError):
    """The configuration cannot be used as it is."""


@dataclass(frozen=True)
class Secret:
    file: str
    reference: str


@dataclass(frozen=True)
class Store:
    command: tuple[str, ...]
    secrets: tuple[Secret, ...]

    def argv(self, secret: Secret) -> list[str]:
        return [part.replace(PLACEHOLDER, secret.reference) for part in self.command]


def load(document: Any) -> Store:
    """The store as configured, or `Refused` naming every fault at once."""
    faults: list[str] = []
    if not isinstance(document, dict):
        raise Refused("the configuration is not an object")
    unknown = sorted(set(document) - {"command", "secrets"})
    if unknown:
        faults.append(f"unknown keys: {', '.join(unknown)}")
    command = document.get("command")
    if (
        not isinstance(command, list)
        or not command
        or not all(isinstance(part, str) and part for part in command)
    ):
        faults.append("`command` is a list of the command's arguments, none empty")
        command = []
    elif not any(PLACEHOLDER in part for part in command):
        faults.append(f"`command` names no {PLACEHOLDER}: every secret would read the same")
    entries = document.get("secrets")
    secrets: list[Secret] = []
    if not isinstance(entries, list) or not entries:
        faults.append("`secrets` lists at least one secret")
        entries = []
    seen: set[str] = set()
    for index, entry in enumerate(entries):
        where = f"secrets[{index}]"
        if not isinstance(entry, dict) or set(entry) != {"file", "reference"}:
            faults.append(f"{where}: an object of `file` and `reference`, nothing else")
            continue
        file, reference = entry["file"], entry["reference"]
        if not isinstance(file, str) or not FILE.match(file):
            faults.append(f"{where}: `file` is a file name under secrets/, no path")
            continue
        if not isinstance(reference, str) or not reference.strip():
            faults.append(f"{where}: `reference` names the value in the store")
            continue
        if file in seen:
            faults.append(f"{where}: the file {file!r} is named twice")
            continue
        seen.add(file)
        secrets.append(Secret(file, reference))
    if faults:
        raise Refused("; ".join(faults))
    return Store(tuple(command), tuple(secrets))


def read(store: Store, secret: Secret, timeout: float = TIMEOUT) -> str | None:
    """The value the store prints for the secret, or None. Nothing of the output is kept."""
    try:
        completed = subprocess.run(  # noqa: S603 — the operator's command, no shell
            store.argv(secret),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    value = completed.stdout
    if value.endswith("\n"):
        value = value[:-1]
        if value.endswith("\r"):
            value = value[:-1]
    return value or None


def write(path: Path, value: str) -> bool:
    """Write `value` into `path` in place when it differs; True when it was written. In place:
    a file mounted into a container keeps its inode, and the container sees the new value."""
    data = value + "\n"
    if path.exists() and path.read_text(encoding="utf-8") == data:
        return False
    if path.exists():
        with path.open("r+", encoding="utf-8") as handle:
            handle.write(data)
            handle.truncate()
    else:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(data)
    # Readable by the containers' own user, as secrets.sh leaves its files; the directory is
    # closed to every other host user.
    path.chmod(0o644)
    return True


def sync(store: Store, directory: Path, log: Any = print) -> bool:
    """One pass over every secret. True when every one was read."""
    directory.mkdir(parents=True, exist_ok=True)
    directory.chmod(0o700)
    complete = True
    for secret in store.secrets:
        value = read(store, secret)
        if value is None:
            complete = False
            log(f"secret store: {secret.file}: not read; the file is left as it was")
            continue
        if write(directory / secret.file, value):
            log(f"secret store: {secret.file}: written")
    return complete


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--config", type=Path, default=CONFIGURATION)
    parser.add_argument("--directory", type=Path, default=DIRECTORY)
    parser.add_argument(
        "--interval", type=float, help="seconds between passes; one pass without it"
    )
    args = parser.parse_args(argv)
    if not args.config.exists():
        return 0
    try:
        store = load(json.loads(args.config.read_text(encoding="utf-8")))
    except (ValueError, OSError) as error:
        print(f"secret store: refused: {error}", file=sys.stderr)
        return 2
    while True:
        complete = sync(store, args.directory)
        if args.interval is None:
            return 0 if complete else 1
        time.sleep(max(args.interval, 1.0))


if __name__ == "__main__":
    sys.exit(main())
