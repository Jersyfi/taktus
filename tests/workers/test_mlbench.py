"""What the ML bench does, beyond the contract: it trains, evaluates and predicts, reproducibly.

The worker is started as a process and reached over HTTP, as the control plane reaches it. A file
server in this process serves it the datasets. The conformance suite against it is
`tests/conformance/test_worker_v1_mlbench.py`; this file holds the bench to what issue #89
requires of the work itself:

- a training returns a model artifact with metrics measured on a held-out split, and progress in
  epochs with a boundary after each;
- the same dataset, seed and worker version give a model with the same digest, and a training
  stopped at an epoch boundary and resumed gives the digest of one run straight through
  (`docs/architecture/methods.md` §1, the row `ml`);
- an evaluation returns the metrics of a model on labelled rows, a prediction each row's class
  and its confidence, and a model whose bytes do not match its digest is used for nothing;
- what is served is what was evaluated: the model file predicts what the classifier predicted.
"""

from __future__ import annotations

import base64
import csv
import functools
import hashlib
import importlib.util
import io
import json
import os
import secrets
import socket
import subprocess
import sys
import threading
import time
import tomllib
from collections.abc import Iterator
from dataclasses import dataclass, field
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import ModuleType
from typing import Any

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
WORKER = ROOT / "workers" / "mlbench" / "worker.py"
TOOLS = ["data.read", "data.generate", "ml.train", "ml.evaluate", "ml.predict"]

type Json = dict[str, Any]


