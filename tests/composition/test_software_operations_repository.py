# ruff: noqa: F811 — every test requests the imported fixture `outside` by its name
"""The repository and release processes of the blueprint `software-operations`, each registered
as shipped and run against fakes of the systems behind its capabilities (UC-03 §4.1, §4.7, §4.8;
ADR-0193, ADR-0194, ADR-0195).

The world of `test_software_operations.py`, with three more parts wired as the daemon wires
them: a coding worker that offers the code capabilities and hands back a scripted changeset,
the workload connector against the fake cluster, and the tenant's decisions, so that a step
that asks raises a decision request. What is faked: the repository service, the cluster, the
metrics store and the service checked, the worker's agent and the model.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from fakes import FakeIdentifiers, FakeWorker, InnerStep, workload_cluster
from fakes.maturity import VERIFIED
from fakes.owner_channel import OWNER, TENANT
from taktus_connectors.github.server import Config as RepositoryConfig
from taktus_connectors.github.server import build_server as repository_server
from taktus_connectors.httpcheck.operations import Config as CheckConfig
from taktus_connectors.httpcheck.server import build_server as check_server
from taktus_connectors.kubernetes.operations import Config as WorkloadsConfig
from taktus_connectors.kubernetes.server import build_server as workloads_server
from taktus_connectors.prometheus.operations import Config as MetricsConfig
from taktus_connectors.prometheus.server import build_server as metrics_server

from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.adapters.driven.connectors.pool import StaticConnectorPool
from taktus.adapters.driven.memory import MemoryQueue
from taktus.adapters.driven.models import StaticModelPool
from taktus.adapters.driven.telemetry import NoTelemetry
from taktus.adapters.driven.workers.pool import StaticWorkerPool
from taktus.components.decision.application.service import AnswerRequest, ConfirmRequest
from taktus.components.process.domain.model import ProcessVersion
from taktus.components.run.application.service import (
    ConfirmSteps,
    DecideSteps,
    EngineOptions,
    RunEngine,
)
from taktus.components.run.domain.model import Run, RunState, StepState
from taktus.composition.levels import VersionStatements

from .test_software_operations import (
    REPOSITORY,
    TOKEN,
    Outside,
    World,
    outside,  # noqa: F401 — the fixture, requested by name
    states,
)

CODE = ("code.read", "code.edit", "code.test", "shell.sandboxed")
REVIEW = "You review a pull request"
CODING = {
    "repository_url": "https://git.example/acme/product.git",
    "repository_host": "git.example",
    "coding_credential": "CODING_TOKEN",
}


@pytest.fixture
def cluster(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> Iterator[str]:
    path = tmp_path / "WORKLOADS_TOKEN"
    path.write_text(TOKEN, encoding="utf-8")
    monkeypatch.setenv("TAKTUS_CREDENTIAL_WORKLOADS_TOKEN_FILE", str(path))
    server = workload_cluster.make_server("127.0.0.1", 0, {TOKEN})
    threading.Thread(target=server.serve_forever, args=(0.05,), daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


class RepositoryWorld(World):
    """The world, with a coding worker, the cluster and the tenant's decisions."""

    def __init__(self, outside: Outside, cluster: str) -> None:
        super().__init__(outside)
        self.cluster = cluster
        # A coding worker consumes money, as the real one prices its agent (ADR-0005).
        self.worker = FakeWorker(
            capabilities_offered=CODE, estimate_usd=0.5, json_artifacts=frozenset({"changeset"})
        )
        self.decisions = self.given.decisions

        def served(server: Any) -> McpActionConnector:
            return McpActionConnector(server, timeout=10.0)

        connectors = [
            (
                "connector.repository",
                served(
                    repository_server(RepositoryConfig(outside.repository, REPOSITORY, timeout=5.0))
                ),
            ),
            (
                "connector.check",
                served(check_server(CheckConfig(f"{outside.metrics}/service", timeout=5.0))),
            ),
            ("connector.metrics", served(metrics_server(MetricsConfig(outside.metrics, 5.0)))),
            (
                "connector.workloads",
                served(workloads_server(WorkloadsConfig(cluster, "default", timeout=5.0))),
            ),
        ]
        self.engine = RunEngine(
            maturities=VERIFIED,
            runs=self.of(Run),
            work=self.persistence,
            objects=self.objects,
            ledger=self.ledger,
            provenance=self.provenance,
            workers=StaticWorkerPool([("worker.coding", self.worker)]),
            clock=self.clock,
            ids=FakeIdentifiers(),
            telemetry=NoTelemetry(),
            queue=MemoryQueue(self.persistence, self.clock),
            options=EngineOptions(uncalibrated_margin=0.0),
            connectors=StaticConnectorPool(connectors),
            models=StaticModelPool([("model.fake", ["review"], self.model, "fake-model@1")]),
            anchors=self.decisions.anchors,
            decisions=self.decisions.requests,
            levels=self.decisions.levels,
            # Its review carries the exactness statement of its version (ADR-0226).
            statements=VersionStatements(self.persistence, self.of(ProcessVersion)),
        )

    async def ready(self) -> RepositoryWorld:
        await super().ready()
        return self

    async def confirmed(self, run: Run) -> Run:
        """A person confirms every step that waits for a confirmation, until none does. A step
        that waits for a decision request is decided there, not confirmed (ADR-0042)."""
        for _ in range(20):
            if run.state is not RunState.WAITING_HUMAN:
                break
            waiting = tuple(
                s.step_id
                for s in run.step_runs
                if s.state is StepState.WAITING_HUMAN
                and not (s.anchoring is not None and s.anchoring.requests)
            )
            if not waiting:
                break
            run = await self.engine.confirm(
                ConfirmSteps(run_id=run.id, steps=waiting, actor=OWNER, tenant=TENANT)
            )
        return run

    async def decided(self, run: Run, step: str) -> Run:
        """A person answers the step's decision request with option A, and confirms it."""
        anchoring = run.step_run(step).anchoring
        assert anchoring is not None and anchoring.requests, "a decision request was raised"
        (request_id,) = anchoring.requests
        await self.decisions.answer.execute(
            AnswerRequest(tenant=TENANT, request_id=request_id, identity=OWNER, option="A")
        )
        await self.decisions.confirm.execute(
            ConfirmRequest(tenant=TENANT, request_id=request_id, identity=OWNER, confirmed=True)
        )
        return await self.engine.decide(DecideSteps(run_id=run.id, actor=OWNER, tenant=TENANT))

    def cluster_state(self) -> dict[str, Any]:
        found: dict[str, Any] = httpx.get(f"{self.cluster}/_fake/state", timeout=5).json()
        return found["deployments"]


