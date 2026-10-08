"""The coding worker against its real agent, under the cap of the environment `live` (#68).

The conformance suite runs the coding worker against a stand-in that imitates the agent's
output (`tests/conformance/test_worker_v1_coding.py`). That proves the worker's mechanics. It
does not prove that the real agent still behaves the way the worker reads it; the first live run
found such a gap (DEC-0038). This file holds the live test that does, and the tests that prove
its wiring without spending anything.

**What the live test does.** One run of a one-step process through `taktusctl run`: the coding
worker writes one file in an empty workspace. The run's budget is the cap per run, converted
into tokens. The run's ledger, its output and the worker's log are kept as the run's evidence.

**How the cap becomes a budget.** The worker learns what an assignment cost only when the
assignment ends. A limit in money therefore cannot stop it while it runs; a limit in tokens can
(`workers/claudecode/README.md`, *Consumption*; ADR-0005, third amendment). So the cap is
converted into input tokens at the dearest rate the real agent has been measured at, rounded
up: `USD_PER_TOKEN` (NTC-0028).

- The **line** is the cap at that rate: the most input tokens the run may use. It is the run's
  token budget, beside the cap itself as the run's money budget.
- The worker's **ceiling** is the line less `YIELD_SHARE`. The worker halts at the first step
  boundary where its running total has reached its ceiling; the call that crossed it has already
  run. That one call is what the held-back share is for, so that the run halts before the line.
- The worker's **estimate** is the ceiling divided by the factor the run will reserve for a
  worker with no history (`scale_for`, DEC-0034). The reservation is then the ceiling.

**When it runs.** Only where the credential file and the cap are both set — in the workflow
`live`, on `main`, monthly and by dispatch (DEC-0048, DEC-0058). Without either, it skips and
says which. With `TAKTUS_REQUIRE_LIVE` set, as the workflow sets it, a missing one fails the
test instead. A cap that is set and is not a positive number of US dollars always fails.

    TAKTUS_CREDENTIAL_CODING_AGENT_API_KEY_FILE   the file that holds the agent's API key
    LIVE_SPEND_CAP_USD                            the most one run may spend, e.g. 0.50
    TAKTUS_LIVE_EVIDENCE                          where the evidence goes; default a temporary
                                                  directory
"""

from __future__ import annotations

import json
import math
import os
import shutil
import socket
import subprocess
import sys
import time
from collections.abc import Iterator, Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml

from taktus.components.run.domain.service.budget import scale_for
from taktus.shared.v1 import Method

type Json = dict[str, Any]

ROOT = Path(__file__).resolve().parents[2]
WORKER = ROOT / "workers" / "claudecode" / "worker.py"
FAKE_AGENT = ROOT / "workers" / "claudecode" / "fake_agent.py"

CAP_VARIABLE = "LIVE_SPEND_CAP_USD"
CREDENTIAL = "CODING_AGENT_API_KEY"
CREDENTIAL_FILE = "TAKTUS_CREDENTIAL_CODING_AGENT_API_KEY_FILE"
EVIDENCE_VARIABLE = "TAKTUS_LIVE_EVIDENCE"
REQUIRE_VARIABLE = "TAKTUS_REQUIRE_LIVE"
AGENT = "claude"
"""The agent's command, as the worker runs it by default (`workers/claudecode/README.md`)."""

USD_PER_TOKEN = 8e-6
"""The dearest rate the real agent has been measured at, rounded up: USD 0.833 for 110 615
tokens, USD 7.53 per million, in the first live run's third attempt (docs/runs/first-run.md
§2). The rate counts every input token — uncached, written to the cache, read from it — the way
the worker reports them, and the money includes the output. It is evidence, not a price list:
the money of the eight attempts varied by 2.4 times against their tokens. The workspace's
monthly spend limit at the provider is the backstop behind it (NEED-0012)."""

YIELD_SHARE = 0.25
"""The share of the line held back for the one call the worker's limit yields by. A call of
the agent in the first live run read 11 000 to 18 000 tokens; a quarter of the line at a cap of
USD 0.50 is 15 600."""

CAPABILITIES = ("code.read", "code.edit")
"""What writing one file needs, and nothing more: least privilege."""

