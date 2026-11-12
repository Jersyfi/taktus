"""On a cluster, one command creates the first tenant and the clock measures the time to a first
rehearsed process (UC-10.4, ADR-0136 §6, ADR-0228, #405).

`deploy/k8s/start.py` runs against stand-ins for `helm` and `kubectl` on the path: they record
what they were asked and answer as a cluster would, so the command's stages, the tenant it
creates in a pod of the control plane, and the measurement it writes are proven without a
cluster. The clock is `deploy/docker/start.py`'s, shared."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "deploy" / "k8s" / "start.py"
KEY = "tk_secret_shown_once"

KUBECTL = """#!{python}
import json, sys
from pathlib import Path
log = Path({log!r})
with log.open("a") as out:
    out.write("kubectl " + " ".join(sys.argv[1:]) + "\\n")
args = sys.argv[1:]
if "rollout" in args:
    sys.exit(0)
if args[:1] == ["version"]:
    print(json.dumps({{"serverVersion": {{"gitVersion": "v1.31.0"}}}}))
    sys.exit(0)
if "nodes" in args:
    print("node/a node/b")
    sys.exit(0)
if "pods" in args:
    print("taktus-all-0")
    sys.exit(0)
if "exec" in args and "start" in args:
    print("tenant ten_first")
    print("Your account key, shown once — keep it like a password: {key}")
    print("Open https://taktus.example/app/ in your browser and sign in with it.")
    sys.exit(0)
if "exec" in args and "rehearsal" in args:
    marker = Path({log!r} + ".asked")
    asked = int(marker.read_text()) if marker.exists() else 0
    marker.write_text(str(asked + 1))
    done = asked >= 1
    print(json.dumps({{
        "tenant": "ten_first",
        "rehearsal_started_at": {started!r},
        "rehearsal_finished_at": {finished!r} if done else None,
        "run": "run_1" if done else None,
    }}))
    sys.exit(0)
sys.exit(1)
"""

HELM = """#!{python}
import sys
from pathlib import Path
with Path({log!r}).open("a") as out:
    out.write("helm " + " ".join(sys.argv[1:]) + "\\n")
"""


def stand_ins(tmp: Path, *, finished: datetime) -> dict[str, str]:
    bin_ = tmp / "bin"
    bin_.mkdir()
    log = str(tmp / "calls.log")
    started = (finished - timedelta(seconds=30)).isoformat()
    for name, text in (("kubectl", KUBECTL), ("helm", HELM)):
        path = bin_ / name
        path.write_text(
            text.format(
                python=sys.executable,
                log=log,
                key=KEY,
                started=started,
                finished=finished.isoformat(),
            )
        )
        path.chmod(0o755)
    return {**os.environ, "PATH": f"{bin_}{os.pathsep}{os.environ['PATH']}"}


def test_one_command_installs_creates_the_first_tenant_in_a_pod_and_measures(
    tmp_path: Path,
) -> None:
    finished = datetime.now(UTC) + timedelta(seconds=2)
    env = stand_ins(tmp_path, finished=finished)
    record = tmp_path / "first-process.json"
    values = tmp_path / "values.yaml"
    values.write_text("profile: small\n")
    done = subprocess.run(  # noqa: S603
        [
            sys.executable, str(SCRIPT), "--values", str(values), "--namespace", "taktus",
            "--address", "https://taktus.example/app/", "--record", str(record),
            "--poll-seconds", "0.1", "--give-up-after", "60",
        ],
        env=env, capture_output=True, text=True, check=False, timeout=120,
    )  # fmt: skip
    assert done.returncode == 0, done.stdout + done.stderr
    calls = (tmp_path / "calls.log").read_text().splitlines()
    assert calls[0].startswith("helm --namespace taktus upgrade --install taktus")
    assert f"--values {values}" in calls[0]
    created = next(c for c in calls if "first start" in c)
    assert "exec taktus-all-0 -c taktusd -- taktusctl first start" in created
    assert KEY in done.stdout, "the key is shown once to the person"
    measured = json.loads(record.read_text())
    assert KEY not in record.read_text(), "the record never holds the key"
    assert measured["on"] == "cluster" and measured["rehearsal_run"] == "run_1"
    assert measured["cluster"] == {"server": "v1.31.0", "nodes": 2}
    assert measured["seconds"]["total"] is not None and measured["within_ten_minutes"]


def test_without_values_or_an_installed_release_nothing_is_installed(tmp_path: Path) -> None:
    env = stand_ins(tmp_path, finished=datetime.now(UTC))
    done = subprocess.run(  # noqa: S603
        [sys.executable, str(SCRIPT), "--address", "https://taktus.example/app/"],
        env=env, capture_output=True, text=True, check=False, timeout=60,
    )  # fmt: skip
    assert done.returncode == 2 and "--values" in done.stdout
    assert not (tmp_path / "calls.log").exists(), "neither helm nor kubectl was asked"


def test_an_installed_release_is_taken_as_it_stands(tmp_path: Path) -> None:
    env = stand_ins(tmp_path, finished=datetime.now(UTC) + timedelta(seconds=1))
    record = tmp_path / "first-process.json"
    done = subprocess.run(  # noqa: S603
        [
            sys.executable, str(SCRIPT), "--installed", "--address", "https://taktus.example/app/",
            "--record", str(record), "--poll-seconds", "0.1", "--give-up-after", "60",
        ],
        env=env, capture_output=True, text=True, check=False, timeout=120,
    )  # fmt: skip
    assert done.returncode == 0, done.stdout + done.stderr
    calls = (tmp_path / "calls.log").read_text()
    assert "helm" not in calls, "the release stands as it is"
    assert json.loads(record.read_text())["installed_before"] is True