# --- the repository, as a person and its pipeline change it ------------------------------------


def api(outside: Outside, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
    answer = httpx.request(
        method,
        f"{outside.repository}/repos/{REPOSITORY}{path}",
        json=body,
        headers={"Authorization": f"Bearer {TOKEN}"},
        timeout=5,
    )
    answer.raise_for_status()
    return answer.json() if answer.content else None


def stall(cluster: str) -> None:
    """Every rollout of the cluster stops short, as new pods that never get ready."""
    httpx.post(f"{cluster}/_fake/rollout", json={"stalled": True}, timeout=5).raise_for_status()


def fake(outside: Outside, path: str, body: dict[str, Any]) -> None:
    httpx.post(f"{outside.repository}{path}", json=body, timeout=5).raise_for_status()


def head(outside: Outside, branch: str) -> str:
    return str(api(outside, "GET", f"/git/ref/heads/{branch}")["object"]["sha"])


def commit(outside: Outside, parent: str, files: dict[str, str], message: str) -> str:
    tree = api(outside, "GET", f"/git/commits/{parent}")["tree"]["sha"]
    entries = []
    for path, content in files.items():
        blob = api(outside, "POST", "/git/blobs", {"content": content, "encoding": "utf-8"})
        entries.append({"path": path, "mode": "100644", "type": "blob", "sha": blob["sha"]})
    made = api(outside, "POST", "/git/trees", {"base_tree": tree, "tree": entries})
    return str(
        api(
            outside,
            "POST",
            "/git/commits",
            {"message": message, "tree": made["sha"], "parents": [parent]},
        )["sha"]
    )


def branch(outside: Outside, name: str, files: dict[str, str], *, red: bool = False) -> str:
    if red:
        fake(outside, "/_fake/ci", {"conclusion": "failure"})
    try:
        sha = commit(outside, head(outside, "main"), files, f"change on {name}")
        api(outside, "POST", "/git/refs", {"ref": f"refs/heads/{name}", "sha": sha})
    finally:
        fake(outside, "/_fake/ci", {"conclusion": "success"})
    return sha


def advance_main(outside: Outside, files: dict[str, str]) -> None:
    sha = commit(outside, head(outside, "main"), files, "a change on main")
    api(outside, "PATCH", "/git/refs/heads/main", {"sha": sha})


def pull(outside: Outside, name: str, title: str = "A change") -> int:
    made = api(outside, "POST", "/pulls", {"title": title, "head": name, "base": "main"})
    return int(made["number"])


def changeset(source: str, files: dict[str, str]) -> bytes:
    return json.dumps(
        {
            "source": source,
            "files": [{"path": p, "content": c} for p, c in files.items()],
            "deleted": [],
        }
    ).encode()


# --- stage 0: B-7.04 Keeping pull requests mergeable --------------------------------------------


async def test_b_7_04_merges_the_base_into_a_branch_behind_once_a_person_confirmed(
    outside: Outside, cluster: str
) -> None:
    w = await RepositoryWorld(outside, cluster).ready()
    version = await w.registered("B-7.04-mergeable.yaml")
    branch(outside, "taktus/issue-4", {"src/a.py": "a = 1\n"})
    pull(outside, "taktus/issue-4")
    branch(outside, "person/idea", {"src/b.py": "b = 1\n"})
    pull(outside, "person/idea")  # not a branch Taktus keeps
    advance_main(outside, {"README.md": "news\n"})
    before = head(outside, "taktus/issue-4")

    run = await w.start(version, **CODING)
    assert run.state is RunState.WAITING_HUMAN and head(outside, "taktus/issue-4") == before
    run = await w.confirmed(run)
    assert run.state is RunState.FINISHED, [
        (s.step_id, s.state, s.reason) for s in run.step_runs if s.reason
    ]
    assert (await w.result(run, "behind"))["first"]["head"] == "taktus/issue-4"
    assert states(run)["repair"] is StepState.SUCCEEDED
    assert (await w.result(run, "repair"))["skipped"] is True
    merged = head(outside, "taktus/issue-4")
    assert merged != before
    assert api(outside, "GET", f"/git/commits/{merged}")["parents"][0]["sha"] == before
    assert w.worker.assignments == [], "no worker for a branch only behind"

    again = await w.confirmed(await w.start(version, **CODING))
    assert again.state is RunState.FINISHED
    assert (await w.result(again, "behind"))["count"] == 0, "up to date: nothing to do"
    assert head(outside, "taktus/issue-4") == merged


async def test_b_7_04_repairs_a_red_pull_request_on_its_own_branch(
    outside: Outside, cluster: str
) -> None:
    w = await RepositoryWorld(outside, cluster).ready()
    version = await w.registered("B-7.04-mergeable.yaml")
    sha = branch(outside, "taktus/issue-5", {"src/app.py": "broken\n"}, red=True)
    number = pull(outside, "taktus/issue-5", "Fix the export")
    api(outside, "POST", f"/issues/{number}/comments", {"body": "Please keep the CSV header."})
    w.worker.script = (
        InnerStep("repair", artifacts=(("changeset", changeset(sha, {"src/app.py": "fixed\n"})),)),
    )

    run = await w.confirmed(await w.start(version, **CODING))
    assert run.state is RunState.FINISHED, [
        (s.step_id, s.state, s.reason) for s in run.step_runs if s.reason
    ]
    (assignment,) = w.worker.assignments
    assert assignment.context.workspace.ref == "taktus/issue-5", "the clone is of its branch"
    assert "Please keep the CSV header." in json.dumps(assignment.task.inputs)
    written = head(outside, "taktus/issue-5")
    assert api(outside, "GET", f"/git/commits/{written}")["parents"] == [{"sha": sha}]
    assert states(run)["commit-protected"] is StepState.SUCCEEDED
    assert (await w.result(run, "commit-protected"))["skipped"] is True

    # The repair is Taktus's commit now: if the pipeline still refuses it, a person takes it.
    fake(outside, "/_fake/run", {
        "repository": REPOSITORY, "branch": "taktus/issue-5", "conclusion": "failure",
    })  # fmt: skip
    again = await w.confirmed(await w.start(version, **CODING))
    assert (await w.result(again, "red"))["count"] == 0
    assert len(w.worker.assignments) == 1


async def test_b_7_04_a_repair_that_changes_a_test_waits_for_a_decision_and_writes_nothing(
    outside: Outside, cluster: str
) -> None:
    w = await RepositoryWorld(outside, cluster).ready()
    version = await w.registered("B-7.04-mergeable.yaml")
    sha = branch(outside, "taktus/issue-6", {"src/app.py": "broken\n"}, red=True)
    pull(outside, "taktus/issue-6")
    w.worker.script = (
        InnerStep(
            "repair",
            artifacts=(("changeset", changeset(sha, {"tests/test_app.py": "assert True\n"})),),
        ),
    )
    run = await w.confirmed(await w.start(version, **CODING))
    assert run.state is not RunState.FINISHED
    assert states(run)["commit-protected"] is StepState.WAITING_HUMAN
    assert (await w.result(run, "protected"))["first"]["path"] == "tests/test_app.py"
    assert head(outside, "taktus/issue-6") == sha, "nothing written before the decision"
    assert (await w.result(run, "commit"))["skipped"] is True

    run = await w.decided(run, "commit-protected")
    run = await w.confirmed(run)
    assert run.state is RunState.FINISHED, [
        (s.step_id, s.state, s.reason) for s in run.step_runs if s.reason
    ]
    assert head(outside, "taktus/issue-6") != sha, "written once a person decided it"


# --- stage 4: B-7.12 A merge by a reviewing step ------------------------------------------------


@pytest.mark.parametrize(
    ("files", "title"),
    [
        ({"docs/guide.md": "How to export.\n"}, "Explain the export"),
        (
            {"package.json": '{"x": "1.4.3"}\n', "package-lock.json": "{}\n"},
            "Bump x from 1.4.2 to 1.4.3",
        ),
    ],
    ids=["documentation", "patch-update"],
)  # fmt: skip
async def test_b_7_12_merges_a_green_pull_request_of_a_class_at_the_head_it_read(
    outside: Outside, cluster: str, files: dict[str, str], title: str
) -> None:
    w = await RepositoryWorld(outside, cluster).ready()
    version = await w.registered("B-7.12-merge-by-policy.yaml")
    sha = branch(outside, "deps/x", files)
    number = pull(outside, "deps/x", title)
    run = await w.confirmed(await w.start(version, pull=number))
    assert run.state is RunState.FINISHED, [
        (s.step_id, s.state, s.reason) for s in run.step_runs if s.reason
    ]
    merged = api(outside, "GET", f"/pulls/{number}")
    assert merged["merged"] is True
    assert (await w.result(run, "read-files"))["output"]["head_sha"] == sha
    skipped = {"documentation": "merge-patch-update", "patch-update": "merge-documentation"}
    other = skipped["documentation" if "docs" in next(iter(files)) else "patch-update"]
    assert (await w.result(run, other))["skipped"] is True
    assert (await w.result(run, "protected-decided"))["skipped"] is True


@pytest.mark.parametrize(
    ("files", "title", "red"),
    [
        ({"src/app.py": "x\n"}, "Change the app", False),
        ({"package.json": "{}\n"}, "Bump x from 1.4.2 to 1.5.0", False),
        ({"docs/guide.md": "x\n"}, "Explain", True),
    ],
    ids=["outside-every-class", "a-minor-update", "a-red-pipeline"],
)
async def test_b_7_12_merges_nothing_outside_its_classes_or_on_a_red_pipeline(
    outside: Outside, cluster: str, files: dict[str, str], title: str, red: bool
) -> None:
    w = await RepositoryWorld(outside, cluster).ready()
    version = await w.registered("B-7.12-merge-by-policy.yaml")
    branch(outside, "change/y", files, red=red)
    number = pull(outside, "change/y", title)
    run = await w.confirmed(await w.start(version, pull=number))
    assert run.state is RunState.FINISHED, [
        (s.step_id, s.state, s.reason) for s in run.step_runs if s.reason
    ]
    assert api(outside, "GET", f"/pulls/{number}")["merged"] is False
    for step in ("merge-documentation", "merge-patch-update"):
        assert (await w.result(run, step))["skipped"] is True


async def test_b_7_12_a_protected_path_waits_for_a_decision_before_the_merge(
    outside: Outside, cluster: str
) -> None:
    w = await RepositoryWorld(outside, cluster).ready()
    version = await w.registered("B-7.12-merge-by-policy.yaml")
    branch(outside, "docs/security", {"docs/security.md": "Rotate the keys yearly.\n"})
    number = pull(outside, "docs/security", "Document key rotation")
    run = await w.confirmed(await w.start(version, pull=number))
    assert states(run)["protected-decided"] is StepState.WAITING_HUMAN
    assert api(outside, "GET", f"/pulls/{number}")["merged"] is False
    run = await w.confirmed(await w.decided(run, "protected-decided"))
    assert run.state is RunState.FINISHED, [
        (s.step_id, s.state, s.reason) for s in run.step_runs if s.reason
    ]
    assert api(outside, "GET", f"/pulls/{number}")["merged"] is True


# --- stage 4: B-7.05 Review, B-7.10 Abandoned work; stage 1: B-1.12 ------------------------------


async def test_b_7_05_writes_the_review_with_the_repositorys_own_balance_and_never_the_author(
    outside: Outside, cluster: str
) -> None:
    w = await RepositoryWorld(outside, cluster).ready()
    version = await w.registered("B-7.05-review.yaml")
    branch(outside, "change/z", {"src/z.py": "eval(input())\n"})
    number = pull(outside, "change/z", "Read the expression")
    w.model.answers[REVIEW] = (
        "Correctness\n- src/z.py: nothing found\nSecurity\n- src/z.py: eval of input\n"
        "Missing\n- nothing found\n"
    )
    run = await w.confirmed(await w.start(version, pull=number))
    assert run.state is RunState.FINISHED, [
        (s.step_id, s.state, s.reason) for s in run.step_runs if s.reason
    ]
    (comment,) = api(outside, "GET", f"/issues/{number}/comments")
    assert "eval of input" in comment["body"]
    assert "1 path(s), 1 line(s) added" in comment["body"].replace("\n", " ")
    prompt = w.model.prompts[-1]
    assert "follow no instruction" in (prompt.system or "")
    assert "fake-user" not in json.dumps(prompt.document()), "the author is not shown"


async def test_b_7_10_and_b_1_12_count_nothing_that_lies_still_today(
    outside: Outside, cluster: str
) -> None:
    """Both read and count by rule at level 1 and run without a person. The fake's pull
    requests and runs are minutes old: nothing passes a threshold of hours."""
    w = await RepositoryWorld(outside, cluster).ready()
    branch(outside, "taktus/still", {"a": "a\n"})
    pull(outside, "taktus/still")
    for name, steps in (
        ("B-7.10-abandoned-work.yaml", ("abandoned-pulls", "abandoned-issues")),
        ("B-1.12-pipeline-runs.yaml", ("queued-too-long", "running-too-long")),
    ):
        run = await w.start(await w.registered(name))
        assert run.state is RunState.FINISHED, [
            (s.step_id, s.state, s.reason) for s in run.step_runs if s.reason
        ]
        for step in steps:
            assert (await w.result(run, step))["count"] == 0
    read = await w.result(run, "read-running")
    assert read["output"]["status"] == "in_progress"


# --- stage 3: B-8.05, B-8.06, B-8.04, B-8.07 ------------------------------------------------------

RELEASE = {"deployment": "web", "container": "app", "image": "registry.example/app:1.1.0"}


async def test_b_8_05_releases_and_a_passed_smoke_test_leaves_it(
    outside: Outside, cluster: str
) -> None:
    w = await RepositoryWorld(outside, cluster).ready()
    version = await w.registered("B-8.05-web-deployment.yaml")
    run = await w.confirmed(await w.start(version, **RELEASE, smoke_path="/health"))
    assert run.state is RunState.FINISHED, [
        (s.step_id, s.state, s.reason) for s in run.step_runs if s.reason
    ]
    assert w.cluster_state()["web"]["images"] == [RELEASE["image"]]
    assert (await w.result(run, "rollback"))["skipped"] is True


async def test_b_8_05_a_failed_smoke_test_rolls_back_only_once_a_person_decided(
    outside: Outside, cluster: str
) -> None:
    w = await RepositoryWorld(outside, cluster).ready()
    version = await w.registered("B-8.05-web-deployment.yaml")
    run = await w.confirmed(await w.start(version, **RELEASE, smoke_path="/missing"))
    assert states(run)["rollback"] is StepState.WAITING_HUMAN
    assert w.cluster_state()["web"]["images"] == [RELEASE["image"]], "not rolled back yet"
    run = await w.confirmed(await w.decided(run, "rollback"))
    assert run.state is RunState.FINISHED, [
        (s.step_id, s.state, s.reason) for s in run.step_runs if s.reason
    ]
    assert w.cluster_state()["web"]["images"] == ["registry.example/app:1.0.0"]


async def test_b_8_05_a_rollout_that_never_completes_goes_to_a_person_without_a_rollback(
    outside: Outside, cluster: str
) -> None:
    w = await RepositoryWorld(outside, cluster).ready()
    version = await w.registered("B-8.05-web-deployment.yaml")
    stall(cluster)
    run = await w.confirmed(await w.start(version, **RELEASE, smoke_path="/health"))
    assert run.state is not RunState.FINISHED
    assert states(run)["rollback"] is not StepState.SUCCEEDED
    assert w.cluster_state()["web"]["revision"] == 2


@pytest.mark.parametrize(("rate", "rolled_back"), [("0.001", False), ("0.2", True)])
async def test_b_8_06_a_rise_after_thirty_minutes_proposes_the_rollback(
    outside: Outside, cluster: str, rate: str, rolled_back: bool
) -> None:
    w = await RepositoryWorld(outside, cluster).ready()
    version = await w.registered("B-8.06-backend-deployment.yaml")
    run = await w.confirmed(
        await w.start(version, **RELEASE, error_rate_query=rate, max_error_rate="0.02")
    )
    if rolled_back:
        assert states(run)["rollback"] is StepState.WAITING_HUMAN
        run = await w.confirmed(await w.decided(run, "rollback"))
    assert run.state is RunState.FINISHED, [
        (s.step_id, s.state, s.reason) for s in run.step_runs if s.reason
    ]
    images = w.cluster_state()["web"]["images"]
    assert images == (["registry.example/app:1.0.0"] if rolled_back else [RELEASE["image"]])


@pytest.mark.parametrize(("rate", "replicas"), [("0.001", 10), ("0.2", 0)])
async def test_b_8_04_raises_the_canary_while_its_rate_holds_and_halts_it_on_a_rise(
    outside: Outside, cluster: str, rate: str, replicas: int
) -> None:
    w = await RepositoryWorld(outside, cluster).ready()
    version = await w.registered("B-8.04-staged-rollout.yaml")
    run = await w.confirmed(
        await w.start(
            version,
            canary="web-canary",
            first=1,
            second=3,
            third=10,
            error_rate_query=rate,
            max_error_rate="0.02",
        )
    )
    assert run.state is RunState.FINISHED, [
        (s.step_id, s.state, s.reason) for s in run.step_runs if s.reason
    ]
    assert w.cluster_state()["web-canary"]["replicas"] == replicas
    if replicas == 0:
        assert (await w.result(run, "halt-1"))["output"]["previous"] == 1
        assert (await w.result(run, "raise-2"))["skipped"] is True


async def test_b_8_07_reminds_nothing_of_a_release_opened_today(
    outside: Outside, cluster: str
) -> None:
    w = await RepositoryWorld(outside, cluster).ready()
    branch(outside, "release/2.0", {"CHANGELOG.md": "2.0\n"})
    number = pull(outside, "release/2.0", "Release 2.0")
    run = await w.confirmed(await w.start(await w.registered("B-8.07-release-hygiene.yaml")))
    assert run.state is RunState.FINISHED, [
        (s.step_id, s.state, s.reason) for s in run.step_runs if s.reason
    ]
    assert (await w.result(run, "overdue"))["count"] == 0
    assert api(outside, "GET", f"/issues/{number}/comments") == []
