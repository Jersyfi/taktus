#!/usr/bin/env python3
"""`make start-cluster`: install Taktus on a cluster in one command, create its first tenant, and
measure the time to a first rehearsed process (UC-10.4, ADR-0136 §6, ADR-0228).

It does on a cluster what `deploy/docker/start.py` does on one machine:

1. installs or upgrades the chart with the operator's own values (`helm upgrade --install`);
   with `--installed` the release is taken as it stands, and the clock starts now;
2. waits for every deployment of the release's namespace to be rolled out;
3. runs `taktusctl first start` in a pod of the control plane, which creates the first tenant and
   its administrator and prints the account key once;
4. keeps the clock: every five seconds it asks `taktusctl first rehearsal`, in the same pod,
   whether the tenant's first rehearsal has finished, and writes what it measured to
   `deploy/k8s/first-process.json` (git ignores it).

Installing the release stays the operator's act: this command runs `helm` with the values the
operator gives it, against the cluster `kubectl` points at, and creates no Secret. The record
holds times, the cluster's version and node count, and whether the time was within ten minutes.
It never holds the account key, and it names no person.

Needs kubectl and helm on the path, and python3. Standard library only. Exit code 0 once the
rehearsal finished; 1 where it did not before `--give-up-after`; 2 where a stage of the install
failed; 130 when the clock was stopped.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CHART = ROOT / "deploy" / "k8s" / "chart"
RECORD = ROOT / "deploy" / "k8s" / "first-process.json"
CONTROL_PLANE = "app.kubernetes.io/component=control-plane"
CONTAINER = "taktusd"
TEN_MINUTES = 600


def _shared() -> Any:
    """The clock of `deploy/docker/start.py`, so that both installs measure the same way."""
    spec = importlib.util.spec_from_file_location(
        "taktus_start", ROOT / "deploy" / "docker" / "start.py"
    )
    if spec is None or spec.loader is None:
        raise SystemExit("start: deploy/docker/start.py cannot be read")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


shared = _shared()


class Cluster:
    def __init__(self, namespace: str, release: str, context: str | None) -> None:
        self.namespace = namespace
        self.release = release
        self.kubectl = ["kubectl", "--namespace", namespace]
        self.helm = ["helm", "--namespace", namespace]
        if context:
            self.kubectl += ["--context", context]
            self.helm += ["--kube-context", context]
        self._pod: str | None = None

    def run(self, *arguments: str, capture: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(  # noqa: S603 — fixed commands of this repository
            list(arguments), cwd=ROOT, text=True, capture_output=capture, check=False
        )

    def install(self, values: list[str], timeout: str) -> subprocess.CompletedProcess[str]:
        files = [a for v in values for a in ("--values", v)]
        return self.run(
            *self.helm, "upgrade", "--install", self.release, str(CHART), *files,
            "--timeout", timeout,
        )  # fmt: skip

    def rolled_out(self, timeout: str) -> subprocess.CompletedProcess[str]:
        return self.run(*self.kubectl, "rollout", "status", "deployment", f"--timeout={timeout}")

    def pod(self) -> str:
        if self._pod is None:
            found = self.run(
                *self.kubectl, "get", "pods", "-l", CONTROL_PLANE,
                "--field-selector=status.phase=Running",
                "-o", "jsonpath={.items[0].metadata.name}",
            )  # fmt: skip
            self._pod = found.stdout.strip() if found.returncode == 0 else ""
        return self._pod

    def taktusctl(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return self.run(
            *self.kubectl, "exec", self.pod(), "-c", CONTAINER, "--", "taktusctl", *arguments
        )

    def described(self) -> dict[str, object]:
        """The cluster as the record names it: its server version and its node count."""
        version = self.run("kubectl", "version", "--output=json")
        nodes = self.run("kubectl", "get", "nodes", "-o", "name")
        server: object = None
        if version.returncode == 0 and version.stdout.strip():
            server = json.loads(version.stdout).get("serverVersion", {}).get("gitVersion")
        return {
            "server": server,
            "nodes": len(nodes.stdout.split()) if nodes.returncode == 0 else None,
        }


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(line_buffering=True)  # type: ignore[union-attr]
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--name", default="My organisation", help="the first tenant's name")
    parser.add_argument("--namespace", default="taktus", help="the control plane's namespace")
    parser.add_argument("--release", default="taktus", help="the chart's release name")
    parser.add_argument("--context", default=None, help="the kubectl context; none: the current")
    parser.add_argument(
        "--values", action="append", default=[], help="a values file of the operator; repeatable"
    )
    parser.add_argument(
        "--installed", action="store_true", help="the release is installed: start the clock"
    )
    parser.add_argument("--address", required=True, help="the web app's address, as opened")
    parser.add_argument("--timeout", default="10m", help="how long a stage may take")
    parser.add_argument("--record", default=str(RECORD), help="where the measurement is written")
    parser.add_argument("--give-up-after", type=float, default=None, help="seconds; none: wait")
    parser.add_argument("--poll-seconds", type=float, default=shared.POLL_SECONDS)
    options = parser.parse_args(argv)
    cluster = Cluster(options.namespace, options.release, options.context)
    marks: dict[str, datetime] = {"started": shared.now()}
    if not options.installed:
        if not options.values:
            print("start: give your values file with --values, or --installed; nothing installed")
            return 2
        print("start: installing Taktus on the cluster kubectl points at.")
        shared.stage("installing the chart", cluster.install(options.values, options.timeout))
    marks["installed"] = shared.now()
    shared.stage("waiting for the roles", cluster.rolled_out(options.timeout))
    marks["ready"] = shared.now()
    if not cluster.pod():
        print("start: no running pod of the control plane was found; Taktus is not ready")
        return 2
    made = cluster.taktusctl("first", "start", "--name", options.name, "--address", options.address)
    shared.stage("creating the first tenant", made)
    marks["tenant_ready"] = shared.now()
    lines = made.stdout.splitlines()
    tenant = lines[0].removeprefix("tenant ").strip() if lines else ""
    print("\n".join(lines[1:]))
    print(
        "\nIn the web app, open the gallery, choose a first process and rehearse it. The clock "
        "runs until that rehearsal has finished. Ctrl-C stops the clock; Taktus keeps running."
    )
    reading, finished, stopped = shared.wait_for_rehearsal(
        cluster.taktusctl, tenant, marks["started"], options.give_up_after, options.poll_seconds
    )
    begun = reading.get("rehearsal_started_at")
    rehearsal_started = None if not begun else datetime.fromisoformat(begun)
    before = finished is not None and finished < marks["started"]
    total = None if finished is None or before else shared.seconds(marks["started"], finished)
    seconds = shared.seconds
    record = {
        "measures": "from the install command to the end of the first rehearsal (UC-10.4)",
        "on": "cluster",
        "started_at": marks["started"].isoformat(),
        "stages": {
            "installed_at": marks["installed"].isoformat(),
            "ready_at": marks["ready"].isoformat(),
            "tenant_ready_at": marks["tenant_ready"].isoformat(),
            "rehearsal_started_at": begun,
            "rehearsal_finished_at": None if finished is None else finished.isoformat(),
        },
        "seconds": {
            "install": seconds(marks["started"], marks["installed"]),
            "start": seconds(marks["installed"], marks["ready"]),
            "first_start": seconds(marks["ready"], marks["tenant_ready"]),
            "to_the_rehearsal": seconds(marks["tenant_ready"], rehearsal_started),
            "rehearsal": None
            if rehearsal_started is None
            else seconds(rehearsal_started, finished),
            "total": total,
        },
        "within_ten_minutes": total is not None and total <= TEN_MINUTES,
        "installed_before": options.installed,
        "rehearsal_run": reading.get("run"),
        "finished_before_this_start": before,
        "clock_stopped_by_hand": stopped,
        "cluster": cluster.described(),
        "machine": shared.machine(),
    }
    return int(shared.told(record, options.record, stopped=stopped, before=before))


if __name__ == "__main__":
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    sys.exit(main())
