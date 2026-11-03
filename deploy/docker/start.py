#!/usr/bin/env python3
"""`make start`: install Taktus on one machine in one command, and measure the time to a first
rehearsed process (UC-10.4, ADR-0136 §6).

It writes the secrets and builds the image as `make up` does, starts the two containers until
the instance is ready, and runs `taktusctl first start`, which creates the first tenant and its
administrator and prints the account key once. Then it keeps a clock: every five seconds it
asks `taktusctl first rehearsal` whether the tenant's first rehearsal has finished. When it has,
it prints the time since this command started, stage by stage, and writes what it measured to
`deploy/docker/first-process.json` (git ignores it). Ctrl-C stops the clock; Taktus keeps
running.

The record holds times, the machine's system, architecture and processor count, and whether
the time was within ten minutes. It never holds the account key, and it names no person.

Needs only what `make up` needs: docker with the compose plugin, and python3. Standard library
only. Exit code 0 once the rehearsal finished; 1 where it did not before `--give-up-after`; 2
where a stage of the install failed; 130 when the clock was stopped.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPOSE_YAML = ROOT / "deploy" / "docker" / "compose.yml"
CONNECTORS_YAML = ROOT / "deploy" / "docker" / "compose.connectors.yml"
"""The operator's further connectors, written from connectors.json (connectors.py)."""
RECORD = ROOT / "deploy" / "docker" / "first-process.json"
TEN_MINUTES = 600
POLL_SECONDS = 5


def now() -> datetime:
    return datetime.now(UTC)


def port_of(given: str | None) -> str:
    """The published port: given, from the environment, from deploy/docker/.env, or 8080."""
    if given:
        return given
    if os.environ.get("TAKTUS_HTTP_PORT"):
        return os.environ["TAKTUS_HTTP_PORT"]
    settings = ROOT / "deploy" / "docker" / ".env"
    if settings.is_file():
        for line in settings.read_text(encoding="utf-8").splitlines():
            name, _, value = line.partition("=")
            if name.strip() == "TAKTUS_HTTP_PORT" and value.strip():
                return value.strip()
    return "8080"


