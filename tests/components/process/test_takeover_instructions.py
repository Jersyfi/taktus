"""Every process version carries takeover instructions, and a trial of them is kept with it
(UC-6.3, ADR-0180).

Registration refuses a bundle without them, with an entry for a step it does not have or none
for one it has, with a credential a step names and its entry does not, and with an identifier a
person could not look up. Every shipped bundle carries all six elements for every step. A trial
names a role and the version, is a ledger entry, and a version at level 3 or 4 without a passed
trial on it is untried; a trial on an earlier version does not count.
"""

from __future__ import annotations

import copy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml
from fakes import FakeClock, FakeIdentifiers
from fakes.takeover import instructed

from taktus.adapters.driven.memory import MemoryLedgerStore, MemoryPersistence, MemoryRepository
from taktus.components.ledger.application.service import ChainedLedger
from taktus.components.process.application.service.register_version import (
    RegisterProcessVersion,
    RegisterProcessVersionHandler,
    parse_bundle,
)
from taktus.components.process.application.service.takeover import (
    TRIAL,
    RecordTrial,
    TakeoverTrials,
)
from taktus.components.process.domain.model import (
    InvalidProcess,
    Process,
    ProcessVersion,
    TakeoverTrial,
)
from taktus.components.process.domain.service import takeover as instructed_rules
from taktus.components.process.domain.service.bundle import bundle_of

ROOT = Path(__file__).resolve().parents[3]
BUNDLES = sorted(
    p
    for p in [*(ROOT / "examples").rglob("*.yaml"), *(ROOT / "blueprints").rglob("*.yaml")]
    if "steps" in (yaml.safe_load(p.read_text()) or {})
)
AT = datetime(2026, 11, 3, 9, 0, tzinfo=UTC)
TENANT = "default"
SIX = ("system", "do", "expertise", "credentials", "done", "skills")


def two_steps(level: int = 2, version: str = "1") -> dict[str, Any]:
    return {
        "id": "p",
        "version": version,
        "name": "P",
        "autonomy": {"level": level, "reason": "r", "toward_next": "t"}
        if level < 4
        else {"level": 4, "reason": "r"},
        "steps": [
            {
                "id": "read",
                "method": "rule",
                "reason": "a read",
                "rejected": [],
                "exactness": "sourced",
                "checks": [{"kind": "bounds", "pattern": "^\\{"}],
                "work": {
                    "rule": "connector",
                    "operation": "repository.issues.read",
                    "input": {"number": 1},
                    "credentials": [{"name": "REPOSITORY_TOKEN", "injected_as": "env"}],
                },
            },
            {
                "id": "write",
                "method": "rule",
                "reason": "a form of words",
                "rejected": [],
                "exactness": "exact",
                "checks": [{"kind": "recomputation"}],
                "depends_on": ["read"],
                "work": {"rule": "constant", "value": "done"},
            },
        ],
        "takeover": {
            "sequence": "a person reads the issue, then writes the answer",
            "steps": {
                "read": {
                    "system": "the repository's hosting service",
                    "do": "open the issue and read it",
                    "expertise": "reading an issue",
                    "credentials": [
                        {"parameter": "REPOSITORY_TOKEN", "where": "the operator's secret store"}
                    ],
                    "done": "the issue is read",
                },
                "write": {
                    "system": "a text file",
                    "do": "write the word done",
                    "expertise": "none",
                    "credentials": [],
                    "done": "the word is written",
                },
            },
        },
    }


def refused(bundle: dict[str, Any]) -> str:
    with pytest.raises(InvalidProcess) as raised:
        parse_bundle(bundle)
    return " ".join(raised.value.findings)


def test_a_version_without_takeover_instructions_does_not_register() -> None:
    bundle = two_steps()
    del bundle["takeover"]
    assert "carries its takeover instructions under `takeover`" in refused(bundle)
    assert parse_bundle(two_steps()).takeover is not None


def test_instructions_that_describe_a_step_it_has_not_or_omit_one_it_has_do_not_register() -> None:
    extra = two_steps()
    extra["takeover"]["steps"]["gone"] = copy.deepcopy(extra["takeover"]["steps"]["write"])
    assert "describe 'gone', which is not a step of this process" in refused(extra)
    omitted = two_steps()
    del omitted["takeover"]["steps"]["write"]
    assert "omit the step 'write'" in refused(omitted)


def test_a_changed_step_that_gains_a_credential_needs_its_instructions_to_name_it() -> None:
    changed = two_steps(version="2")
    changed["steps"][1]["work"] = {
        "rule": "connector",
        "operation": "repository.comments.list",
        "input": {"number": 1},
        "credentials": [{"name": "REPOSITORY_TOKEN", "injected_as": "env"}],
    }
    found = refused(changed)
    assert "'write' uses the credential REPOSITORY_TOKEN" in found
    changed["takeover"]["steps"]["write"]["credentials"] = [
        {"parameter": "REPOSITORY_TOKEN", "where": "the operator's secret store"}
    ]
    assert parse_bundle(changed).takeover is not None


@pytest.mark.parametrize("field", ["system", "do", "expertise", "credentials", "done"])
def test_every_written_element_is_required(field: str) -> None:
    bundle = two_steps()
    del bundle["takeover"]["steps"]["write"][field]
    assert "takeover: steps.write." + field in refused(bundle)


