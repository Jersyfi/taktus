"""P-03 Implementation started by an event, end to end (DEC-0037, issue #77), against PostgreSQL.

An issue handed to Taktus — labelled `to-taktus` (DEC-0197) — starts P-03 through its own trigger,
without a person and without the input `closing_section`: the daemon's automation role reacts
to the event, its runner executes the run. The coding worker implements the issue in a clone,
and after its change runs the repository's generator in its workspace — the command the bundle
names under `after` — and the run appends what it printed. What is proven: the section the pull
request ends with is byte for byte what `tools/check_status.py --print` prints on the branch the
pull request carries, read back from the repository hosting service, and the description check
passes on that branch.

What is real: the daemon with every role, the run engine, the reference connector, the coding
worker. What is faked: the repository hosting service and the coding agent, as in
`test_dev_orchestration.py`; the intake's part — the delivery kept with its outbox entry — is
written here directly, as in `test_event_reactions.py`.
"""

from __future__ import annotations

import base64
import os
import subprocess
import sys
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml
from fakes.maturity import configurations, verified

from taktus.adapters.driven.postgres import PostgresOutbox, PostgresRepository
from taktus.components.catalog.domain.model import AdapterMaturity
from taktus.components.command.domain.model import IntakeEvent
from taktus.components.run.domain.model import RunState, StepState
from taktus.composition.daemon import Wired
from taktus.composition.reactions import run_id_of
from taktus.ports.connector import idempotency_key
from taktus.ports.outbox import INTAKE_ACCEPTED

from .test_dev_orchestration import BLUEPRINT, REPOSITORY, Outside, backlog, hand, outside
from .test_event_reactions import ACCOUNT, linked
from .test_time_triggers import (
    Daemon,
    ManualClock,
    daemons,
    eventually,
    registered,
    runs_of,
    tenant,
)

__all__ = ["daemons", "outside", "tenant"]  # the fixtures, used by name

GIT = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@localhost",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@localhost",
}
GENERATOR = "tools/check_status.py"
# A record the register holds open on `main`, so that the generated section lists something.
OPEN_RECORD = (
    "docs/decisions/open/DEC-0998-a-question-for-the-test.md",
    "# DEC-0998 — A question for the test\n\n**Category:** NON-BLOCKING\n"
    "**Needed by:** 2026-11-01\n**Issue:** [#5](https://repo.example/issues/5)\n",
)


def on_both_sides(outside: Outside, path: str, content: str) -> None:
    """Put a file on `main` of the hosting service, which the branch is made from, and of the
    clone the worker works in: the two are one repository."""
    outside.commit_on_main({path: content})
    origin = Path(outside.clone_url)
    (origin / path).parent.mkdir(parents=True, exist_ok=True)
    (origin / path).write_text(content, encoding="utf-8")
    for command in (["git", "add", "-A"], ["git", "commit", "--quiet", "-m", path]):
        subprocess.run(  # noqa: S603 — git with fixed arguments in the test's own repository
            command, cwd=origin, env={**os.environ, **GIT}, check=True, capture_output=True
        )


def the_bundle(outside: Outside) -> dict[str, Any]:
    """P-03 as shipped, its trigger pointing at the fake's clone instead of the repository's."""
    with (BLUEPRINT / "P-03-implementation.yaml").open(encoding="utf-8") as handle:
        document: dict[str, Any] = yaml.safe_load(handle)
    (trigger,) = document["triggers"]
    assert trigger["event"] == "issue.labelled" and trigger["filter"] == {"label": "to-taktus"}
    assert "closing_section" not in trigger["inputs"], "a trigger cannot give it"
    trigger["inputs"]["repository_url"] = outside.clone_url
    trigger["inputs"]["repository_host"] = "localhost"
    return document


async def verified_adapters(wired: Wired, tenant: str, outside: Outside) -> None:
    """P-03 runs at level 4: its integrations must be verified under what they declare now."""
    declared = await configurations(
        workers={"worker.endpoint": outside.worker_url},
        connectors={"connector.channel.repo": outside.connector_url},
    )
    async with wired.work.transaction(tenant):
        for configuration in declared:
            await PostgresRepository(wired.persistence, AdapterMaturity).put(
                tenant, verified(configuration, tenant, datetime.now(UTC))
            )