FILE = "hello.txt"
CONTENT = "hello, world"
TASK: Json = {
    "goal": (
        f"Create the file {FILE} in the workspace, containing exactly the line "
        f"'{CONTENT}'. The workspace is empty: do not look around it. Write the file with "
        "one call, then stop."
    ),
    "acceptance": [f"the workspace contains {FILE}, whose only line is '{CONTENT}'"],
    "inputs": {},
}


class CapRefused(ValueError):
    """The cap is set and is not a positive number of US dollars."""


def cap_of(environ: Mapping[str, str]) -> float | None:
    """The cap per run in US dollars, or None where it is not set. A value that is set and is
    not a positive, finite number is refused: a cap that cannot be read is not a cap."""
    raw = environ.get(CAP_VARIABLE, "").strip()
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError:
        raise CapRefused(f"{CAP_VARIABLE}={raw!r} is not a number of US dollars") from None
    if not math.isfinite(value) or value <= 0:
        raise CapRefused(f"{CAP_VARIABLE}={raw!r} is not a positive amount of US dollars")
    return value


def missing(environ: Mapping[str, str]) -> str | None:
    """Why the live test cannot run here, or None when it can."""
    absent = [name for name in (CREDENTIAL_FILE, CAP_VARIABLE) if not environ.get(name)]
    if absent:
        return (
            "the live test of the coding worker needs "
            + " and ".join(absent)
            + " (tests/workers/test_coding_worker_live.py)"
        )
    if not Path(environ[CREDENTIAL_FILE]).is_file():
        return f"{CREDENTIAL_FILE} names no file"
    if shutil.which(AGENT) is None:
        return f"the agent's command {AGENT!r} is not on the path"
    return None


@dataclass(frozen=True)
class Budget:
    """The cap converted: the run's budget, the worker's ceiling and the worker's estimate."""

    cap_usd: float
    usd_per_token: float
    line_tokens_in: int
    ceiling_tokens_in: int
    factor_tokens_in: float
    factor_currency: float
    estimate_tokens_in: int
    estimate_tokens_out: int
    estimate_currency: float
    estimate_steps: int
    estimate_wall_seconds: int
    max_steps: int

    def limits(self) -> Json:
        """The run's budget: the cap in money, and the line in input tokens."""
        return {"currency": {"usd": self.cap_usd}, "tokens": {"in": self.line_tokens_in}}

    def worker_options(self) -> list[str]:
        return [
            "--estimate-tokens-in",
            str(self.estimate_tokens_in),
            "--estimate-tokens-out",
            str(self.estimate_tokens_out),
            "--estimate-currency",
            f"{self.estimate_currency:.2f}",
            "--estimate-steps",
            str(self.estimate_steps),
            "--estimate-wall-seconds",
            str(self.estimate_wall_seconds),
            "--max-turns",
            str(self.max_steps),
        ]


def budget_of(cap_usd: float, capabilities: tuple[str, ...] = CAPABILITIES) -> Budget:
    """Convert the cap. The factors are the ones the run applies to a worker with no history
    for these capabilities — the seed of the first live run where it applies, twice the
    estimate otherwise — so that the reservation is the ceiling and never more."""
    line = math.floor(cap_usd / USD_PER_TOKEN)
    ceiling = math.floor(line * (1 - YIELD_SHARE))
    scale, _ = scale_for("worker.endpoint", Method.WORKER, capabilities, ())
    factor_in = scale.get("tokens_in", 1.0)
    factor_currency = scale.get("currency.*", 1.0)
    # Cents, rounded down, so that the reserved money stays inside the ceiling's share.
    currency = math.floor(100 * cap_usd * (1 - YIELD_SHARE) / factor_currency) / 100
    return Budget(
        cap_usd=cap_usd,
        usd_per_token=USD_PER_TOKEN,
        line_tokens_in=line,
        ceiling_tokens_in=ceiling,
        factor_tokens_in=factor_in,
        factor_currency=factor_currency,
        estimate_tokens_in=math.floor(ceiling / factor_in),
        estimate_tokens_out=2_000,
        estimate_currency=currency,
        estimate_steps=4,
        estimate_wall_seconds=300,
        max_steps=10,
    )


