"""Taktus can still develop itself: the self-development bundles, replayed from recordings of
real runs (ADR-0108, ADR-0096 §1 ring 3, issue #393).

P-01, P-02, P-03 and S-07 are registered as they are in `blueprints/` and run once each, as a
rehearsal against a database, with every step that would leave the engine answered by the
recorded result of the same step (`tests/rehearsal/recordings/`). Rules, admission, the step
boundaries, conditions and the engine's handling run for real. Every step must reach the state
it reached in the recorded run.

The deliberate breaks below show that the replay turns red, and names the step, when a bundle
changes what a step sends, when a recorded answer no longer leads where it led, and when an
answer is missing. `make rehearse` runs this file, as CI's lane `rehearse` does on a pull
request that touches what it replays and on every commit on `main`; it needs no credential and
reaches nothing outside.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from taktus.composition.replay import Replayed, bundle_of, replay, stores

ROOT = Path(__file__).resolve().parents[2]
RECORDINGS = Path(__file__).resolve().parent / "recordings"
BUNDLES = {
    "p01-roadmap-control": "dev-orchestration/processes/P-01-roadmap-control.yaml",
    "p02-refinement": "dev-orchestration/processes/P-02-refinement.yaml",
    "p03-implementation": "dev-orchestration/processes/P-03-implementation.yaml",
    "s07-change-in-dialogue": "self-operation/processes/S-07-change-in-dialogue.yaml",
}


def bundle(process: str) -> dict[str, Any]:
    return bundle_of(ROOT / "blueprints" / BUNDLES[process])


async def replayed(
    database: str, process: str, document: dict[str, Any], directory: Path | None = None
) -> Replayed:
    async with stores(database) as store:
        return await replay(document, directory or RECORDINGS / process, store)


@pytest.mark.parametrize("process", sorted(BUNDLES))
async def test_every_step_reaches_its_end_as_recorded(postgres_url: str, process: str) -> None:
    done = await replayed(postgres_url, process, bundle(process))
    assert done.held, f"{process} replayed differently:\n" + "\n".join(done.differences)
    assert done.run.rehearsal, "a replay is a rehearsal, marked as one wherever it is recorded"


def test_every_recording_is_of_a_bundle_and_every_bundle_has_one() -> None:
    assert sorted(p.name for p in RECORDINGS.iterdir() if p.is_dir()) == sorted(BUNDLES)
    for process in BUNDLES:
        recorded = json.loads((RECORDINGS / process / "recording.json").read_text())
        assert recorded["process"] == bundle(process)["id"] == process


def test_the_readme_says_where_each_recording_was_taken() -> None:
    """The table of `recordings/README.md` names each process with where its recording was
    taken, as the recording says it: a recording replaced from the instance cannot leave the
    table saying `local`, nor the other way round. #393 is complete when every row says
    `instance`."""
    table: dict[str, str] = {}
    for line in (RECORDINGS / "README.md").read_text(encoding="utf-8").splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) == 3 and cells[1] in ("`local`", "local", "instance", "`instance`"):
            table[cells[0].strip("`")] = cells[1].strip("`")
    recorded = {
        process: json.loads((RECORDINGS / process / "recording.json").read_text())["taken"]
        for process in BUNDLES
    }
    assert table == recorded


async def test_a_bundle_that_sends_something_else_turns_the_replay_red(postgres_url: str) -> None:
    """A deliberate break of a bundle: P-02 reads the comments with one more field. The step
    sends another input than the recorded step sent, and fails, naming the part that differs.
    The step is one every run of P-02 takes, so the break bites whatever the recorded issue
    held."""
    document = bundle("p02-refinement")
    comments = next(s for s in document["steps"] if s["id"] == "read-comments")
    comments["work"]["input"]["per_page"] = 50
    done = await replayed(postgres_url, "p02-refinement", document)
    assert not done.held
    (line,) = [d for d in done.differences if d.startswith("read-comments:")]
    assert "replayed failed" in line and "input" in line and "differs" in line, done.differences


async def test_a_recorded_answer_that_leads_elsewhere_turns_the_replay_red(
    postgres_url: str, tmp_path: Path
) -> None:
    """A deliberate break of a recorded answer: the issue P-03 read lost its label `ready`. The
    rule that admits it refuses it now, and the replay names the step and the run."""
    directory = tmp_path / "p03-implementation"
    shutil.copytree(RECORDINGS / "p03-implementation", directory)
    path = directory / "results" / "read-issue.json"
    result = json.loads(path.read_text(encoding="utf-8"))
    result["output"]["labels"] = [label for label in result["output"]["labels"] if label != "ready"]
    path.write_text(json.dumps(result), encoding="utf-8")
    done = await replayed(
        postgres_url, "p03-implementation", bundle("p03-implementation"), directory
    )
    assert not done.held
    assert any(d.startswith("admit: recorded succeeded, replayed failed") for d in done.differences)
    assert any(d.startswith("the run: recorded finished") for d in done.differences)


async def test_a_step_without_its_recorded_answer_turns_the_replay_red(
    postgres_url: str, tmp_path: Path
) -> None:
    """A deliberate break of the recording: S-07's model answer is gone. The step fails, and
    the reason says the recording holds no answer for its prompt."""
    directory = tmp_path / "s07-change-in-dialogue"
    shutil.copytree(RECORDINGS / "s07-change-in-dialogue", directory)
    recording = json.loads((directory / "recording.json").read_text(encoding="utf-8"))
    for step in recording["steps"]:
        if step["id"] == "propose":
            del step["answer"]
    (directory / "recording.json").write_text(json.dumps(recording), encoding="utf-8")
    done = await replayed(
        postgres_url, "s07-change-in-dialogue", bundle("s07-change-in-dialogue"), directory
    )
    assert not done.held
    assert any(
        d.startswith("propose: recorded succeeded, replayed failed") for d in done.differences
    )


def test_the_recordings_carry_what_a_recording_may_carry() -> None:
    """Content-free where the ledger is: no request is kept, only its digests; no person is
    named; every file a recording names is there."""
    for process in BUNDLES:
        directory = RECORDINGS / process
        recorded = json.loads((directory / "recording.json").read_text(encoding="utf-8"))
        text = json.dumps(recorded)
        assert "idn_" not in text, f"{process} names an identity"
        for step in recorded["steps"]:
            answer = step.get("answer")
            if answer is None:
                continue
            assert set(answer["request"]) == {"digest", "parts"}, step["id"]
            for name in [answer.get("result"), *(a["file"] for a in answer.get("artifacts", []))]:
                if name is not None:
                    assert (directory / name).is_file(), f"{process}: {name}"
