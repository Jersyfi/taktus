"""The two runnable processes of the dev-orchestration blueprint, end to end, with everything
outside Taktus faked and everything inside real.

Both read the backlog's ready standard (docs/process/README.md, issue #70). P-02 Refinement
reads an issue that lacks a section of it, has a model write the missing section and posts it
as a comment; an issue that carries every section it leaves alone. P-03 Implementation admits
only an issue that meets the standard — made from the form `Task`, labelled `ready`, with a
milestone, one priority and nothing open under "Blocked by" — and refuses any other with the
reason; it claims the one it admits with `in-progress`, has the coding worker implement it in
a clone of a repository, puts the worker's change on a branch through the connector, waits for
the pipeline's verdict, opens the pull request and labels it. `taktusctl run` drives both, as
the owner will drive the live run (`tools/first_run.sh`).

What is real: the command line, the run engine, the reference connector (a process, over MCP),
the coding worker (a process, behind the worker contract), the model adapter. What is faked:
the repository hosting service (`tests/fakes/repository_service.py`, a process), the model
endpoint (`tests/fakes/model_service.py`, a thread), the coding agent
(`workers/claudecode/fake_agent.py`, which really writes files). What the fakes hold
afterwards is the proof: one comment with the missing section, the claim on the ready issue,
one branch with the worker's files on one marked commit, one pull request with one label, and
the run's ledger with an egress entry for each write.

`tools/first_run.sh` tells two stops apart from any other failure by what `taktusctl run`
prints: P-02 refusing an issue it has nothing to write for, and P-03 finding the branch an
earlier attempt left. Both patterns are read from the script and held against the real output
here, so that a change of wording fails this test and not a live run (issue #30).
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import secrets
import subprocess
import sys
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest
import yaml
from fakes import model_service
from fakes.identity import added_by_command_line
from fakes.maturity import configurations, write_verified

from taktus.adapters.driven.configuration.environment import EnvironmentConfiguration
from taktus.components.catalog.application.service import REMOVAL_TESTED
from taktus.components.process.application.service.register_version import (
    RegisterProcessVersion,
    parse_bundle,
)
from taktus.components.run.domain.model import (
    ConnectorRule,
    LlmWork,
    RunState,
    WaitWork,
    WorkerWork,
    parse_work,
)
from taktus.composition.local import LocalWiring
from taktus.shared.v1 import Method

from .conftest import ROOT, free_port
from .test_first_slice import PLAIN, taktusctl
from .test_removal_test import TENANT, result_of, run_removal

BLUEPRINT = ROOT / "blueprints" / "dev-orchestration" / "processes"
FAKE_SERVICE = ROOT / "tests" / "fakes" / "repository_service.py"
CODING_WORKER = ROOT / "workers" / "claudecode" / "worker.py"
FAKE_AGENT = ROOT / "workers" / "claudecode" / "fake_agent.py"
FIRST_RUN = ROOT / "tools" / "first_run.sh"
REPOSITORY = "acme/product"
RECORDS = "docs/decisions/open"
# What the fake model answers P-02 with: the one section the issue it refines lacks.
SECTION_ANSWER = "### How it is verified\n\n- the fake answered: {prompt}\n"

# An issue as the form `Task` renders it (.github/ISSUE_TEMPLATE/task.yml).
FORM = """### What must be achieved

A greeting is written to hello.txt.

### How it is verified

{verified}

### Where the boundary lies

No other file changes.

### Component

workers

### Source

docs/roadmap.md, 0.2.0

### Blocked by