def bundle(budget: Budget, capabilities: tuple[str, ...] = CAPABILITIES) -> Json:
    """The process the live test runs: one worker step, the budget the cap converts to."""
    return {
        "id": "live-coding-worker",
        "version": "1",
        "name": "Live test of the coding worker",
        "autonomy": {
            "level": 2,
            "reason": (
                "a test: it writes one file in an empty workspace and hands nothing outward; "
                "the job's evidence is read by a person"
            ),
            "toward_next": "none sought; a test is read, not operated",
        },
        "author": "the repository",
        "reason": "the coding worker against its real agent, under the cap (#68)",
        "limits": budget.limits(),
        "steps": [
            {
                "id": "write-file",
                "method": "worker",
                "reason": (
                    "the coding worker is what is tested; the assignment is the smallest one "
                    "that makes the agent use a tool"
                ),
                "rejected": [
                    {"method": "rule", "why": "a rule would test nothing of the agent"},
                ],
                "exactness": "tolerant",
                "fallback": {"when": "the assignment fails or is stopped", "to": "human"},
                "requires": list(capabilities),
                "work": {
                    "task": TASK,
                    "max_steps": budget.max_steps,
                    "credentials": [{"name": CREDENTIAL, "injected_as": "env"}],
                },
            }
        ],
    }


@dataclass(frozen=True)
class Outcome:
    returncode: int
    output: str
    ledger: list[Json]
    evidence: Path

    def step(self, kind: str) -> Json:
        return next(e for e in self.ledger if is_step(e, kind))


def step_of(entry: Json) -> str | None:
    return (entry.get("refs") or {}).get("step_id")


def is_step(entry: Json, kind: str) -> bool:
    return bool(entry["kind"] == kind and step_of(entry) == "write-file")


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def taktusctl() -> str:
    path = shutil.which("taktusctl")
    assert path is not None, "taktusctl is not on the path; run under `uv run`"
    return path


def run_under_cap(
    evidence: Path,
    *,
    cap_usd: float,
    credential_value: str,
    agent: str = AGENT,
    capabilities: tuple[str, ...] = CAPABILITIES,
    agent_env: Mapping[str, str] | None = None,
    worker_state: Path,
) -> Outcome:
    """Start the coding worker with the converted estimate, run the bundle through `taktusctl
    run` with the converted budget, and keep what the run leaves under `evidence`. The
    worker's state — workspaces, checkpoints, the agent's own configuration — stays outside the
    evidence: the agent's configuration is not the repository's to publish."""
    evidence.mkdir(parents=True, exist_ok=True)
    budget = budget_of(cap_usd, capabilities)
    (evidence / "budget.json").write_text(json.dumps(asdict(budget), indent=2) + "\n")
    process = evidence / "bundle.yaml"
    process.write_text(yaml.safe_dump(bundle(budget, capabilities), sort_keys=False))
    port = free_port()
    env = {**os.environ, CREDENTIAL: credential_value, **(agent_env or {})}
    env.pop(CREDENTIAL_FILE, None)
    args = [
        sys.executable,
        str(WORKER),
        "--port",
        str(port),
        "--auth",
        "api-key",
        "--agent",
        agent,
        "--state-dir",
        str(worker_state),
        "--agent-env",
        ",".join(agent_env or {}),
        *budget.worker_options(),
    ]
    log = evidence / "worker.log"
    with log.open("wb") as handle:
        worker = subprocess.Popen(  # noqa: S603 — our own script, fixed arguments
            args, stdout=handle, stderr=subprocess.STDOUT, env=env
        )
    try:
        wait_ready(worker, f"http://127.0.0.1:{port}/v1/health", log)
        completed = subprocess.run(  # noqa: S603 — our own entry point, fixed arguments
            [
                taktusctl(),
                "run",
                "--process",
                str(process),
                "--worker",
                f"http://127.0.0.1:{port}",
                "--state-dir",
                str(evidence / "state"),
            ],
            capture_output=True,
            text=True,
            env={
                **{k: v for k, v in os.environ.items() if k not in (CREDENTIAL, CREDENTIAL_FILE)},
                "TAKTUS_PROVISIONAL_IDENTITY": "default=idn_live",
                "NO_COLOR": "1",
                "TERM": "dumb",
            },
            timeout=budget.estimate_wall_seconds * 2,
            check=False,
        )
    finally:
        worker.terminate()
        try:
            worker.wait(timeout=10)
        except subprocess.TimeoutExpired:
            worker.kill()
    output = completed.stdout + completed.stderr
    (evidence / "run.txt").write_text(output)
    ledger_file = evidence / "state" / "ledger.json"
    ledger = json.loads(ledger_file.read_text())["default"] if ledger_file.is_file() else []
    outcome = Outcome(completed.returncode, output, ledger, evidence)
    (evidence / "summary.md").write_text(summary(budget, outcome))
    leaked = [p for p in evidence.rglob("*") if p.is_file() and contains(p, credential_value)]
    for path in leaked:
        path.unlink()
    assert not leaked, f"the credential's value was found in {leaked}; the files were removed"
    return outcome


