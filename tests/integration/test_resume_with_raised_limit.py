"""A halted run continues with its money limit raised, by one command (#458, ADR-0005 §4).

`taktusctl resume --run RUN --raise AMOUNT --reason TEXT` raises the run's own limit and
continues it: no bundle is read and no version registered, the ledger's `budget.set` names the
statement with the limit before and the reason, and a raise past the operator's ceiling, or
without one, is refused. The example with a money limit halts at admission: a compute second
has no price without a price table. Its money limit is raised here, which does not lift that
halt, so the run halts again — what is proven is the raise, not the work.
"""

from __future__ import annotations

import json
import os
import subprocess
from decimal import Decimal
from pathlib import Path

import pytest
import yaml
from fakes.identity import added_by_command_line

from taktus.adapters.driving.cli.resume_command import RaiseRefused, ceiling_of, raised
from taktus.ports.worker import Limits

from .test_first_slice import EXAMPLE, PLAIN, taktusctl


def halted(worker_endpoint: str, tmp_path: Path) -> tuple[str, dict[str, str], Path]:
    """The example, with a money limit beside its compute limit, run until it halts."""
    bundle = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))
    bundle["limits"]["currency"] = {"usd": 1.0}
    path = tmp_path / "with-money.yaml"
    path.write_text(yaml.safe_dump(bundle), encoding="utf-8")
    env = {
        **os.environ,
        **PLAIN,
        "TAKTUS_WORKER": worker_endpoint,
        "TAKTUS_STATE_DIR": str(tmp_path / "state"),
    }
    env.pop("TAKTUS_RAISE_CEILING", None)
    added_by_command_line(taktusctl(), "idn_test", env)
    command = [taktusctl(), "run", "--process", str(path)]
    run_id = None
    for _ in range(8):
        done = subprocess.run(command, capture_output=True, text=True, env=env, check=False)  # noqa: S603
        if "state halted (" in done.stdout:
            run_id = next(x for x in done.stdout.splitlines() if x.startswith("run ")).split()[1]
            break
        waiting = [line for line in done.stdout.splitlines() if "waits for a person:" in line]
        assert waiting, done.stdout + done.stderr
        hint = waiting[0]
        run_id = hint.split("--resume ", 1)[1].split()[0]
        command = [
            taktusctl(),
            "run",
            "--process",
            str(path),
            "--resume",
            run_id,
            "--approve",
            hint.split()[-1],
        ]
    assert run_id is not None
    return run_id, env, tmp_path / "state"


def ledger(state: Path) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = json.loads((state / "ledger.json").read_text())["default"]
    return entries


def test_a_halted_run_continues_with_its_limit_raised_and_no_version_registered(
    worker_endpoint: str, tmp_path: Path
) -> None:
    run_id, env, state = halted(worker_endpoint, tmp_path)
    before = [e for e in ledger(state) if e["kind"] == "budget.set"]
    versions = [e for e in ledger(state) if e["kind"] == "process.version_registered"]
    env["TAKTUS_RAISE_CEILING"] = "5 usd"
    resumed = subprocess.run(  # noqa: S603 — our own entry point, fixed arguments
        [
            taktusctl(),
            "resume",
            "--run",
            run_id,
            "--raise",
            "1.5",
            "--reason",
            "larger than estimated",
        ],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert resumed.returncode == 3, resumed.stdout + resumed.stderr
    assert "{'usd': 1.0} -> {'usd': 2.5}, raised by idn_test" in resumed.stdout
    after = ledger(state)
    raised_entries = [e for e in after if e["kind"] == "budget.set"]
    assert len(raised_entries) == len(before) + 1
    entry = raised_entries[-1]
    assert entry["refs"]["actor"] == "idn_test"  # type: ignore[index]
    digest = str(entry["content_digest"]).removeprefix("sha256:")
    statement = json.loads((state / "objects" / digest).read_text(encoding="utf-8"))
    assert statement["budget"]["currency"] == {"usd": 2.5}
    assert statement["changed"] == {
        "from": {
            "currency": {"usd": 1.0},
            "compute": {"seconds": 2, "resource_class": "cpu.small"},
        },
        "reason": "larger than estimated",
    }
    assert [e for e in after if e["kind"] == "process.version_registered"] == versions
    assert all("larger than estimated" not in json.dumps(e) for e in after), "no text in the ledger"


def test_a_raise_without_a_ceiling_is_refused(worker_endpoint: str, tmp_path: Path) -> None:
    run_id, env, _ = halted(worker_endpoint, tmp_path)
    refused = subprocess.run(  # noqa: S603 — our own entry point, fixed arguments
        [taktusctl(), "resume", "--run", run_id, "--raise", "1", "--reason", "more"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert refused.returncode == 2
    assert "no raise without a ceiling" in refused.stderr


LIMIT = Limits.model_validate({"currency": {"usd": 5.0}})


def test_a_raise_is_held_to_the_ceiling_and_to_the_runs_currency() -> None:
    assert raised(LIMIT, Decimal("2"), ceiling_of("8 usd")).currency == {"usd": 7.0}
    with pytest.raises(RaiseRefused, match="exceed the ceiling"):
        raised(LIMIT, Decimal("4"), ceiling_of("8 usd"))
    with pytest.raises(RaiseRefused, match="the ceiling is in eur"):
        raised(LIMIT, Decimal("1"), ceiling_of("8 eur"))
    with pytest.raises(RaiseRefused, match="positive"):
        raised(LIMIT, Decimal("0"), ceiling_of("8 usd"))
    with pytest.raises(RaiseRefused, match="amount and a currency"):
        ceiling_of("8")