{blocked}
"""


@dataclass
class Outside:
    """Everything the two processes reach, and how the command line is told about it."""

    service_url: str
    connector_url: str
    model_url: str
    worker_url: str
    clone_url: str
    token: str

    def environment(self, state_dir: Path) -> dict[str, str]:
        return {
            **os.environ,
            **PLAIN,
            "TAKTUS_STATE_DIR": str(state_dir),
            "TAKTUS_WORKER": self.worker_url,
            "TAKTUS_CONNECTORS": f"channel.repo={self.connector_url}",
            "TAKTUS_MODEL_ENDPOINT": self.model_url,
            "TAKTUS_MODEL_NAME": "fake-model",
        }

    def state(self) -> dict[str, object]:
        result: dict[str, object] = httpx.get(f"{self.service_url}/_fake/state", timeout=5).json()
        return result

    def get(self, path: str) -> object:
        headers = {"Authorization": f"Bearer {self.token}"}
        return httpx.get(f"{self.service_url}{path}", headers=headers, timeout=5).json()

    def send(self, method: str, path: str, body: dict[str, object]) -> dict[str, object]:
        headers = {"Authorization": f"Bearer {self.token}"}
        answer = httpx.request(
            method, f"{self.service_url}{path}", json=body, headers=headers, timeout=5
        )
        answer.raise_for_status()
        result: dict[str, object] = answer.json()
        return result

    def issue(self, title: str, body: str, labels: list[str], milestone: int | None) -> int:
        given: dict[str, object] = {"title": title, "body": body, "labels": labels}
        if milestone is not None:
            given["milestone"] = milestone
        return int(str(self.send("POST", f"/repos/{REPOSITORY}/issues", given)["number"]))

    def labels(self, number: int) -> list[str]:
        issue = self.get(f"/repos/{REPOSITORY}/issues/{number}")
        assert isinstance(issue, dict)
        return sorted(label["name"] for label in issue["labels"])

    def commit_on_main(self, files: dict[str, str]) -> None:
        """Put files on `main` through the service's object interface, as a push would."""
        repo = f"/repos/{REPOSITORY}"
        ref = self.get(f"{repo}/git/ref/heads/main")
        assert isinstance(ref, dict)
        head = self.get(f"{repo}/git/commits/{ref['object']['sha']}")
        assert isinstance(head, dict)
        entries = []
        for path, content in files.items():
            blob = self.send("POST", f"{repo}/git/blobs", {"content": content})
            entries.append({"path": path, "mode": "100644", "type": "blob", "sha": blob["sha"]})
        tree = self.send(
            "POST", f"{repo}/git/trees", {"base_tree": head["tree"]["sha"], "tree": entries}
        )
        commit = self.send(
            "POST",
            f"{repo}/git/commits",
            {"message": "records", "tree": tree["sha"], "parents": [ref["object"]["sha"]]},
        )
        self.send("PATCH", f"{repo}/git/refs/heads/main", {"sha": commit["sha"]})


def wait_ready(process: subprocess.Popen[bytes], url: str, log: Path, what: str) -> None:
    import time

    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"the {what} exited early; see {log.read_text()[-2000:]}")
        try:
            if httpx.get(url, timeout=1.0).status_code == 200:
                return
        except httpx.HTTPError:
            time.sleep(0.1)
    raise RuntimeError(f"the {what} did not become ready; see {log.read_text()[-2000:]}")


@pytest.fixture
def outside(tmp_path: Path) -> Iterator[Outside]:
    started: list[subprocess.Popen[bytes]] = []
    token = "tok-" + secrets.token_hex(12)
    agent_key = "key-" + secrets.token_hex(12)
    try:
        # The repository hosting service, faked, and the reference connector against it.
        service_port = free_port()
        service_log = tmp_path / "service.log"
        with service_log.open("wb") as handle:
            service = subprocess.Popen(  # noqa: S603 — our own script, fixed arguments
                [sys.executable, str(FAKE_SERVICE), "--port", str(service_port)],
                stdout=handle,
                stderr=subprocess.STDOUT,
                env={**os.environ, "FAKE_REPOSITORY_TOKENS": f"{token}:write"},
            )
        started.append(service)
        service_url = f"http://127.0.0.1:{service_port}"
        wait_ready(service, f"{service_url}/_fake/state", service_log, "fake service")

        connector_port = free_port()
        connector_log = tmp_path / "connector.log"
        with connector_log.open("wb") as handle:
            connector = subprocess.Popen(  # noqa: S603 — our own module, fixed arguments
                [
                    sys.executable,
                    "-m",
                    "taktus.adapters.driven.connectors.github",
                    "--port",
                    str(connector_port),
                    "--target",
                    service_url,
                    "--repository",
                    REPOSITORY,
                ],
                stdout=handle,
                stderr=subprocess.STDOUT,
                env={**os.environ, "REPOSITORY_TOKEN": token},
            )
        started.append(connector)
        connector_url = f"http://127.0.0.1:{connector_port}"
        wait_ready(connector, f"{connector_url}/health", connector_log, "connector")

        # The model endpoint, faked, in a thread.
        model, _ = model_service.make_server("127.0.0.1", 0, answer=SECTION_ANSWER)
        threading.Thread(target=model.serve_forever, daemon=True).start()
        model_url = f"http://127.0.0.1:{model.server_address[1]}"

        # A repository for the worker to clone: one commit on main.
        clone = tmp_path / "origin"
        clone.mkdir()
        git_env = {
            **os.environ,
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@localhost",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@localhost",
        }
        for command in (
            ["git", "init", "--quiet", "--initial-branch", "main"],
            ["git", "commit", "--quiet", "--allow-empty", "-m", "first"],
        ):
            subprocess.run(command, cwd=clone, env=git_env, check=True, capture_output=True)  # noqa: S603

        # The coding worker against the fake agent, by endpoint, with its credential in its
        # environment as an endpoint worker's operator would put it.
        worker_port = free_port()
        worker_log = tmp_path / "worker.log"
        with worker_log.open("wb") as handle:
            worker = subprocess.Popen(  # noqa: S603 — our own script, fixed arguments
                [
                    sys.executable,
                    str(CODING_WORKER),
                    "--port",
                    str(worker_port),
                    "--auth",
                    "api-key",
                    "--agent",
                    f"{sys.executable} {FAKE_AGENT}",
                    "--state-dir",
                    str(tmp_path / "worker-state"),
                    "--estimate-steps",
                    "8",
                    "--estimate-currency",
                    "0.5",
                ],
                stdout=handle,
                stderr=subprocess.STDOUT,
                env={**os.environ, "CODING_AGENT_API_KEY": agent_key},
            )
        started.append(worker)
        worker_url = f"http://127.0.0.1:{worker_port}"
        wait_ready(worker, f"{worker_url}/v1/health", worker_log, "coding worker")

        yield Outside(service_url, f"{connector_url}/mcp", model_url, worker_url, str(clone), token)
        model.shutdown()
    finally:
        for process in started:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