def contains(path: Path, value: str) -> bool:
    return value.encode() in path.read_bytes()


def wait_ready(process: subprocess.Popen[bytes], url: str, log: Path) -> None:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"the coding worker exited early; see {log}")
        try:
            if httpx.get(url, timeout=1.0).status_code == 200:
                return
        except httpx.HTTPError:
            time.sleep(0.1)
    raise RuntimeError(f"the coding worker did not become ready; see {log}")


def quantities(entry: Json | None) -> Json:
    return (entry or {}).get("consumption") or {}


def summary(budget: Budget, outcome: Outcome) -> str:
    """The tokens against the estimate, for the job's summary page and the issue."""
    admitted = quantities(next((e for e in outcome.ledger if is_step(e, "step.admitted")), None))
    used = quantities(next((e for e in outcome.ledger if is_step(e, "step.finished")), None))
    state = next(
        (line for line in outcome.output.splitlines() if line.startswith("run ")), "no run"
    )
    rows = [
        ("the cap per run", f"USD {budget.cap_usd:.2f}"),
        ("the line: the cap at the rate", f"{budget.line_tokens_in} tokens in"),
        ("the worker's ceiling", f"{budget.ceiling_tokens_in} tokens in"),
        ("the worker's estimate, as the ledger admitted it", json.dumps(admitted)),
        ("what the worker used, as the ledger finished it", json.dumps(used)),
    ]
    table = "\n".join(f"| {name} | {value} |" for name, value in rows)
    return (
        "## The coding worker against its real agent\n\n"
        f"`{state}`\n\n| | |\n|---|---|\n{table}\n\n"
        "The ledger, the run's output and the worker's log are the job's artifact.\n"
    )


def changed_files(outcome: Outcome) -> dict[str, str]:
    """The files the worker's changeset carries, by path, from the run's stored artifacts."""
    for path in sorted((outcome.evidence / "state").rglob("*")):
        if not path.is_file():
            continue
        try:
            document = json.loads(path.read_text())
        except (ValueError, UnicodeDecodeError):
            continue
        found = find_changeset(document)
        if found is not None:
            return found
    return {}


def find_changeset(node: Any) -> dict[str, str] | None:
    if isinstance(node, dict):
        files = node.get("files")
        if isinstance(files, list) and all(isinstance(f, dict) and "path" in f for f in files):
            if "deleted" in node:
                return {f["path"]: str(f.get("content", "")) for f in files}
        for value in node.values():
            found = find_changeset(value)
            if found is not None:
                return found
    elif isinstance(node, list):
        for value in node:
            found = find_changeset(value)
            if found is not None:
                return found
    elif isinstance(node, str) and node.startswith("{") and '"deleted"' in node:
        try:
            return find_changeset(json.loads(node))
        except ValueError:
            return None
    return None


# --- the live test -------------------------------------------------------------------------


@pytest.fixture
def live(tmp_path: Path) -> Iterator[tuple[float, str, Path]]:
    """The cap, the credential's value and where the evidence goes — or a skip naming what is
    missing, a failure where the live test is required."""
    cap = cap_of(os.environ)  # a cap that is set and unreadable fails here, never skips
    reason = missing(os.environ)
    if reason is not None:
        if os.environ.get(REQUIRE_VARIABLE):
            pytest.fail(f"{REQUIRE_VARIABLE} is set and {reason}")
        pytest.skip(reason)
    assert cap is not None
    value = Path(os.environ[CREDENTIAL_FILE]).read_text().strip()
    configured = os.environ.get(EVIDENCE_VARIABLE)
    yield cap, value, Path(configured) if configured else tmp_path / "evidence"


