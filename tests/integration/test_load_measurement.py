"""S-04: how many concurrent runs one instance carries, at which latency (ADR-0223).

A daemon with the `runner` role serves a database of this test's own. `taktusctl load measure`
submits the shipped probe at two levels of concurrency against it and waits for every run. The
measurement names the machine, and per level the runs, their states, the median, 95th
percentile and longest latency, and the throughput. Every run finished; the latencies are read
from the runs' own records, so each lies between zero and the time the command took.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from collections.abc import Callable
from pathlib import Path

from fakes.identity import added_by_command_line

from taktus.adapters.driving.cli.load_command import level_of, percentile

from .test_daemon_scaling import Instance, instances  # noqa: F401 — the fixture
from .test_first_slice import PLAIN, taktusctl

PROBE = (
    Path(__file__).resolve().parents[2] / "blueprints/self-operation/processes/S-04-load-probe.yaml"
)


async def test_the_instance_carries_each_level_and_says_at_which_latency(
    postgres_url: str,
    tmp_path: Path,
    instances: Callable[..., Instance],  # noqa: F811
) -> None:
    env = {
        **os.environ,
        **PLAIN,
        "TAKTUS_DATABASE_URL": postgres_url,
        "TAKTUS_STATE_DIR": str(tmp_path / "cli"),
    }
    added_by_command_line(taktusctl(), "idn_test", env)
    out = tmp_path / "load.json"
    async with instances("load", TAKTUS_ROLES="runner", TAKTUS_RUNNER_CONCURRENCY="4"):
        began = time.monotonic()
        measuring = await asyncio.create_subprocess_exec(
            taktusctl(),
            "load",
            "measure",
            "--process",
            str(PROBE),
            "--levels",
            "1,6",
            "--timeout",
            "120",
            "--out",
            str(out),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        printed, said = await asyncio.wait_for(measuring.communicate(), timeout=180)
        took = time.monotonic() - began
    assert measuring.returncode == 0, printed.decode() + said.decode()
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["format"] == "taktus.load-measurement/1"
    assert report["process"] == "s04-load-probe@1"
    assert report["hardware"]["processors"] and report["hardware"]["architecture"]
    one, six = report["levels"]
    assert (one["concurrency"], one["runs"], six["concurrency"], six["runs"]) == (1, 1, 6, 6)
    for level in (one, six):
        assert level["states"] == {"finished": level["runs"]}
        latency = level["latency_seconds"]
        assert 0 <= latency["median"] <= latency["p95"] <= latency["max"] <= took
        assert (
            level["throughput_runs_per_second"] is None or level["throughput_runs_per_second"] > 0
        )
    assert "6 at once: median" in printed.decode()


def test_the_figures_are_nearest_rank_percentiles_of_the_runs_records() -> None:
    assert percentile([0.3, 0.1, 0.2], 0.5) == 0.2
    assert percentile([float(n) for n in range(1, 21)], 0.95) == 19.0
    assert percentile([5.0], 0.95) == 5.0
    from datetime import UTC, datetime, timedelta

    from taktus.components.run.domain.model import RunState

    class Seen:
        def __init__(self, start: int, end: int) -> None:
            at = datetime(2026, 11, 7, tzinfo=UTC)
            self.created_at = at + timedelta(seconds=start)
            self.updated_at = at + timedelta(seconds=end)
            self.state = RunState.FINISHED

    figures = level_of(2, [Seen(0, 2), Seen(0, 4)])  # type: ignore[list-item]
    assert figures["latency_seconds"] == {"median": 2.0, "p95": 4.0, "max": 4.0}
    assert figures["throughput_runs_per_second"] == 0.5 and figures["states"] == {"finished": 2}
