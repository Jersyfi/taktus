# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
"""Reserve the number of a record of the register before it is written (DEC-0189 rule 6).

Runs as `make reserve KIND=DEC|NTC|NEED` (the next free number) or `make reserve ID=NTC-0207`
(exactly that number, when it is free). Standard library and git only.

A number of the register, `DEC-NNNN`, `NTC-NNNN` or `NEED-NNNN`, is reserved by creating the
ref `refs/register/<PREFIX>-<NNNN>` on the remote. Creating a ref is atomic on the host: of two
sessions that try the same number at the same moment, exactly one creates it, and the other
moves on to the next. Each reservation points at a commit of its own, a child of the remote's
`main` with the number and a random nonce in its message, so that a second push to the same
ref is never a no-op that looks like success; the reservation is the caller's only when the
remote's ref names that commit afterwards.

The next free number is one above the highest that is held anywhere: by a record on any branch
the remote has (a branch from before this tool had no reservation), by a record in the working
tree, or by a reservation. A number is never reused; a reservation that was never written
leaves a gap, and a gap means nothing.

`tools/check_decisions.py --base` fails a record a branch adds whose number is not reserved, so
that a number taken by hand is caught before it collides.

The last line is the identifier reserved, so that a script can take it with `tail -n 1`.
"""

from __future__ import annotations

import argparse
import os
import re
import secrets
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGISTER = "docs/decisions"
PREFIXES = ("DEC", "NTC", "NEED")
NAMESPACE = "refs/register/"
IDENTIFIER = re.compile(r"^(DEC|NTC|NEED)-(\d{4})$")
RECORD = re.compile(r"\b(DEC|NTC|NEED)-(\d{4})-[a-z0-9-]+\.md$")
ATTEMPTS = 50
IDENTITY = {
    "GIT_AUTHOR_NAME": "Taktus register",
    "GIT_AUTHOR_EMAIL": "register@taktus.invalid",
    "GIT_COMMITTER_NAME": "Taktus register",
    "GIT_COMMITTER_EMAIL": "register@taktus.invalid",
}
"""The reservation commit's identity: it is nobody's work, and no configuration is needed."""


class ReservationError(RuntimeError):
    """A number could not be reserved, with the reason."""


def git(*args: str, cwd: Path = ROOT, check: bool = True) -> subprocess.CompletedProcess[str]:
    # A fixed executable and arguments assembled here from validated identifiers: nothing
    # untrusted reaches the command line.
    result = subprocess.run(  # noqa: S603
        ["git", *args],  # noqa: S607
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, **IDENTITY},
    )
    if check and result.returncode != 0:
        raise ReservationError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result


def reservations(remote: str = "origin", cwd: Path = ROOT) -> dict[str, str]:
    """Every reservation on the remote: identifier to the commit its ref names."""
    listed = git("ls-remote", remote, f"{NAMESPACE}*", cwd=cwd).stdout
    found: dict[str, str] = {}
    for line in listed.splitlines():
        sha, _, ref = line.partition("\t")
        name = ref.removeprefix(NAMESPACE)
        if ref.startswith(NAMESPACE) and IDENTIFIER.match(name):
            found[name] = sha
    return found


def held(prefix: str, remote: str = "origin", cwd: Path = ROOT) -> set[int]:
    """Every number of `prefix` some record or reservation holds."""
    numbers: set[int] = set()
    names: list[str] = []
    branches = git(
        "for-each-ref", "--format=%(refname)", f"refs/remotes/{remote}/", cwd=cwd
    ).stdout.split()
    for branch in branches:
        listed = git("ls-tree", "-r", "--name-only", branch, "--", REGISTER, cwd=cwd, check=False)
        names.extend(listed.stdout.splitlines())
    register = cwd / REGISTER
    if register.is_dir():
        names.extend(str(path) for path in register.rglob("*.md"))
    for name in names:
        if (match := RECORD.search(name)) and match.group(1) == prefix:
            numbers.add(int(match.group(2)))
    for identifier in reservations(remote, cwd):
        found = IDENTIFIER.match(identifier)
        if found and found.group(1) == prefix:
            numbers.add(int(found.group(2)))
    return numbers


def on_main(remote: str = "origin", cwd: Path = ROOT) -> set[str]:
    """The identifiers of the records the remote's `main` holds."""
    listed = git(
        "ls-tree", "-r", "--name-only", f"refs/remotes/{remote}/main", "--", REGISTER, cwd=cwd
    ).stdout
    return {
        f"{match.group(1)}-{match.group(2)}"
        for name in listed.splitlines()
        if (match := RECORD.search(name))
    }


def claim(identifier: str, remote: str, cwd: Path) -> bool:
    """Try to create the reservation; True when it is the caller's."""
    base = git("rev-parse", "--verify", f"refs/remotes/{remote}/main^{{commit}}", cwd=cwd)
    parent = base.stdout.strip()
    tree = git("rev-parse", f"{parent}^{{tree}}", cwd=cwd).stdout.strip()
    message = f"reserve {identifier}\n\nnonce {secrets.token_hex(16)}\n"
    commit = git("commit-tree", tree, "-p", parent, "-m", message, cwd=cwd).stdout.strip()
    ref = f"{NAMESPACE}{identifier}"
    pushed = git("push", "--quiet", remote, f"{commit}:{ref}", cwd=cwd, check=False)
    if pushed.returncode != 0 and "rejected" not in pushed.stderr and "exists" not in pushed.stderr:
        raise ReservationError(f"pushing {ref} to {remote} failed: {pushed.stderr.strip()}")
    return reservations(remote, cwd).get(identifier) == commit


def reserve(
    prefix: str | None = None,
    identifier: str | None = None,
    *,
    remote: str = "origin",
    cwd: Path = ROOT,
    fetch: bool = True,
) -> str:
    """Reserve `identifier` exactly, or the next free number of `prefix`; the identifier."""
    if fetch:
        git("fetch", "--quiet", remote, cwd=cwd)
    if identifier is not None:
        if IDENTIFIER.match(identifier) is None:
            raise ReservationError(f"{identifier!r} is not DEC-NNNN, NTC-NNNN or NEED-NNNN")
        if identifier in on_main(remote, cwd):
            raise ReservationError(f"{identifier} is a record on {remote}/main already")
        if claim(identifier, remote, cwd):
            return identifier
        raise ReservationError(
            f"{identifier} is reserved already; `make reserve KIND={identifier.split('-')[0]}` "
            "gives the next free number"
        )
    if prefix not in PREFIXES:
        raise ReservationError(f"the kind is one of {', '.join(PREFIXES)}, not {prefix!r}")
    number = max(held(prefix, remote, cwd), default=0) + 1
    for _ in range(ATTEMPTS):
        candidate = f"{prefix}-{number:04d}"
        if claim(candidate, remote, cwd):
            return candidate
        number += 1
    raise ReservationError(f"no {prefix} number reserved after {ATTEMPTS} attempts")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    which = parser.add_mutually_exclusive_group(required=True)
    which.add_argument("--kind", choices=PREFIXES, help="reserve the next free number")
    which.add_argument("--id", dest="identifier", help="reserve exactly this number, if free")
    parser.add_argument("--remote", default="origin", help="the remote to reserve on")
    args = parser.parse_args(argv)
    try:
        reserved = reserve(args.kind, args.identifier, remote=args.remote)
    except ReservationError as error:
        print(f"not reserved: {error}", file=sys.stderr)
        return 1
    print(f"reserved on {args.remote} as {NAMESPACE}{reserved}; write the record under it")
    print(reserved)
    return 0


if __name__ == "__main__":
    sys.exit(main())
