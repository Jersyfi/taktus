"""Stage 4 of UC-03 end to end: from a customer's message to the merged fix (#439, UC-03 §4.7,
§5).

One chain, each process registered as shipped and run in-process against the fakes of the
other composition tests: B-3.06 files the defect a customer reported as an issue; B-7.01
classifies it; the dev-orchestration blueprint's P-02 writes the sections it lacks; P-03 has the
coding worker implement it, puts the change on a branch, waits for the pipeline and opens the
pull request; B-7.05 reviews it; B-7.12 merges it under its policy. What one process left in the
repository is what the next one reads: the issue's number, then the pull request's.

Two acts in between are a person's, as UC-03 keeps them: confirming the specification (B-7.02)
— the person takes the sections P-02 proposed into the issue — and the roadmap — the person
gives it a milestone and a priority, marks it ready and hands it to Taktus (DEC-0197). The test
does both by hand, through the repository's API.

What is faked: the repository hosting service with its pipeline, the mail server, the model
(answers by the step's system prompt) and the coding worker, whose change is a documentation
file, the class B-7.12's policy merges.
"""

from __future__ import annotations

from typing import Any

import yaml
from fakes import FakeIdentifiers, InnerStep
from fakes.maturity import VERIFIED
from fakes.owner_channel import OWNER, TENANT
from taktus_connectors.github.server import Config as RepositoryConfig
from taktus_connectors.github.server import build_server as repository_server
from taktus_connectors.mail.protocol import Config as MailConfig
from taktus_connectors.mail.server import build_server as mail_server

from taktus.adapters.driven.connectors.mcp import McpActionConnector
from taktus.adapters.driven.connectors.pool import StaticConnectorPool
from taktus.adapters.driven.memory import MemoryQueue
from taktus.adapters.driven.models import StaticModelPool
from taktus.adapters.driven.telemetry import NoTelemetry
from taktus.adapters.driven.workers.pool import StaticWorkerPool
from taktus.components.process.domain.model import ProcessVersion
from taktus.components.run.application.service import EngineOptions, ResumeRun, RunEngine
from taktus.components.run.domain.model import Run, RunState
from taktus.composition.levels import VersionStatements

from .test_software_operations import (
    MAILBOX,
    REPORT,
    REPOSITORY,
    ROOT,
    TRIAGE,
    Outside,
    RegisterProcessVersion,
)
from .test_software_operations import outside as outside  # the fixture, requested by name
from .test_software_operations_repository import (
    CODING,
    REVIEW,
    RepositoryWorld,
    advance_main,
    api,
    changeset,
    head,
)
from .test_software_operations_repository import cluster as cluster  # the fixture, by name

DEV = ROOT / "blueprints" / "dev-orchestration" / "processes"
RECORDS = "docs/decisions/open"
SECTIONS = (
    "### What must be achieved\n\nThe CSV export finishes for reports of any size.\n\n"
    "### How it is verified\n\ndocs/export.md names the limit the export holds.\n\n"
    "### Where the boundary lies\n\nOnly the export's documentation changes.\n"
)
SUMMARY = (
    "<!-- commit-type: docs -->\n"
    "## What this is about\n\nThe export's limit, undocumented until now.\n\n"
    "## Decisions required\n\nNone.\n\n"
    "## Behaviour changes\n\nNone.\n\n"
    "## What was done\n\ndocs/export.md names the limit.\n\n"
    "## Why this way\n\nThe issue asks for the documentation only.\n\n"
    "## What to check\n\nThe limit in docs/export.md.\n"
)
"""The worker's summary, in the form of the repository's pull request description."""
CLOSING = "## Needed from the owner\n\nNothing is open.\n"


class ChainWorld(RepositoryWorld):
    """The repository world, with the mail server B-3.06 reads and a model for every purpose
    the chain asks for."""

    def __init__(self, outside: Outside, cluster: str) -> None:
        super().__init__(outside, cluster)

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
                "connector.mail",
                served(
                    mail_server(
                        MailConfig(
                            imap_host="127.0.0.1",
                            imap_port=outside.mail.imap_port,
                            smtp_host="127.0.0.1",
                            smtp_port=outside.mail.smtp_port,
                            user=MAILBOX,
                            address=MAILBOX,
                            security="none",
                            timeout=5.0,
                        )
                    )
                ),
            ),
        ]
        purposes = ["triage", "support", "check", "review", "reasoning"]
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
            models=StaticModelPool([("model.fake", purposes, self.model, "fake-model@1")]),
            anchors=self.decisions.anchors,
            decisions=self.decisions.requests,
            levels=self.decisions.levels,
            messages=self.told,
            statements=VersionStatements(self.persistence, self.of(ProcessVersion)),
        )

    async def ready(self) -> ChainWorld:
        await super().ready()
        return self

    async def developed(self, name: str) -> ProcessVersion:
        """A bundle of the dev-orchestration blueprint, registered as shipped."""
        bundle = yaml.safe_load((DEV / name).read_text(encoding="utf-8"))
        return await self.register.execute(RegisterProcessVersion(bundle, tenant=TENANT, by=OWNER))

    async def through(self, run: Run) -> Run:
        """Confirmed until nothing waits, and every parked step resumed at its next check, as
        the runner does."""
        for _ in range(30):
            run = await self.confirmed(run)
            if run.state is not RunState.HALTED:
                return run
            moments = [
                s.block.next_check_at for s in run.step_runs if s.block and s.block.next_check_at
            ]
            if moments:
                self.clock.current = max(self.clock.current, min(moments))
            run = await self.engine.resume(ResumeRun(run_id=run.id, actor=OWNER, tenant=TENANT))
        return run