async def handed_over(wired: Wired, tenant: str, issue: int, at: datetime) -> None:
    """What the intake keeps for the label `to-taktus` added to the issue, with its outbox entry."""
    event = IntakeEvent(
        id=f"dlv_taktus_{issue}",
        tenant=tenant,
        channel="channel.repo",
        event="issue.labelled",
        sender_account=ACCOUNT,
        sender_kind="person",
        intent="to-taktus",
        context={"repository": REPOSITORY, "issue": str(issue), "label": "to-taktus"},
        reply_channel="channel.repo",
        reply_address=f"{REPOSITORY}#{issue}",
        occurred_at=at,
        received_at=at,
    )
    async with wired.work.transaction(tenant):
        await PostgresRepository(wired.persistence, IntakeEvent).put(tenant, event)
        await PostgresOutbox(wired.persistence).write(
            tenant, INTAKE_ACCEPTED, {"event_id": event.id}
        )


def checkout(outside: Outside, branch: str, into: Path) -> None:
    """The branch's tree, file by file, as the hosting service holds it."""
    ref = outside.get(f"/repos/{REPOSITORY}/git/ref/heads/{branch}")
    assert isinstance(ref, dict)
    commit = outside.get(f"/repos/{REPOSITORY}/git/commits/{ref['object']['sha']}")
    assert isinstance(commit, dict)
    tree = outside.get(f"/repos/{REPOSITORY}/git/trees/{commit['tree']['sha']}")
    assert isinstance(tree, dict)
    for entry in tree["tree"]:
        file = outside.get(f"/repos/{REPOSITORY}/contents/{entry['path']}?ref={branch}")
        assert isinstance(file, dict)
        (into / entry["path"]).parent.mkdir(parents=True, exist_ok=True)
        (into / entry["path"]).write_bytes(base64.b64decode(file["content"]))


DESCRIPTION_CHECK = """
import sys
sys.path.insert(0, "tools")
import check_status
report = check_status.Report()
expected = check_status.generated(check_status.open_records())
check_status.check_pull_request(open(sys.argv[1], encoding="utf-8").read(), expected, report)
sys.exit(1 if report.failures else 0)
"""


def generated_on(tree: Path) -> str:
    """What the repository's generator prints in a tree."""
    return subprocess.run(  # noqa: S603 — the repository's own tool, fixed arguments
        [sys.executable, GENERATOR, "--print"], cwd=tree, capture_output=True, check=True
    ).stdout.decode("utf-8")


def description_check(tree: Path, body: Path) -> subprocess.CompletedProcess[str]:
    """The description check of `tools/check_status.py`, run on a tree for a description."""
    return subprocess.run(  # noqa: S603 — the repository's own tool, fixed arguments
        [sys.executable, "-c", DESCRIPTION_CHECK, str(body)],
        cwd=tree,
        capture_output=True,
        text=True,
        check=False,
    )


async def test_an_issue_handed_over_becomes_a_pull_request_that_ends_with_the_branchs_section(
    daemons: Callable[..., Daemon], tenant: str, outside: Outside, tmp_path: Path
) -> None:
    tasks = backlog(outside)
    # The clone carries the generator already (the fixture); `main` of the service gains it.
    generator = (Path(outside.clone_url) / GENERATOR).read_text(encoding="utf-8")
    outside.commit_on_main({GENERATOR: generator})
    on_both_sides(outside, *OPEN_RECORD)
    clock = ManualClock(datetime.now(UTC))
    daemon = await daemons(
        "all",
        clock,
        TAKTUS_WORKER=outside.worker_url,
        TAKTUS_CONNECTORS=f"channel.repo={outside.connector_url}",
    ).start()
    assert daemon.wired is not None
    wired = daemon.wired
    await linked(wired, tenant)
    await verified_adapters(wired, tenant, outside)
    version = await registered(wired, tenant, the_bundle(outside))
    assert version.ref == "p03-implementation@11"

    clock.current += timedelta(minutes=1)
    hand(outside, tasks.ready)
    await handed_over(wired, tenant, tasks.ready, clock.now())

    async def ended() -> bool:
        runs = await runs_of(wired, tenant, version.ref)
        return len(runs) == 1 and runs[0].state in (RunState.FINISHED, RunState.ESCALATED)

    await eventually(ended, seconds=180)
    (run,) = await runs_of(wired, tenant, version.ref)
    assert run.state is RunState.FINISHED, run
    assert "closing_section" not in run.inputs and run.inputs["issue"] == tasks.ready
    async with wired.work.transaction(tenant):
        entries = await wired.ledger.entries(tenant, run.id)
        assert (await wired.ledger.verify(tenant)).intact
    assert [e.kind for e in entries][:2] == ["run.created", "run.triggered"]
    assert entries[1].outcome == "event"
    comments = outside.get(f"/repos/{REPOSITORY}/issues/{tasks.ready}/comments")
    assert isinstance(comments, list) and len(comments) == 1
    assert str(comments[0]["body"]).startswith(f"Taktus took this issue: run `{run.id}` of ")

    pulls = outside.get(f"/repos/{REPOSITORY}/pulls")
    assert isinstance(pulls, list) and len(pulls) == 1
    body = str(pulls[0]["body"])
    branch = f"taktus/issue-{tasks.ready}"
    assert pulls[0]["head"]["ref"] == branch

    # What the repository's generator prints on the branch the pull request carries.
    tree = tmp_path / "branch"
    checkout(outside, branch, tree)
    assert (tree / OPEN_RECORD[0]).is_file() and (tree / "hello.txt").is_file()
    printed = generated_on(tree)
    assert "DEC-0998" in printed
    closing = "## Needed from the owner\n\n" + printed
    described = body.split("<!-- taktus-idempotency-key")[0]
    assert described.endswith(closing + "\n"), described[-600:]
    assert described.index("Wrote notes/plan.md") < described.index(closing)

    # The description check of the repository passes on that branch.
    (tmp_path / "body.md").write_text(body, encoding="utf-8")
    checked = description_check(tree, tmp_path / "body.md")
    assert checked.returncode == 0, checked.stdout + checked.stderr


