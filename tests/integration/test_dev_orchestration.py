"""The two runnable processes of the dev-orchestration blueprint, end to end, with everything
outside Taktus faked and everything inside real.

P-02 Refinement reads an issue without acceptance criteria, has a model write them and posts
them as a comment. P-03 Implementation reads the same issue, admits it now that the criteria
are there, has the coding worker implement it in a clone of a repository, puts the worker's
change on a branch through the connector, waits for the pipeline's verdict, opens the pull
request and labels it. `taktusctl run` drives both, as the owner will drive the live run
(`tools/first_run.sh`).

What is real: the command line, the run engine, the reference connector (a process, over MCP),
the coding worker (a process, behind the worker contract), the model adapter. What is faked:
the repository hosting service (`tests/fakes/repository_service.py`, a process), the model
endpoint (`tests/fakes/model_service.py`, a thread), the coding agent
(`workers/claudecode/fake_agent.py`, which really writes files). What the fakes hold
afterwards is the proof: one comment with the criteria, one branch with the worker's files on
one marked commit, one pull request with one label, and the run's ledger with an egress entry
for each of the three writes.
"""

from __future__ import annotations

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
from fakes import model_service

from .conftest import ROOT, free_port
from .test_first_slice import PLAIN, taktusctl

BLUEPRINT = ROOT / "blueprints" / "dev-orchestration" / "processes"
FAKE_SERVICE = ROOT / "tests" / "fakes" / "repository_service.py"
CODING_WORKER = ROOT / "workers" / "claudecode" / "worker.py"
FAKE_AGENT = ROOT / "workers" / "claudecode" / "fake_agent.py"
REPOSITORY = "acme/product"
ISSUE = 1  # the fake seeds every repository with issue #1, without acceptance criteria


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
        model, _ = model_service.make_server("127.0.0.1", 0)
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


def run_bundle(outside: Outside, state_dir: Path, bundle: str, *inputs: str) -> str:
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
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return completed.stdout


def test_refinement_then_implementation_end_to_end(outside: Outside, tmp_path: Path) -> None:
    state_dir = tmp_path / "state"

    # P-02: the issue gains its acceptance criteria as a comment.
    output = run_bundle(outside, state_dir, "P-02-refinement.yaml", f"issue={ISSUE}")
    assert "state finished" in output, output
    assert re.search(r"egress\.write\s+write-criteria\s+acted", output), output
    assert re.search(r"refine\s+llm\s+sourced\s+succeeded\s+tokens", output), output
    comments = outside.get(f"/repos/{REPOSITORY}/issues/{ISSUE}/comments")
    assert isinstance(comments, list) and len(comments) == 1
    assert "## Acceptance criteria" in comments[0]["body"]
    assert "Written by Taktus, process P-02" in comments[0]["body"]
    assert "taktus-idempotency-key" in comments[0]["body"], "the mark that makes a repeat findable"

    # P-02 again: the issue now has criteria, so admission refuses — nothing is written twice.
    again = subprocess.run(  # noqa: S603
        [
            taktusctl(),
            "run",
            "--process",
            str(BLUEPRINT / "P-02-refinement.yaml"),
            "--input",
            f"issue={ISSUE}",
        ],
        capture_output=True,
        text=True,
        env=outside.environment(state_dir),
        check=False,
        timeout=120,
    )
    assert again.returncode == 3, again.stdout + again.stderr
    assert "condition 4 does not hold" in again.stdout, again.stdout
    assert outside.state()[REPOSITORY]["comments"] == 1  # type: ignore[index]

    # P-03: the coding worker implements, the run branches, waits for the pipeline, opens the
    # pull request and labels it.
    output = run_bundle(
        outside,
        state_dir,
        "P-03-implementation.yaml",
        f"issue={ISSUE}",
        f"repository_url={outside.clone_url}",
        "repository_host=localhost",
        "coding_credential=CODING_AGENT_API_KEY",
    )
    assert "state finished" in output, output
    for step in ("admit", "verify"):
        assert f"{step:<20} rule       exact     succeeded" in output, output
    assert "implement            worker     tolerant  succeeded" in output, output
    assert "wait-for-pipeline    wait       -         succeeded" in output, output
    kinds = [
        line.split()[2]
        for line in output.splitlines()
        if line.strip().startswith(tuple("0123456789")) and "egress" in line
    ]
    assert kinds == ["egress.write", "egress.write", "egress.write"], output

    state = outside.state()[REPOSITORY]
    assert state == {  # type: ignore[comparison-overlap]
        "issues": 1,
        "pulls": 1,
        "comments": 1,
        "runs": 2,  # the seed's and the branch's
        "branches": 2,  # main and taktus/issue-1
        "labels": 1,
    }
    ref = outside.get(f"/repos/{REPOSITORY}/git/ref/heads/taktus/issue-{ISSUE}")
    assert isinstance(ref, dict)
    commit = outside.get(f"/repos/{REPOSITORY}/git/commits/{ref['object']['sha']}")
    assert isinstance(commit, dict)
    assert "Taktus-Idempotency-Key: taktus:run_" in commit["message"]
    tree = outside.get(f"/repos/{REPOSITORY}/git/trees/{commit['tree']['sha']}")
    assert isinstance(tree, dict)
    paths = sorted(entry["path"] for entry in tree["tree"])
    assert paths == ["checked.txt", "hello.txt", "notes/plan.md"], "the fake agent's files"
    pulls = outside.get(f"/repos/{REPOSITORY}/pulls")
    assert isinstance(pulls, list) and len(pulls) == 1
    pull = pulls[0]
    assert pull["head"]["ref"] == f"taktus/issue-{ISSUE}" and pull["base"]["ref"] == "main"
    assert pull["title"] == f"Seed issue (#{ISSUE})"
    assert f"Closes #{ISSUE}." in pull["body"] and "Opened by Taktus, process P-03" in pull["body"]
    assert "Wrote notes/plan.md" in pull["body"], "the worker's own summary"
    assert [label["name"] for label in pull["labels"]] == ["taktus"]

    # Every write is in the ledger as egress, and the chain and the provenance verify.
    ledger = json.loads((state_dir / "ledger.json").read_text())["default"]
    egress = [e for e in ledger if e["kind"].startswith("egress.")]
    assert [e["refs"]["step_id"] for e in egress] == [
        "write-criteria",
        "create-branch",
        "open-pr",
        "label",
    ]
    assert all(e["content_digest"].startswith("sha256:") for e in egress)
    assert "DOES NOT VERIFY" not in output