def finished(run: Run) -> None:
    assert run.state is RunState.FINISHED, [
        (s.step_id, s.state, s.reason) for s in run.step_runs if s.reason
    ]


async def test_a_customers_message_becomes_a_merged_fix_through_stage_four(
    outside: Outside, cluster: str
) -> None:
    w = await ChainWorld(outside, cluster).ready()
    advance_main(outside, {f"{RECORDS}/README.md": "Open records.\n"})

    # B-3.06: the customer's message, filed as an issue once a person confirmed it.
    w.model.answers[REPORT] = (
        "title: CSV export stops with an error\nsteps: open Reports, press Export\n"
        "device: not given\nversion: 2.4.1\n"
    )
    run = await w.through(
        await w.start(
            await w.registered("B-3.06-bug-from-support.yaml"), message="<seed-1@mail.example>"
        )
    )
    finished(run)
    [issue] = [i for i in outside.issues() if i["title"] == "CSV export stops with an error"]
    number = issue["number"]
    assert "support-case:<seed-1@mail.example>" in issue["body"]

    # B-7.01: classified and labelled.
    w.model.answers[TRIAGE] = "class: defect\n"
    run = await w.through(await w.start(await w.registered("B-7.01-triage.yaml"), issue=number))
    finished(run)
    assert "type:defect" in [
        label["name"] for label in api(outside, "GET", f"/issues/{number}")["labels"]
    ]

    # P-02: the sections the issue lacks, proposed as a comment.
    w.model.answers["You write the missing sections"] = SECTIONS
    run = await w.through(await w.start(await w.developed("P-02-refinement.yaml"), issue=number))
    finished(run)
    proposed = [c["body"] for c in api(outside, "GET", f"/issues/{number}/comments")]
    assert any("How it is verified" in body for body in proposed)

    # A person confirms the specification and orders it into the roadmap: the sections into the
    # issue's text, a component, a milestone, one priority, ready, and handed to Taktus.
    milestone = api(outside, "POST", "/milestones", {"title": "2.5.0"})["number"]
    api(
        outside,
        "PATCH",
        f"/issues/{number}",
        {
            "body": f"{issue['body']}\n\n{SECTIONS}\n### Component\n\nexport\n\n"
            "### Blocked by\n\nnothing\n",
            "milestone": milestone,
        },
    )
    api(
        outside,
        "POST",
        f"/issues/{number}/labels",
        {"labels": ["ready", "priority:high", "to-taktus"]},
    )

    # P-03: implemented by the coding worker, put on a branch, judged by the pipeline, opened.
    w.worker.script = (
        InnerStep(
            "implement",
            artifacts=(
                (
                    "changeset",
                    changeset(head(outside, "main"), {"docs/export.md": "Up to 1 GB.\n"}),
                ),
                ("summary", SUMMARY.encode()),
                ("closing", CLOSING.encode()),
            ),
        ),
    )
    run = await w.through(
        await w.start(
            await w.developed("P-03-implementation.yaml"),
            issue=number,
            records_path=RECORDS,
            **CODING,
        )
    )
    finished(run)
    [pull] = [p for p in api(outside, "GET", "/pulls") if f"Closes #{number}." in p["body"]]

    # B-7.05: reviewed by a model that is not shown the author.
    w.model.answers[REVIEW] = (
        "Correctness\n- docs/export.md: nothing found\nSecurity\n- nothing found\n"
        "Missing\n- nothing found\n"
    )
    run = await w.through(
        await w.start(await w.registered("B-7.05-review.yaml"), pull=pull["number"])
    )
    finished(run)
    assert api(outside, "GET", f"/issues/{pull['number']}/comments")

    # B-7.12: a green pull request of documentation, merged under the policy at the head it read.
    run = await w.through(
        await w.start(await w.registered("B-7.12-merge-by-policy.yaml"), pull=pull["number"])
    )
    finished(run)
    assert api(outside, "GET", f"/pulls/{pull['number']}")["merged"] is True