def bench() -> ModuleType:
    """The bench module, loaded from its file: the worker is a deployable, not a package."""
    spec = importlib.util.spec_from_file_location("mlbench_bench", WORKER.parent / "bench.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # its dataclasses look their module up while it loads
    spec.loader.exec_module(module)
    return module


def dataset(*, rows: int, labelled: bool = True, seed: int = 3) -> bytes:
    """Three classes around three centres in four features, drawn from the seed."""
    import random

    rng = random.Random(seed)  # noqa: S311 — test data drawn from a seed, not a secret
    centres = [[rng.uniform(-3, 3) for _ in range(4)] for _ in range(3)]
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(["a", "b", "c", "d", *(["kind"] if labelled else [])])
    for row in range(rows):
        label = row % 3
        values = [f"{c + rng.gauss(0, 0.8):.6f}" for c in centres[label]]
        writer.writerow([*values, *([f"k{label}"] if labelled else [])])
    return out.getvalue().encode()


def digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


@dataclass
class Bench:
    endpoint: str
    host: str
    served: Path
    log: Path
    finished: list[Json] = field(default_factory=list)

    def serve(self, name: str, data: bytes) -> Json:
        (self.served / name).write_bytes(data)
        return {"uri": f"http://{self.host}/{name}", "digest": digest(data)}

    def run(
        self,
        inputs: Json,
        *,
        stop_at: str | None = None,
        checkpoint_ref: str | None = None,
        hosts: list[str] | None = None,
    ) -> tuple[Json, list[Json], dict[str, bytes]]:
        """Post one assignment, read its stream to the end, fetch its artifacts. `stop_at`
        names the step at whose start a stop is requested."""
        assignment_id = "asg_test_" + secrets.token_hex(6)
        context: Json = {"workspace": {"kind": "none"}}
        if checkpoint_ref is not None:
            context["checkpoint_ref"] = checkpoint_ref
        body = {
            "assignment_id": assignment_id,
            "task": {"goal": "test the bench", "acceptance": ["it ends"], "inputs": inputs},
            "context": context,
            "frame": {
                "autonomy_level": 2,
                "allowed_tools": TOOLS,
                "allowed_hosts": [self.host] if hosts is None else hosts,
                "max_steps": 100,
            },
            "limits": {"compute": {"seconds": 600, "resource_class": "cpu.small"}},
            "callback": {"events": "sse"},
        }
        with httpx.Client(base_url=self.endpoint, timeout=60.0) as client:
            accepted = client.post("/v1/assignments", json=body)
            assert accepted.status_code == 201, accepted.text
            events: list[Json] = []
            with client.stream("GET", f"/v1/assignments/{assignment_id}/events") as stream:
                for line in stream.iter_lines():
                    if not line.startswith("data: "):
                        continue
                    event = json.loads(line[len("data: ") :])
                    events.append(event)
                    if (
                        stop_at is not None
                        and event["type"] == "step.started"
                        and event["step_id"] == stop_at
                    ):
                        client.post(f"/v1/assignments/{assignment_id}/stop", json={})
            artifacts = {
                e["artifact_id"]: client.get(e["uri"]).content
                for e in events
                if e["type"] == "artifact.produced"
            }
        return events[-1], events, artifacts


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class QuietFiles(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        pass


@pytest.fixture
def ml_bench(tmp_path: Path) -> Iterator[Bench]:
    served = tmp_path / "served"
    served.mkdir()
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), functools.partial(QuietFiles, directory=str(served))
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = free_port()
    log = tmp_path / "mlbench.log"
    with log.open("wb") as handle:
        process = subprocess.Popen(  # noqa: S603 — our own script, fixed arguments
            [
                sys.executable,
                str(WORKER),
                "--port",
                str(port),
                "--state-dir",
                str(tmp_path / "state"),
                "--epoch-floor",
                "0.15",
            ],
            stdout=handle,
            stderr=subprocess.STDOUT,
            env=dict(os.environ),
        )
    endpoint = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 20
        while True:
            assert process.poll() is None, log.read_text()
            try:
                if httpx.get(f"{endpoint}/v1/health", timeout=1.0).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            assert time.monotonic() < deadline, "the ML bench did not become ready"
            time.sleep(0.1)
        yield Bench(endpoint, f"127.0.0.1:{server.server_port}", served, log)
    finally:
        process.terminate()
        process.wait(timeout=5)
        server.shutdown()
        server.server_close()


def train(ml: Bench, data: bytes, **settings: Any) -> Json:
    return {
        "operation": "train",
        "dataset": ml.serve("train.csv", data),
        "label": "kind",
        "epochs": 4,
        "seed": 5,
        **settings,
    }


def test_a_training_returns_a_model_with_metrics_measured_on_held_out_rows(
    ml_bench: Bench,
) -> None:
    data = dataset(rows=900)
    finished, events, artifacts = ml_bench.run(train(ml_bench, data))
    assert finished["outcome"] == "succeeded", finished
    epochs = [e for e in events if e["type"] == "step.progress" and "progress" in e]
    assert [e["progress"]["current"] for e in epochs] == [1, 2, 3, 4]
    assert {e["progress"]["unit"] for e in epochs} == {"epochs"}
    boundaries = [e["step_id"] for e in events if e["type"] == "step.boundary"]
    assert boundaries == ["load", "epoch-1", "epoch-2", "epoch-3", "epoch-4", "evaluate"]
    kinds = {e["artifact_id"]: e["kind"] for e in events if e["type"] == "artifact.produced"}
    assert kinds["model"] == "model" and kinds["metrics"] == "report"
    assert kinds["checkpoint-4"] == "model.checkpoint"
    model = json.loads(artifacts["model"])
    metrics = json.loads(artifacts["metrics"])
    assert metrics["rows"] == 180, "a fifth of 900 rows is held out"
    assert metrics["accuracy"] > 0.9
    assert model["evaluation"] == metrics
    assert model["dataset"] == {"digest": digest(data), "rows": 900, "label": "kind"}
    assert model["seed"] == 5 and model["epochs"] == 4
    assert model["produced_by"]["worker"] == "mlbench"
    assert set(model["produced_by"]["libraries"]) == {"numpy", "scikit-learn"}
    assert model["classes"] == ["k0", "k1", "k2"]
    consumed = [e for e in events if e["type"] == "consumption.reported"]
    assert len(consumed) == 6 and all(e["resource_class"] == "cpu.small" for e in consumed)


def test_the_same_dataset_seed_and_version_give_the_same_model(ml_bench: Bench) -> None:
    data = dataset(rows=600)
    _, _, first = ml_bench.run(train(ml_bench, data))
    _, _, second = ml_bench.run(train(ml_bench, data))
    _, _, other_seed = ml_bench.run(train(ml_bench, data, seed=6))
    assert digest(first["model"]) == digest(second["model"])
    assert first["metrics"] == second["metrics"]
    assert digest(other_seed["model"]) != digest(first["model"]), "the seed is what varies"


def test_a_training_stopped_at_an_epoch_and_resumed_ends_in_the_same_model(
    ml_bench: Bench,
) -> None:
    data = dataset(rows=600)
    _, _, straight = ml_bench.run(train(ml_bench, data))
    stopped, _, before = ml_bench.run(train(ml_bench, data), stop_at="epoch-2")
    assert stopped["outcome"] == "stopped", stopped
    assert stopped["checkpoint_ref"].endswith("/epoch-2")
    assert "model" not in before
    resumed, after_events, after = ml_bench.run(
        train(ml_bench, data), checkpoint_ref=stopped["checkpoint_ref"]
    )
    assert resumed["outcome"] == "succeeded", resumed
    started = [e["step_id"] for e in after_events if e["type"] == "step.started"]
    assert started == ["epoch-3", "epoch-4", "evaluate"]
    assert not set(before) & set(after), "nothing from before the checkpoint is produced again"
    assert digest(after["model"]) == digest(straight["model"])


def test_the_default_work_trains_on_the_built_in_dataset(ml_bench: Bench) -> None:
    finished, events, artifacts = ml_bench.run({})
    assert finished["outcome"] == "succeeded", finished
    tools = [e["tool"] for e in events if e["type"] == "tool.called"]
    assert tools[0] == "data.generate" and "data.read" not in tools
    assert json.loads(artifacts["model"])["dataset"]["rows"] == 2000


def test_a_model_evaluates_and_predicts_as_it_was_trained(ml_bench: Bench) -> None:
    data = dataset(rows=900)
    _, _, trained = ml_bench.run(train(ml_bench, data))
    model = trained["model"]
    pinned = {"base64": base64.b64encode(model).decode(), "digest": digest(model)}

    fresh = dataset(rows=300, seed=3)  # the same centres, rows drawn again
    finished, _, evaluated = ml_bench.run(
        {"operation": "evaluate", "model": pinned, "dataset": ml_bench.serve("eval.csv", fresh)}
    )
    assert finished["outcome"] == "succeeded", finished
    metrics = json.loads(evaluated["metrics"])
    assert metrics["rows"] == 300 and metrics["accuracy"] > 0.9
    assert set(metrics["per_class"]) == {"k0", "k1", "k2"}

    rows = dataset(rows=30, labelled=False, seed=3)
    finished, _, predicted = ml_bench.run(
        {"operation": "predict", "model": pinned, "dataset": ml_bench.serve("rows.csv", rows)}
    )
    assert finished["outcome"] == "succeeded", finished
    table = list(csv.DictReader(io.StringIO(predicted["predictions"].decode())))
    assert len(table) == 30
    assert {r["class"] for r in table} <= {"k0", "k1", "k2"}
    assert all(0.0 < float(r["confidence"]) <= 1.0 for r in table)


def test_a_model_that_does_not_match_its_digest_is_used_for_nothing(ml_bench: Bench) -> None:
    data = dataset(rows=300)
    _, _, trained = ml_bench.run(train(ml_bench, data, epochs=1))
    model = trained["model"]
    wrong = "sha256:" + "0" * 64
    rows = ml_bench.serve("rows.csv", dataset(rows=10, labelled=False))

    inline = {"base64": base64.b64encode(model).decode(), "digest": wrong}
    finished, events, _ = ml_bench.run({"operation": "predict", "model": inline, "dataset": rows})
    assert finished["outcome"] == "rejected" and "digest" in finished["reason"]
    assert len(events) == 1, "rejected before it started"

    served = {**ml_bench.serve("model.json", model), "digest": wrong}
    finished, events, artifacts = ml_bench.run(
        {"operation": "predict", "model": served, "dataset": rows}
    )
    assert finished["outcome"] == "failed" and "digest" in finished["reason"]
    assert [e["step_id"] for e in events if e["type"] == "step.started"] == ["load"]
    assert artifacts == {}

    unpinned = {"base64": base64.b64encode(model).decode()}
    finished, _, _ = ml_bench.run({"operation": "predict", "model": unpinned, "dataset": rows})
    assert finished["outcome"] == "rejected" and "digest" in finished["reason"]


def test_a_dataset_on_a_host_the_frame_does_not_allow_is_not_read(ml_bench: Bench) -> None:
    finished, events, artifacts = ml_bench.run(train(ml_bench, dataset(rows=60)), hosts=[])
    assert finished["outcome"] == "failed"
    reads = [e for e in events if e["type"] == "tool.called"]
    assert reads and reads[0]["host"] == ml_bench.host and reads[0]["refused"] is True
    assert artifacts == {}


def test_the_model_file_predicts_what_the_classifier_predicted() -> None:
    """What is served is what was evaluated: the file's numbers alone give the classifier's
    classes and probabilities, for two classes and for three."""
    module = bench()
    for classes in (2, 3):
        _, table = module.synthetic({"rows": 400, "features": 5, "classes": classes}, 9)
        data = module.prepare(table, 9, 0.25)
        state = None
        for _ in range(3):
            state, _ = module.epoch(data, 9, state)
        fitted = module.classifier(9, data.classes, state)
        expected = fitted.predict((data.x_holdout - data.mean) / data.scale)
        probability = fitted.predict_proba((data.x_holdout - data.mean) / data.scale).max(axis=1)
        file = module.model_file(
            data, state, seed=9, epochs=3, worker={"worker": "t", "version": "0"}, metrics=None
        )
        served, confidence = module.predict(module.load_model(file), data.x_holdout)
        assert served.tolist() == expected.tolist()
        assert confidence.round(9).tolist() == probability.round(9).tolist()


def test_the_image_installs_the_versions_the_tests_ran() -> None:
    """The image pins every library of the bench to the version uv.lock holds, so that what the
    tests proved reproducible is what ships (requirements.txt, installed with --no-deps)."""
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    packages = {p["name"]: p for p in lock["package"]}
    lines = (WORKER.parent / "requirements.txt").read_text(encoding="utf-8").splitlines()
    pinned = dict(line.split("==", 1) for line in lines if line and not line.startswith("#"))
    closure: set[str] = set()
    pending = ["scikit-learn"]
    while pending:
        name = pending.pop()
        if name not in closure:
            closure.add(name)
            pending += [d["name"] for d in packages[name].get("dependencies", [])]
    assert set(pinned) == closure
    assert {name: packages[name]["version"] for name in pinned} == pinned