def test_the_coding_worker_against_its_real_agent_under_the_cap(
    live: tuple[float, str, Path], tmp_path: Path
) -> None:
    cap, value, evidence = live
    outcome = run_under_cap(
        evidence,
        cap_usd=cap,
        credential_value=value,
        worker_state=tmp_path / "worker-state",
    )
    budget = budget_of(cap)
    assert outcome.returncode == 0, outcome.output
    assert "state finished" in outcome.output, outcome.output
    assert "DOES NOT VERIFY" not in outcome.output, outcome.output
    used = quantities(outcome.step("step.finished"))
    assert used.get("tokens_in", 0) > 0, "the real agent's tokens were counted"
    assert used.get("tokens_in", 0) <= budget.line_tokens_in, "the run stayed inside its line"
    assert (used.get("currency") or {}).get("usd", 0) > 0, "the agent's money was reported"
    files = changed_files(outcome)
    assert files.get(FILE, "").strip() == CONTENT, files


# --- the wiring, without the key ------------------------------------------------------------


@pytest.mark.parametrize(
    ("cap", "line", "ceiling"),
    [(0.50, 62_500, 46_875), (1.00, 125_000, 93_750), (0.08, 10_000, 7_500)],
)
def test_the_cap_becomes_a_line_and_a_ceiling_the_worker_halts_at(
    cap: float, line: int, ceiling: int
) -> None:
    budget = budget_of(cap)
    assert budget.limits() == {"currency": {"usd": cap}, "tokens": {"in": line}}
    assert budget.line_tokens_in * USD_PER_TOKEN <= cap
    assert budget.ceiling_tokens_in == ceiling
    # A worker with no history reserves twice its estimate (DEC-0034): the reservation is the
    # ceiling, rounded down, and the money reserved stays inside the ceiling's share of the cap.
    assert budget.factor_tokens_in == 2.0
    assert math.ceil(budget.estimate_tokens_in * budget.factor_tokens_in) <= ceiling
    assert budget.estimate_currency * budget.factor_currency <= cap * (1 - YIELD_SHARE)
    assert budget.estimate_steps <= budget.max_steps


def test_the_conversion_follows_the_seed_where_it_applies() -> None:
    """Where the step requires what the first live run's seed covers, the run reserves the
    seed's measured error; the estimate shrinks so that the reservation is still the ceiling."""
    seeded = budget_of(0.50, ("code.read", "code.edit", "code.test", "shell.sandboxed"))
    assert seeded.factor_tokens_in > 4
    assert math.ceil(seeded.estimate_tokens_in * seeded.factor_tokens_in) <= 46_875


@pytest.mark.parametrize("raw", ["", "  "])
def test_no_cap_is_none(raw: str) -> None:
    assert cap_of({CAP_VARIABLE: raw}) is None
    assert cap_of({}) is None


@pytest.mark.parametrize("raw", ["abc", "0", "-0.5", "nan", "inf", "0,50"])
def test_a_cap_that_is_not_a_positive_amount_is_refused(raw: str) -> None:
    with pytest.raises(CapRefused, match=CAP_VARIABLE):
        cap_of({CAP_VARIABLE: raw})


def test_the_live_test_names_what_it_misses(tmp_path: Path) -> None:
    key = tmp_path / "key"
    key.write_text("not a key")
    assert CREDENTIAL_FILE in (missing({CAP_VARIABLE: "0.5"}) or "")
    assert CAP_VARIABLE in (missing({CREDENTIAL_FILE: str(key)}) or "")
    both = missing({}) or ""
    assert CREDENTIAL_FILE in both and CAP_VARIABLE in both
    assert "names no file" in (
        missing({CREDENTIAL_FILE: str(tmp_path / "absent"), CAP_VARIABLE: "0.5"}) or ""
    )


