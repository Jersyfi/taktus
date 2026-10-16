# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
"""Replay merged pull requests without their catch-up merges, and print what would conflict.

    tools/replay_merges.py SINCE

For each pull request squash-merged into `origin/main` after the commit SINCE: take its branch
head before its first merge of `main` (a catch-up), merge that head with `git merge-tree` onto
`main` as it stood right before the squash, and print the files that conflict. This is the
replay of `docs/research/2026-10-13-ci-review.md` §2; #392 reran it to see whether the shared
files still conflict. Run from a clone that has every pull request's commits:
`git fetch origin '+refs/pull/*/head:refs/remotes/pull/*'`, and with `gh` signed in.
"""

from __future__ import annotations

import json
import subprocess
import sys


def run(*command: str) -> subprocess.CompletedProcess[str]:
    # Fixed executables with arguments assembled here and commit names from git itself.
    return subprocess.run(command, capture_output=True, text=True, check=False)  # noqa: S603


def head_before_catch_up(number: str) -> tuple[str | None, bool]:
    """The pull request's last commit before its first merge commit, and whether it has one."""
    commits = json.loads(run("gh", "pr", "view", number, "--json", "commits").stdout)["commits"]
    head = None
    for commit in commits:
        parents = run("git", "rev-list", "--parents", "-n", "1", commit["oid"]).stdout.split()
        if len(parents) > 2:
            return head, True
        head = commit["oid"]
    return head, False


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: replay_merges.py SINCE", file=sys.stderr)
        return 2
    since = argv[0]
    log = run("git", "log", "--first-parent", "--format=%H %s", f"{since}..origin/main").stdout
    for line in reversed(log.splitlines()):
        sha, subject = line.split(" ", 1)
        if "(#" not in subject or not subject.endswith(")"):
            continue
        number = subject.rsplit("(#", 1)[1].rstrip(")")
        head, caught_up = head_before_catch_up(number)
        if head is None:
            continue
        merged = run(
            "git", "merge-tree", "--write-tree", "--name-only", "--no-messages", f"{sha}^", head
        )  # fmt: skip
        lines = merged.stdout.splitlines()[1:]
        conflicts = [path for path in lines if path.strip()] if merged.returncode == 1 else []
        print(
            f"#{number}\tcatch-up={'yes' if caught_up else 'no'}"
            f"\tconflicts={','.join(conflicts) or '-'}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