VERIFIED = ("worker.endpoint", "model.endpoint", "connector.channel.repo")
"""The integrations the processes run on here. P-01 and P-02 run at level 3, P-03 at 4: a step
on an integration runs only where it is *verified* (ADR-0039). The fakes are recorded so in
the state the runs read, as both halves of a real verification would record them, so that what
is tested is the processes' own logic. A live run needs the real integrations verified."""


def verified(outside: Outside, state_dir: Path) -> None:
    """Write the catalog's maturity records for `VERIFIED` into the state's snapshot, each under
    the configuration the fake declares now: a pass counts only for that (ADR-0044)."""
    if (state_dir / "adaptermaturity.json").exists():
        return
    declared = asyncio.run(
        configurations(
            workers={"worker.endpoint": outside.worker_url},
            connectors={"connector.channel.repo": outside.connector_url},
            models={"model.endpoint": ("fake-model", ("*",))},
        )
    )
    assert {c.adapter for c in declared} == set(VERIFIED)
    write_verified(state_dir, declared, ("default",))


def run_bundle(
    outside: Outside, state_dir: Path, bundle: str, *inputs: str, expect: int = 0
) -> str:
    added_by_command_line(taktusctl(), "idn_test", outside.environment(state_dir))
    verified(outside, state_dir)
    command = [taktusctl(), "run", "--process", str(BLUEPRINT / bundle)]
    for given in inputs:
        command += ["--input", given]
    completed = subprocess.run(  # noqa: S603 — our own entry point
        command,
        capture_output=True,
        text=True,
        env=outside.environment(state_dir),
        check=False,
        timeout=300,
    )
    assert completed.returncode == expect, completed.stdout + completed.stderr
    return completed.stdout


def first_run_pattern(name: str) -> re.Pattern[str]:
    """One of the patterns `tools/first_run.sh` greps the output of `taktusctl run` with."""
    found = re.search(rf'^{name}="(.*)"$', FIRST_RUN.read_text(encoding="utf-8"), re.MULTILINE)
    assert found is not None, f"{name} is not defined in {FIRST_RUN}"
    return re.compile(found.group(1))


def refused(output: str, step: str, reason: str) -> bool:
    """Whether the run stopped at `step`, a rule classed exact, with `reason` in its line."""
    line = re.compile(rf"\b{re.escape(step)}\s+rule\s+exact\s+failed\b.*{re.escape(reason)}")
    return any(line.search(row) for row in output.splitlines())


# What `tools/first_run.sh` generates with `tools/check_status.py --print` and hands to P-03:
# the section a description ends with. Here a fixed text, since the fake has no register.
CLOSING = "## Needed from the owner\n\n<!-- generated -->\nNothing is open.\n<!-- end -->"