def test_without_the_credential_it_skips_and_where_required_it_fails(tmp_path: Path) -> None:
    """The live test run on its own, in a fresh interpreter, with the cap and without the
    credential: it skips naming the credential; with `TAKTUS_REQUIRE_LIVE` it fails. With a
    cap that cannot be read it fails whether required or not."""
    base = {
        k: v
        for k, v in os.environ.items()
        if k not in (CREDENTIAL_FILE, CAP_VARIABLE, REQUIRE_VARIABLE)
    }
    test = f"{Path(__file__)}::test_the_coding_worker_against_its_real_agent_under_the_cap"

    def pytest_run(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(  # noqa: S603 — the interpreter running this test, fixed arguments
            [sys.executable, "-m", "pytest", test, "-rs", "-p", "no:cacheprovider"],
            capture_output=True,
            text=True,
            env=env,
            cwd=tmp_path,
            check=False,
        )

    skipped = pytest_run({**base, CAP_VARIABLE: "0.50"})
    assert skipped.returncode == 0 and "1 skipped" in skipped.stdout, skipped.stdout
    assert CREDENTIAL_FILE in skipped.stdout
    required = pytest_run({**base, CAP_VARIABLE: "0.50", REQUIRE_VARIABLE: "1"})
    assert required.returncode == 1 and CREDENTIAL_FILE in required.stdout, required.stdout
    unreadable = pytest_run({**base, CAP_VARIABLE: "half a dollar"})
    assert unreadable.returncode == 1 and "not a number" in unreadable.stdout, unreadable.stdout


@pytest.mark.skipif(shutil.which("git") is None, reason="the coding worker needs git")
def test_the_harness_runs_end_to_end_against_the_stand_in(tmp_path: Path) -> None:
    """The live test's own harness with the stand-in for the agent and a small usage: the run
    finishes, the ledger shows the step admitted, reserved and finished with its tokens, the
    evidence carries the ledger, the bundle, the conversion and the summary, and the
    credential's value is in none of it. The stand-in's fixed plan uses the shell, so the step
    is given it here."""
    value = "live-" + os.urandom(12).hex()
    outcome = run_under_cap(
        tmp_path / "evidence",
        cap_usd=0.50,
        credential_value=value,
        agent=f"{sys.executable} {FAKE_AGENT}",
        capabilities=(*CAPABILITIES, "shell.sandboxed"),
        agent_env={"FAKE_AGENT_USAGE_FACTOR": "0.01"},
        worker_state=tmp_path / "worker-state",
    )
    assert outcome.returncode == 0, outcome.output
    assert "state finished" in outcome.output
    kinds = [e["kind"] for e in outcome.ledger if step_of(e) == "write-file"]
    assert {"step.admitted", "step.reserved", "step.finished"} <= set(kinds), kinds
    assert quantities(outcome.step("step.finished")).get("tokens_in", 0) > 0
    assert changed_files(outcome).get(FILE, "").strip() == CONTENT
    for name in ("bundle.yaml", "budget.json", "run.txt", "summary.md", "worker.log"):
        assert (outcome.evidence / name).is_file(), name
    assert (outcome.evidence / "state" / "ledger.json").is_file()
    assert "tokens in" in (outcome.evidence / "summary.md").read_text()


@pytest.mark.skipif(shutil.which("git") is None, reason="the coding worker needs git")
def test_an_agent_that_overruns_halts_at_its_ceiling_inside_the_line(tmp_path: Path) -> None:
    """The stand-in at its full usage — about 6 000 to 32 000 input tokens a call — under the
    cap of USD 0.50: the worker halts at the first boundary where its total reached the ceiling
    of 46 875, and the call that crossed it stays inside the line of 62 500. The run halts with
    the limit as its cause; it does not finish and it does not cross the cap's line."""
    budget = budget_of(0.50, (*CAPABILITIES, "shell.sandboxed"))
    outcome = run_under_cap(
        tmp_path / "evidence",
        cap_usd=0.50,
        credential_value="live-" + os.urandom(12).hex(),
        agent=f"{sys.executable} {FAKE_AGENT}",
        capabilities=(*CAPABILITIES, "shell.sandboxed"),
        worker_state=tmp_path / "worker-state",
    )
    assert outcome.returncode == 3, outcome.output
    assert "state halted (limit)" in outcome.output, outcome.output
    finished = outcome.step("step.finished")
    assert finished.get("outcome") == "stopped", finished
    stopped = quantities(finished)
    assert budget.ceiling_tokens_in <= stopped["tokens_in"] <= budget.line_tokens_in, stopped