@pytest.mark.parametrize(
    "text",
    ["read { $input: issue }", "see ADR-0128", "as UC-6.3 says", "the run run_0001", "${name}"],
)
def test_an_identifier_a_person_could_not_look_up_is_refused(text: str) -> None:
    bundle = two_steps()
    bundle["takeover"]["steps"]["read"]["do"] = text
    assert "could not look up without Taktus" in refused(bundle)


def test_a_credential_names_its_parameter_never_a_value() -> None:
    bundle = two_steps()
    bundle["takeover"]["steps"]["read"]["credentials"] = [{"parameter": "ghp_x1", "where": "w"}]
    assert "credentials" in refused(bundle)


@pytest.mark.parametrize("path", BUNDLES, ids=lambda p: str(p.relative_to(ROOT)))
def test_every_shipped_bundle_finds_all_six_for_every_step_and_nothing_unlookable(
    path: Path,
) -> None:
    version = parse_bundle(yaml.safe_load(path.read_text()))
    assert version.takeover is not None
    read = instructed_rules.rendered(version.takeover, version.ordered(), {})
    assert [entry["step"] for entry in read["steps"]] == [s.id for s in version.ordered()]
    for entry in read["steps"]:
        for element in SIX:
            assert element in entry, f"{entry['step']}: {element}"
        for element in ("system", "do", "expertise", "done"):
            assert entry[element].strip(), f"{entry['step']}: {element} is empty"
        for credential in entry["credentials"]:
            assert credential["parameter"] and credential["where"].strip()
    assert read["sequence"].strip()
    for where, text in instructed_rules.texts(version.takeover):
        for pattern, what in instructed_rules.UNLOOKABLE:
            assert pattern.search(text) is None, f"{path.name} {where}: {what}"


def test_a_version_written_back_carries_its_instructions() -> None:
    version = parse_bundle(two_steps())
    again = parse_bundle(bundle_of(version, as_version="2", author=None, reason="a rollback"))
    assert again.takeover == version.takeover


def test_the_fixture_gives_a_test_bundle_instructions_that_register() -> None:
    bundle = two_steps()
    del bundle["takeover"]
    assert parse_bundle(instructed(bundle)).takeover is not None


class World:
    def __init__(self) -> None:
        self.clock = FakeClock(AT)
        self.persistence = MemoryPersistence()
        self.ledger = ChainedLedger(MemoryLedgerStore(self.persistence), self.clock)
        self.processes = MemoryRepository(self.persistence, Process)
        self.versions = MemoryRepository(self.persistence, ProcessVersion)
        self.trials = TakeoverTrials(
            self.processes,
            self.versions,
            MemoryRepository(self.persistence, TakeoverTrial),
            ledger=self.ledger,
            work=self.persistence,
            clock=self.clock,
            identifiers=FakeIdentifiers(),
        )

    async def register(self, bundle: dict[str, Any]) -> ProcessVersion:
        return await RegisterProcessVersionHandler(
            self.versions, self.persistence, self.processes, ledger=self.ledger, clock=self.clock
        ).execute(RegisterProcessVersion(bundle, tenant=TENANT, by="idn_a", approved_by="idn_a"))


async def test_a_trial_is_kept_with_the_version_names_a_role_and_is_a_ledger_entry() -> None:
    world = World()
    await world.register(two_steps())
    trial = await world.trials.record(
        RecordTrial(
            tenant=TENANT,
            process_id="p",
            role="owner",
            passed=False,
            missing=("where the issue number comes from", " "),
            by="idn_a",
        )
    )
    assert (trial.process_version, trial.role, trial.passed) == ("p@1", "owner", False)
    assert trial.at >= AT
    assert trial.missing == ("where the issue number comes from",)
    assert "idn_a" not in trial.model_dump_json(), "a trial names a role, never a person"
    read = await world.trials.read(TENANT, "p")
    assert read is not None and [t["id"] for t in read["trials"]] == [trial.id]
    async with world.persistence.transaction(TENANT):
        entries = await world.ledger.entries(TENANT, None)
    recorded = [e for e in entries if e.kind == TRIAL]
    assert [(e.outcome, e.refs.process_version, e.refs.actor) for e in recorded] == [
        ("failed", "p@1", "idn_a")
    ]


async def test_a_version_above_level_2_without_a_passed_trial_on_it_is_untried() -> None:
    world = World()
    at_two = await world.register({**two_steps(level=2), "id": "q"})
    assert not await world.trials.untried(TENANT, at_two)
    at_three = await world.register(two_steps(level=3))
    assert await world.trials.untried(TENANT, at_three)
    await world.trials.record(RecordTrial(TENANT, "p", "owner", passed=False, by="idn_a"))
    assert await world.trials.untried(TENANT, at_three), "a failed trial is no pass"
    await world.trials.record(RecordTrial(TENANT, "p", "owner", passed=True, by="idn_a"))
    assert not await world.trials.untried(TENANT, at_three)
    next_one = await world.register(two_steps(level=3, version="2"))
    assert await world.trials.untried(TENANT, next_one), "a pass on an earlier version is not one"


async def test_a_trial_of_a_process_without_an_active_version_is_refused() -> None:
    with pytest.raises(InvalidProcess, match="no active version"):
        await World().trials.record(RecordTrial(TENANT, "nothing", "owner", passed=True))