@dataclass
class Backlog:
    ready: int
    missing_section: int
    no_milestone: int
    blocked: int


def backlog(outside: Outside) -> Backlog:
    """A backlog in the shape of this repository's: issues made from the form `Task`, a
    milestone, and one open decision record on `main` under the directory of open records."""
    outside.commit_on_main(
        {
            f"{RECORDS}/README.md": "Open records.\n",
            f"{RECORDS}/DEC-0999-an-open-decision.md": "# DEC-0999\n",
        }
    )
    milestone = outside.send("POST", f"/repos/{REPOSITORY}/milestones", {"title": "0.2.0"})
    number = int(str(milestone["number"]))
    labelled = ["task", "ready", "priority:high"]
    complete = FORM.format(verified="hello.txt says hello.", blocked="nothing")
    return Backlog(
        ready=outside.issue("Write a greeting", complete, labelled, number),
        missing_section=outside.issue(
            "Without a verification",
            FORM.format(verified="_No response_", blocked="nothing"),
            labelled,
            number,
        ),
        no_milestone=outside.issue("Without a milestone", complete, labelled, None),
        blocked=outside.issue(
            "Blocked by a decision",
            FORM.format(verified="hello.txt says hello.", blocked="DEC-0999"),
            labelled,
            number,
        ),
    )


def p03_inputs(outside: Outside, issue: int) -> list[str]:
    return [
        f"issue={issue}",
        f"records_path={RECORDS}",
        f"repository_url={outside.clone_url}",
        "repository_host=localhost",
        "coding_credential=CODING_AGENT_API_KEY",
        f"closing_section={CLOSING}",
    ]