class Install:
    def __init__(self, project: str | None, port: str) -> None:
        self.compose = ["docker", "compose", "-f", str(COMPOSE_YAML)]
        if CONNECTORS_YAML.is_file():
            self.compose += ["-f", str(CONNECTORS_YAML)]
        if project:
            self.compose += ["-p", project]
        self.environment = {**os.environ, "TAKTUS_HTTP_PORT": port}

    def run(self, *arguments: str, capture: bool = False) -> subprocess.CompletedProcess[str]:
        return subprocess.run(  # noqa: S603 — fixed commands of this repository
            list(arguments),
            cwd=ROOT,
            env=self.environment,
            text=True,
            capture_output=capture,
            check=False,
        )

    def taktusctl(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return self.run(
            *self.compose, "exec", "-T", "taktus", "taktusctl", *arguments, capture=True
        )


def stage(name: str, result: subprocess.CompletedProcess[str]) -> None:
    if result.returncode != 0:
        if result.stderr:
            sys.stderr.write(result.stderr)
        print(f"start: {name} failed (exit code {result.returncode}); Taktus is not installed")
        sys.exit(2)


def seconds(start: datetime, end: datetime | None) -> float | None:
    return None if end is None else round((end - start).total_seconds(), 1)


def main() -> int:
    # Each line reaches the person, or the file the output goes to, as it is printed: the key
    # and the instructions must not wait in a buffer behind the clock.
    sys.stdout.reconfigure(line_buffering=True)  # type: ignore[union-attr]
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--name", default="My organisation", help="the first tenant's name")
    parser.add_argument("--project", default=None, help="a compose project of its own")
    parser.add_argument("--port", default=None, help="the port the web app is published on")
    parser.add_argument("--record", default=str(RECORD), help="where the measurement is written")
    parser.add_argument("--give-up-after", type=float, default=None, help="seconds; none: wait")
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="build as on a new machine: pull the base images, use no cached layer",
    )
    options = parser.parse_args()
    port = port_of(options.port)
    connectors = [sys.executable, str(ROOT / "deploy" / "docker" / "connectors.py")]
    stage(
        "configuring the connectors",
        subprocess.run(connectors, capture_output=True, text=True, check=False),  # noqa: S603
    )
    install = Install(options.project, port)
    address = f"http://localhost:{port}/app/"
    marks: dict[str, datetime] = {"started": now()}
    print("start: installing Taktus. The first build of the image takes several minutes.")

    stage("writing the secrets", install.run(str(ROOT / "deploy" / "docker" / "secrets.sh")))
    fresh = ["--no-cache", "--pull"] if options.no_cache else []
    stage("building the image", install.run(*install.compose, "build", *fresh, "taktus"))
    marks["image_built"] = now()
    stage("starting the containers", install.run(*install.compose, "up", "--detach", "--wait"))
    marks["ready"] = now()
    made = install.taktusctl("first", "start", "--name", options.name, "--address", address)
    stage("creating the first tenant", made)
    marks["tenant_ready"] = now()
    lines = made.stdout.splitlines()
    tenant = lines[0].removeprefix("tenant ").strip() if lines else ""
    print("\n".join(lines[1:]))
    print(
        "\nIn the web app, open the gallery, choose a first process and rehearse it. The clock "
        "runs until that rehearsal has finished. Ctrl-C stops the clock; Taktus keeps running."
    )

    reading: dict[str, str | None] = {}
    finished: datetime | None = None
    stopped = False
    try:
        while True:
            answer = install.taktusctl("first", "rehearsal", "--tenant", tenant)
            if answer.returncode == 0 and answer.stdout.strip():
                reading = json.loads(answer.stdout.strip().splitlines()[-1])
                if reading.get("rehearsal_finished_at"):
                    finished = datetime.fromisoformat(str(reading["rehearsal_finished_at"]))
                    break
            elapsed = (now() - marks["started"]).total_seconds()
            if options.give_up_after is not None and elapsed > options.give_up_after:
                break
            time.sleep(POLL_SECONDS)
    except KeyboardInterrupt:
        stopped = True
    started_rehearsal = reading.get("rehearsal_started_at")
    rehearsal_started = None if not started_rehearsal else datetime.fromisoformat(started_rehearsal)
    before = finished is not None and finished < marks["started"]
    total = None if finished is None or before else seconds(marks["started"], finished)
    record = {
        "measures": "from the install command to the end of the first rehearsal (UC-10.4)",
        "started_at": marks["started"].isoformat(),
        "stages": {
            "image_built_at": marks["image_built"].isoformat(),
            "ready_at": marks["ready"].isoformat(),
            "tenant_ready_at": marks["tenant_ready"].isoformat(),
            "rehearsal_started_at": started_rehearsal,
            "rehearsal_finished_at": None if finished is None else finished.isoformat(),
        },
        "seconds": {
            "image": seconds(marks["started"], marks["image_built"]),
            "start": seconds(marks["image_built"], marks["ready"]),
            "first_start": seconds(marks["ready"], marks["tenant_ready"]),
            "to_the_rehearsal": seconds(marks["tenant_ready"], rehearsal_started),
            "rehearsal": None
            if rehearsal_started is None
            else seconds(rehearsal_started, finished),
            "total": total,
        },
        "within_ten_minutes": total is not None and total <= TEN_MINUTES,
        "build_cache": "none" if options.no_cache else "the machine's",
        "rehearsal_run": reading.get("run"),
        "finished_before_this_start": before,
        "clock_stopped_by_hand": stopped,
        "machine": {
            "system": platform.system(),
            "release": platform.release(),
            "architecture": platform.machine(),
            "processors": os.cpu_count(),
        },
    }
    Path(options.record).write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    if stopped:
        print(f"\nstart: the clock was stopped; Taktus keeps running. Written: {options.record}")
        return 130
    if before:
        print("\nstart: this tenant's first rehearsal finished before; nothing was measured.")
        return 0
    if total is None:
        print(f"\nstart: no rehearsal finished in time. Written: {options.record}")
        return 1
    minutes, rest = divmod(int(total), 60)
    print(f"\nstart: your first rehearsal finished {minutes} min {rest} s after the install began.")
    for name, value in record["seconds"].items():  # type: ignore[union-attr]
        print(f"  {name:<18} {value} s")
    print(f"Written: {options.record}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