def branch_of_run(outside: Outside, branch: str, key: str) -> str:
    """A branch whose head commit carries `key` as its trailer, as `create-branch` writes it:
    what a run finds when what it would write is already its own. Returns the head's sha."""
    repo = f"/repos/{REPOSITORY}"
    main = outside.get(f"{repo}/git/ref/heads/main")
    assert isinstance(main, dict)
    head = outside.get(f"{repo}/git/commits/{main['object']['sha']}")
    assert isinstance(head, dict)
    commit = outside.send(
        "POST",
        f"{repo}/git/commits",
        {
            "message": f"Write a greeting\n\nTaktus-Idempotency-Key: {key}\n",
            "tree": head["tree"]["sha"],
            "parents": [main["object"]["sha"]],
        },
    )
    outside.send("POST", f"{repo}/git/refs", {"ref": f"refs/heads/{branch}", "sha": commit["sha"]})
    return str(commit["sha"])


async def test_a_branch_that_is_the_runs_own_lets_the_run_go_on_and_is_replayed(
    daemons: Callable[..., Daemon], tenant: str, outside: Outside
) -> None:
    """ADR-0099: the branch read before the coding step is free when its head carries the key
    `create-branch` will write under: the run's own, as a run that started again under the
    same identifier finds it. The run implements, and `create-branch` replays the branch instead
    of ending in `conflict`. The run's identifier is derived from the delivery (ADR-0048 §4), so
    the branch can be made before the run starts."""
    tasks = backlog(outside)
    generator = (Path(outside.clone_url) / GENERATOR).read_text(encoding="utf-8")
    outside.commit_on_main({GENERATOR: generator})
    clock = ManualClock(datetime.now(UTC))
    daemon = await daemons(
        "all",
        clock,
        TAKTUS_WORKER=outside.worker_url,
        TAKTUS_CONNECTORS=f"channel.repo={outside.connector_url}",
    ).start()
    assert daemon.wired is not None
    wired = daemon.wired
    await linked(wired, tenant)
    await verified_adapters(wired, tenant, outside)
    version = await registered(wired, tenant, the_bundle(outside))

    run_id = run_id_of(tenant, "p03-implementation", f"dlv_taktus_{tasks.ready}")
    branch = f"taktus/issue-{tasks.ready}"
    sha = branch_of_run(outside, branch, idempotency_key(run_id, "create-branch", 1))

    clock.current += timedelta(minutes=1)
    hand(outside, tasks.ready)
    await handed_over(wired, tenant, tasks.ready, clock.now())

    async def ended() -> bool:
        runs = await runs_of(wired, tenant, version.ref)
        return len(runs) == 1 and runs[0].state in (RunState.FINISHED, RunState.ESCALATED)

    await eventually(ended, seconds=180)
    (run,) = await runs_of(wired, tenant, version.ref)
    assert run.id == run_id
    assert run.state is RunState.FINISHED, run
    assert run.step_run("read-branch").state is StepState.SUCCEEDED
    assert run.step_run("implement").state is StepState.SUCCEEDED
    async with wired.work.transaction(tenant):
        entries = await wired.ledger.entries(tenant, run.id)
    (made,) = [e for e in entries if e.kind == "egress.write" and e.refs.step_id == "create-branch"]
    assert made.outcome == "replayed", made
    ref = outside.get(f"/repos/{REPOSITORY}/git/ref/heads/{branch}")
    assert isinstance(ref, dict) and ref["object"]["sha"] == sha, "the branch was not rewritten"