def test_refinement_writes_only_the_missing_section(outside: Outside, tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    tasks = backlog(outside)
    p02 = "P-02-refinement.yaml"
    already = first_run_pattern("P02_ALREADY_REFINED")

    # An issue that carries every section is left alone: refused before the model is asked.
    output = run_bundle(outside, state_dir, p02, f"issue={tasks.ready}", expect=3)
    assert refused(output, "missing", "carries every section already"), output
    assert any(already.search(line) for line in output.splitlines()), output
    assert outside.state()[REPOSITORY]["comments"] == 0  # type: ignore[index]

    # An issue missing a section gains exactly that section, as a comment.
    output = run_bundle(outside, state_dir, p02, f"issue={tasks.missing_section}")
    assert "state finished" in output, output
    assert re.search(r"missing\s+rule\s+exact\s+succeeded", output), output
    assert re.search(r"egress\.write\s+write-sections\s+acted", output), output
    assert re.search(r"refine\s+llm\s+sourced\s+succeeded\s+tokens", output), output
    comments = outside.get(f"/repos/{REPOSITORY}/issues/{tasks.missing_section}/comments")
    assert isinstance(comments, list) and len(comments) == 1
    body = comments[0]["body"]
    assert body.startswith("### How it is verified"), body
    assert '["How it is verified"]' in body, "the model was told which section is missing"
    assert "Written by Taktus, process P-02 Refinement" in body
    assert "taktus-idempotency-key" in body, "the mark that makes a repeat findable"
    labels = outside.labels(tasks.missing_section)
    assert labels == ["priority:high", "ready", "task"], "P-02 adds no label"

    # P-02 again on the same issue: its comment is there, so it writes nothing twice.
    output = run_bundle(outside, state_dir, p02, f"issue={tasks.missing_section}", expect=3)
    assert refused(output, "admit", "condition 1 does not hold"), output
    assert any(already.search(line) for line in output.splitlines()), output
    assert outside.state()[REPOSITORY]["comments"] == 1  # type: ignore[index]


def test_implementation_admits_a_ready_issue_claims_it_and_refuses_the_rest(
    outside: Outside, tmp_path: Path
) -> None:
    state_dir = tmp_path / "state"
    tasks = backlog(outside)
    p03 = "P-03-implementation.yaml"

    # Each issue that fails the standard is refused at admission with the reason, and nothing
    # is written: no claim, no branch.
    for number, reason in (
        (tasks.missing_section, "section 'How it is verified' is missing or empty"),
        (tasks.no_milestone, "no milestone"),
        (tasks.blocked, "blocked by DEC-0999, still open"),
    ):
        output = run_bundle(outside, state_dir, p03, *p03_inputs(outside, number), expect=3)
        assert refused(output, "admit", f"issue #{number} is not ready: "), output
        assert refused(output, "admit", reason), output
        assert "in-progress" not in outside.labels(number)
    assert outside.state()[REPOSITORY]["branches"] == 1  # type: ignore[index]

    # The ready one is admitted, claimed, implemented, and becomes a pull request.
    output = run_bundle(outside, state_dir, p03, *p03_inputs(outside, tasks.ready))
    assert "state finished" in output, output
    for step in ("admit", "verify"):
        assert f"{step:<20} rule       exact     succeeded" in output, output
    assert "implement            worker     tolerant  succeeded" in output, output
    assert "wait-for-pipeline    wait       -         succeeded" in output, output
    writes = [
        line.split()[2:4]
        for line in output.splitlines()
        if line.strip().startswith(tuple("0123456789")) and "egress" in line
    ]
    assert writes == [
        ["egress.write", "claim"],
        ["egress.write", "create-branch"],
        ["egress.write", "open-pr"],
        ["egress.write", "label"],
    ], output
    assert outside.labels(tasks.ready) == ["in-progress", "priority:high", "ready", "task"]

    ref = outside.get(f"/repos/{REPOSITORY}/git/ref/heads/taktus/issue-{tasks.ready}")
    assert isinstance(ref, dict)
    commit = outside.get(f"/repos/{REPOSITORY}/git/commits/{ref['object']['sha']}")
    assert isinstance(commit, dict)
    assert "Taktus-Idempotency-Key: taktus:run_" in commit["message"]
    tree = outside.get(f"/repos/{REPOSITORY}/git/trees/{commit['tree']['sha']}")
    assert isinstance(tree, dict)
    paths = sorted(entry["path"] for entry in tree["tree"])
    assert paths == [
        "checked.txt",
        f"{RECORDS}/DEC-0999-an-open-decision.md",
        f"{RECORDS}/README.md",
        "hello.txt",
        "notes/plan.md",
    ], "main's files and the fake agent's"
    pulls = outside.get(f"/repos/{REPOSITORY}/pulls")
    assert isinstance(pulls, list) and len(pulls) == 1
    pull = pulls[0]
    assert pull["head"]["ref"] == f"taktus/issue-{tasks.ready}" and pull["base"]["ref"] == "main"
    assert pull["title"] == f"Write a greeting (#{tasks.ready})"
    assert f"Closes #{tasks.ready}." in pull["body"]
    assert "Opened by Taktus, process P-03" in pull["body"]
    assert "Wrote notes/plan.md" in pull["body"], "the worker's own summary"
    # The generated section closes the description, after the summary and verbatim; the mark
    # that makes a repeat findable is an HTML comment after it, which the check strips.
    body = pull["body"].split("<!-- taktus-idempotency-key")[0].rstrip()
    assert body.endswith(CLOSING), body
    assert body.index("Wrote notes/plan.md") < body.index("## Needed from the owner")
    assert [label["name"] for label in pull["labels"]] == ["taktus"]

    # Every write is in the ledger as egress, and the chain and the provenance verify.
    ledger = json.loads((state_dir / "ledger.json").read_text())["default"]
    egress = [e for e in ledger if e["kind"].startswith("egress.")]
    assert [e["refs"]["step_id"] for e in egress] == ["claim", "create-branch", "open-pr", "label"]
    assert all(e["content_digest"].startswith("sha256:") for e in egress)
    assert "DOES NOT VERIFY" not in output

    # A second run on the same issue finds it claimed and takes nothing up.
    output = run_bundle(outside, state_dir, p03, *p03_inputs(outside, tasks.ready), expect=3)
    assert refused(output, "admit", "claimed: labelled in-progress"), output
    assert outside.state()[REPOSITORY]["pulls"] == 1  # type: ignore[index]


def test_a_branch_left_by_an_earlier_attempt_stops_the_run_in_the_words_first_run_reads(
    outside: Outside, tmp_path: Path
) -> None:
    """A ready issue whose branch `taktus/issue-<n>` already exists without this run's key, as
    an earlier attempt after a defect leaves it: the run ends `conflict` at create-branch,
    opens nothing, and says so in the words `tools/first_run.sh` looks for (issue #30)."""
    state_dir = tmp_path / "state"
    tasks = backlog(outside)
    main = outside.get(f"/repos/{REPOSITORY}/git/ref/heads/main")
    assert isinstance(main, dict)
    outside.send(
        "POST",
        f"/repos/{REPOSITORY}/git/refs",
        {"ref": f"refs/heads/taktus/issue-{tasks.ready}", "sha": main["object"]["sha"]},
    )
    inputs = p03_inputs(outside, tasks.ready)
    output = run_bundle(outside, state_dir, "P-03-implementation.yaml", *inputs, expect=3)
    leftover = first_run_pattern("P03_LEFTOVER_BRANCH")
    assert any(leftover.search(line) for line in output.splitlines()), output
    assert outside.state()[REPOSITORY]["pulls"] == 0  # type: ignore[index]


# --- P-01 Roadmap control (issue #71) ------------------------------------------------------------

ROADMAP = """# Roadmap

### `0.1.0` — first
{first}

**Complete when** it is done.

**Done so far:** the seed (#1) and more (#42).

### `0.2.0` — second
{second}

**Complete when** it is done.
"""


def make_backlog_script() -> object:
    """`tools/backlog.py`, the script behind `make backlog`, loaded by its path."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("backlog_script", ROOT / "tools" / "backlog.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # its dataclass resolves annotations through its module
    spec.loader.exec_module(module)
    return module


def run_p01(outside: Outside, state_dir: Path, report: int) -> tuple[str, str]:
    """P-01 once: what `taktusctl run` printed, and the report it wrote."""
    before = outside.get(f"/repos/{REPOSITORY}/issues/{report}/comments")
    assert isinstance(before, list)
    output = run_bundle(
        outside,
        state_dir,
        "P-01-roadmap-control.yaml",
        "roadmap_path=docs/roadmap.md",
        f"records_path={RECORDS}",
        f"report_issue={report}",
    )
    assert "state finished" in output, output
    for step in ("order", "reconcile"):
        assert re.search(rf"{step}\s+rule\s+exact\s+succeeded", output), output
    writes = [line.split()[2:4] for line in output.splitlines() if "egress." in line]
    assert writes == [["egress.write", "write-report"]], output
    after = outside.get(f"/repos/{REPOSITORY}/issues/{report}/comments")
    assert isinstance(after, list) and len(after) == len(before) + 1
    return output, str(after[-1]["body"])


def section(report: str, heading: str) -> list[str]:
    """The lines of one section of the report, up to the next heading or the footer."""
    part = report.split(f"### {heading}\n", 1)[1]
    part = re.split(r"^(?:### |---$)", part, maxsplit=1, flags=re.MULTILINE)[0]
    return [line for line in part.strip().splitlines() if line.strip()]


def order_in(report: str) -> dict[str, list[int]]:
    """The order the report prints, group by group, as issue numbers."""
    groups: dict[str, list[int]] = {}
    current = ""
    for line in section(report, "The backlog in its order"):
        if line.startswith("**"):
            current = {"Ready": "ready", "Claimed": "claimed", "Not ready": "not_ready"}[
                line.strip("*").split(",")[0]
            ]
            groups[current] = []
        elif m := re.match(r"- #(\d+) ", line):
            groups[current].append(int(m[1]))
    return groups


def order_of_make_backlog(outside: Outside) -> dict[str, list[int]]:
    """What `make backlog` prints for the fake's open issues, by the script's own code."""
    script = make_backlog_script()
    every = outside.get(f"/repos/{REPOSITORY}/issues?state=open&per_page=100")
    assert isinstance(every, list)
    raw = [issue for issue in every if "pull_request" not in issue]
    found = script.groups(raw, {"DEC-0999"})  # type: ignore[attr-defined]
    return {group: [e["number"] for e in found[group]] for group in found}


def test_roadmap_control_reports_nothing_for_a_consistent_backlog(
    outside: Outside, tmp_path: Path
) -> None:
    """A roadmap whose items name their issues, and issues in the milestones that name them: the
    report says no disagreement, and its order is the one `make backlog` prints."""
    first = outside.send("POST", f"/repos/{REPOSITORY}/milestones", {"title": "0.1.0"})
    second = outside.send("POST", f"/repos/{REPOSITORY}/milestones", {"title": "0.2.0"})
    complete = FORM.format(verified="hello.txt says hello.", blocked="nothing")
    lacking = FORM.format(verified="_No response_", blocked="nothing")
    ready = outside.issue("Ready", complete, ["task", "ready", "priority:high"], second["number"])  # type: ignore[arg-type]
    unready = outside.issue("Unready", lacking, ["task", "priority:low"], first["number"])  # type: ignore[arg-type]
    report = outside.issue("Reports of P-01", "", ["report"], None)
    outside.commit_on_main(
        {
            "docs/roadmap.md": ROADMAP.format(
                first=f"The first item (#{unready})", second=f"A greeting (#{ready})"
            ),
            f"{RECORDS}/DEC-0999-an-open-decision.md": "# DEC-0999\n",
        }
    )

    _, body = run_p01(outside, tmp_path / "state", report)
    assert section(body, "Where the roadmap and the issues disagree") == ["none"], body
    assert section(body, "Issues labelled `ready` that fail the standard") == ["none"], body
    assert order_in(body) == order_of_make_backlog(outside), body
    assert order_in(body) == {"ready": [ready], "claimed": [], "not_ready": [unready, 1]}
    assert "Written by Taktus, process P-01 Roadmap control" in body
    assert outside.labels(unready) == ["priority:low", "task"], "P-01 changes nothing"


def test_roadmap_control_reports_each_disagreement_once(outside: Outside, tmp_path: Path) -> None:
    """Every kind of disagreement, each once: an item without an issue, an issue its
    milestone's items do not name — named elsewhere or nowhere — and an issue labelled `ready`
    whose content fails the standard; an issue blocked by an open record keeps its label
    rightly and is not reported."""
    first = outside.send("POST", f"/repos/{REPOSITORY}/milestones", {"title": "0.1.0"})
    second = outside.send("POST", f"/repos/{REPOSITORY}/milestones", {"title": "0.2.0"})
    complete = FORM.format(verified="hello.txt says hello.", blocked="nothing")
    lacking = FORM.format(verified="_No response_", blocked="nothing")
    blocked = FORM.format(verified="hello.txt says hello.", blocked="DEC-0999")
    labelled = ["task", "ready", "priority:normal"]
    one, two = first["number"], second["number"]
    ready = outside.issue("Ready", complete, ["task", "ready", "priority:high"], two)  # type: ignore[arg-type]
    failing = outside.issue("Labelled, lacking", lacking, labelled, one)  # type: ignore[arg-type]
    elsewhere = outside.issue("Blocked, placed elsewhere", blocked, labelled, two)  # type: ignore[arg-type]
    nowhere = outside.issue("Placed nowhere", complete, ["task", "priority:low"], two)  # type: ignore[arg-type]
    report = outside.issue("Reports of P-01", "", ["report"], None)
    outside.commit_on_main(
        {
            "docs/roadmap.md": ROADMAP.format(
                first=f"The first item (#{failing}) · the second item (#{elsewhere})",
                second=f"A greeting (#{ready}) · an item without an issue",
            ),
            f"{RECORDS}/DEC-0999-an-open-decision.md": "# DEC-0999\n",
        }
    )

    _, body = run_p01(outside, tmp_path / "state", report)
    assert section(body, "Where the roadmap and the issues disagree") == [
        "- 0.2.0: the item “an item without an issue” names no issue",
        f"- #{elsewhere} is in milestone 0.2.0; the roadmap places it in 0.1.0",
        f"- #{nowhere} is in milestone 0.2.0; the roadmap does not name it",
    ], body
    assert section(body, "Issues labelled `ready` that fail the standard") == [
        f"- #{failing} is labelled `ready` and fails the standard: "
        "section 'How it is verified' is missing or empty"
    ], body
    for number in (failing, elsewhere, nowhere):
        disagreements = body.split("### The backlog in its order")[0]
        assert len(re.findall(rf"#{number}\b", disagreements)) == 1, body
    assert order_in(body) == order_of_make_backlog(outside), body
    assert outside.labels(failing) == ["priority:normal", "ready", "task"], "it only proposes"
    assert outside.state()[REPOSITORY]["comments"] == 1  # type: ignore[index]


# --- the takeover of every integration step (issue #90) ---------------------------------------

BUNDLES = {
    "P-01-roadmap-control.yaml": "p01-roadmap-control@2",
    "P-02-refinement.yaml": "p02-refinement@3",
    "P-03-implementation.yaml": "p03-implementation@3",
}
REPOSITORY_CONNECTOR = "connector.channel.repo"
TAKEN_OVER: dict[str, dict[str, set[str]]] = {
    REPOSITORY_CONNECTOR: {
        "p01-roadmap-control@2": {
            "read-roadmap",
            "read-issues",
            "read-open-records",
            "write-report",
        },
        "p02-refinement@3": {"read-issue", "read-comments", "write-sections"},
        "p03-implementation@3": {
            "read-issue",
            "read-comments",
            "read-open-issues",
            "read-open-records",
            "claim",
            "create-branch",
            "wait-for-pipeline",
            "read-pipeline",
            "open-pr",
            "label",
        },
    },
    "worker.endpoint": {"p03-implementation@3": {"implement"}},
    "model.endpoint": {"p02-refinement@3": {"refine"}},
}
"""Per integration, the steps of P-01 to P-03 it serves, which a person takes over without it."""


def bundle_of(name: str) -> dict[str, object]:
    with (BLUEPRINT / name).open(encoding="utf-8") as handle:
        document: dict[str, object] = yaml.safe_load(handle)
    return document


def on_an_integration(work: object) -> bool:
    """Whether a step's work reaches an adapter: a connector call, a wait on a connector, a
    worker assignment or a model call — what the removal test withholds."""
    return isinstance(work, ConnectorRule | WorkerWork | LlmWork) or (
        isinstance(work, WaitWork) and work.until is not None
    )


@pytest.mark.parametrize("bundle", sorted(BUNDLES))
def test_every_step_on_an_integration_falls_back_to_a_person_when_it_is_unavailable(
    bundle: str,
) -> None:
    """Issue #90, ADR-0013 B: a person can take over every step an integration serves. Each such
    step names `human` as its fallback, under a condition that names the integration being
    unavailable — what the removal test relies on for *changed* (contracts.md §4)."""
    version = parse_bundle(bundle_of(bundle))
    examples = {name: declared.example for name, declared in version.inputs.items()}
    found: set[str] = set()
    for step in version.ordered():
        if not on_an_integration(parse_work(step, version.work.get(step.id), examples)):
            continue
        found.add(step.id)
        fallback = step.fallback
        assert fallback is not None, f"{bundle}: {step.id} names no fallback"
        assert fallback.to is Method.HUMAN, f"{bundle}: {step.id} falls back to {fallback.to}"
        assert "unavailable" in fallback.when, (
            f"{bundle}: the fallback of {step.id} does not name its integration unavailable"
        )
    expected: set[str] = set()
    for uses in TAKEN_OVER.values():
        expected |= uses.get(BUNDLES[bundle], set())
    assert found == expected


async def test_removing_each_integration_of_the_three_processes_changes_them(
    outside: Outside, tmp_path: Path
) -> None:
    """Issue #90: S-01 withholds the repository connector, the coding worker and the model in
    turn, with P-01 to P-03 registered. No step breaks: every step the integration served falls
    back to a person, the verdict is *changed*, and the adapter's maturity record holds the
    removal half as passed. The processes write outward and the worker reaches a host, so their
    verdicts rest on resolution (ADR-0030); nothing is sent to the fakes."""
    state_dir = tmp_path / "state"
    configuration = EnvironmentConfiguration(
        {**outside.environment(state_dir), "TAKTUS_MODEL_PURPOSES": "reasoning"}
    )
    async with LocalWiring(configuration).services(
        state_dir=state_dir, worker_endpoint=outside.worker_url
    ) as services:
        for bundle in BUNDLES:
            await services.register_version.execute(
                RegisterProcessVersion(bundle_of(bundle), tenant=TENANT)
            )
        for integration, uses in TAKEN_OVER.items():
            run = await run_removal(services, integration)
            assert run.state is RunState.FINISHED, (integration, run.reason)

            result = (await result_of(services, run, "exercise"))["output"]
            assert result["verdict"] == "changed", (integration, result)
            steps = {p["process"]: {s["step"] for s in p["steps"]} for p in result["processes"]}
            assert steps == uses, integration
            for process in result["processes"]:
                for finding in process["steps"]:
                    assert finding["verdict"] != "broke", (integration, finding)
                    assert finding["fallback"] == "human", (integration, finding)
                    assert finding.get("alternative") is None, "no second adapter is configured"

            recorded = (await result_of(services, run, "record"))["output"]
            assert recorded["integration"] == integration
            assert not [gap for gap in recorded["missing"] if "removal" in gap], recorded

        async with services.work.transaction(TENANT):
            entries = list(await services.ledger.entries(TENANT))
        tested = [(e.adapter, e.outcome) for e in entries if e.kind == REMOVAL_TESTED]
        assert tested == [(integration, "changed") for integration in TAKEN_OVER]
        assert not [e for e in entries if e.kind.startswith("egress.")], "nothing left the system"
