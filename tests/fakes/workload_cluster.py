#!/usr/bin/env python3
"""A fake workload cluster: the part of a Kubernetes API server the workload connector uses, in
memory.

The connector under `connectors/taktus_connectors/kubernetes/` asks, under
`/apis/apps/v1/namespaces/<namespace>/`:

- `GET deployments/<name>`: the deployment, 404 for one the namespace does not hold;
- `PATCH deployments/<name>` with `application/strategic-merge-patch+json`: containers merged by
  name, maps merged key by key; a `metadata.resourceVersion` that is not the current one is 409,
  as the API server answers a stale write. With `application/json-patch+json`, the operations
  `replace` and `add` on a path (RFC 6902);
- `GET deployments/<name>/scale` and `PATCH deployments/<name>/scale` with
  `application/merge-patch+json`: the replicas wanted;
- `GET replicasets?labelSelector=<k>=<v>,...`: the revisions, each with its pod template, its
  owner and its `deployment.kubernetes.io/revision`.

What it enforces, because the connector's checks depend on it:

- **Authentication.** Every request needs `Authorization: Bearer <value>` with a value the fake
  was started with (`FAKE_TOKENS`, comma separated). Otherwise 401.
- **Revisions as the controller keeps them.** A change of the pod template makes the template's
  revision the newest: an existing replica set with the same template takes the next number,
  otherwise a new one is made with it. The deployment's revision annotation follows.
- **A rollout.** It completes at once — every wanted replica updated, ready and available —
  unless `POST /_fake/rollout` with `{"stalled": true}` holds it, as a rollout whose new pods
  never become ready.

The namespace `default` holds the deployments `web` (container `app`, image
`registry.example/app:1.0.0`, three replicas) and `web-canary` (the same, no replicas), each
with one revision. Test-only: `GET /_fake/state` names the deployments with their images,
replicas and revisions, and counts the requests; `POST /_fake/reset` restores the start.
Standard library only; runnable as `python3 tests/fakes/workload_cluster.py --port 9230`.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import sys
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

type Json = dict[str, Any]

REVISION = "deployment.kubernetes.io/revision"
IMAGE = "registry.example/app:1.0.0"


def deployment(name: str, replicas: int) -> Json:
    labels = {"app": name}
    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {
            "name": name,
            "namespace": "default",
            "uid": str(uuid.uuid4()),
            "generation": 1,
            "resourceVersion": "1",
            "annotations": {REVISION: "1"},
        },
        "spec": {
            "replicas": replicas,
            "selector": {"matchLabels": labels},
            "template": {
                "metadata": {"labels": dict(labels)},
                "spec": {"containers": [{"name": "app", "image": IMAGE}]},
            },
        },
        "status": {},
    }


class State:
    def __init__(self, tokens: set[str]) -> None:
        self.tokens = tokens
        self.lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        self.requests = 0
        self.stalled = False
        self.version = 1
        self.deployments: dict[str, Json] = {}
        self.replicasets: list[Json] = []
        for name, replicas in (("web", 3), ("web-canary", 0)):
            made = deployment(name, replicas)
            self.deployments[name] = made
            self._replicaset(made, 1)
            self._status(made)

    def _replicaset(self, owner: Json, revision: int) -> None:
        template = copy.deepcopy(owner["spec"]["template"])
        template["metadata"].setdefault("labels", {})["pod-template-hash"] = uuid.uuid4().hex[:10]
        self.replicasets.append(
            {
                "metadata": {
                    "name": f"{owner['metadata']['name']}-{uuid.uuid4().hex[:10]}",
                    "namespace": "default",
                    "labels": dict(owner["spec"]["selector"]["matchLabels"]),
                    "annotations": {REVISION: str(revision)},
                    "ownerReferences": [
                        {"kind": "Deployment", "name": owner["metadata"]["name"],
                         "uid": owner["metadata"]["uid"]}
                    ],
                },
                "spec": {"template": template},
            }
        )  # fmt: skip

    def _status(self, made: Json) -> None:
        replicas = int(made["spec"].get("replicas", 1))
        ready = 0 if self.stalled else replicas
        made["status"] = {
            "observedGeneration": made["metadata"]["generation"],
            "replicas": replicas,
            "updatedReplicas": ready,
            "readyReplicas": ready,
            "availableReplicas": ready,
            "unavailableReplicas": replicas - ready,
        }

    def owned(self, made: Json) -> list[Json]:
        uid = made["metadata"]["uid"]
        return [
            rs
            for rs in self.replicasets
            if any(o.get("uid") == uid for o in rs["metadata"]["ownerReferences"])
        ]

    def changed(self, made: Json, before: Json) -> None:
        """After a write: the generation and version move, and a new template is a revision."""
        self.version += 1
        made["metadata"]["resourceVersion"] = str(self.version)
        if made["spec"] == before["spec"]:
            return
        made["metadata"]["generation"] += 1
        if made["spec"]["template"] != before["spec"]["template"]:
            owned = self.owned(made)
            newest = max(int(rs["metadata"]["annotations"][REVISION]) for rs in owned) + 1
            for rs in owned:
                template = copy.deepcopy(rs["spec"]["template"])
                template["metadata"]["labels"].pop("pod-template-hash", None)
                if template == made["spec"]["template"]:
                    rs["metadata"]["annotations"][REVISION] = str(newest)
                    break
            else:
                self._replicaset(made, newest)
            made["metadata"]["annotations"][REVISION] = str(newest)
        self._status(made)

    def summary(self) -> Json:
        return {
            "requests": self.requests,
            "deployments": {
                name: {
                    "images": [c["image"] for c in d["spec"]["template"]["spec"]["containers"]],
                    "replicas": d["spec"]["replicas"],
                    "revision": int(d["metadata"]["annotations"][REVISION]),
                    "revisions": len(self.owned(d)),
                }
                for name, d in self.deployments.items()
            },
        }


def strategic(target: Json, patch: Json) -> None:
    for key, value in patch.items():
        if key == "containers" and isinstance(value, list):
            by_name = {c["name"]: c for c in target.get(key, [])}
            for container in value:
                if container.get("name") in by_name:
                    strategic(by_name[container["name"]], container)
                else:
                    target.setdefault(key, []).append(copy.deepcopy(container))
        elif isinstance(value, dict) and isinstance(target.get(key), dict):
            strategic(target[key], value)
        elif value is None:
            target.pop(key, None)
        else:
            target[key] = copy.deepcopy(value)


def pointer(path: str) -> list[str]:
    return [p.replace("~1", "/").replace("~0", "~") for p in path.lstrip("/").split("/")]


def json_patch(target: Json, operations: list[Json]) -> bool:
    for op in operations:
        if op.get("op") not in ("replace", "add"):
            return False
        *parents, last = pointer(str(op.get("path", "")))
        node: Any = target
        for part in parents:
            node = node[int(part)] if isinstance(node, list) else node.get(part)
            if node is None:
                return False
        if isinstance(node, list):
            node[int(last)] = copy.deepcopy(op["value"])
        elif op["op"] == "replace" and last not in node:
            return False
        else:
            node[last] = copy.deepcopy(op["value"])
    return True


def handler(state: State) -> type[BaseHTTPRequestHandler]:
    base = r"/apis/apps/v1/namespaces/default"

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, format: str, *args: Any) -> None:
            sys.stderr.write(f"fake-cluster {format % args}\n")

        def answer(self, status: int, body: Any) -> None:
            payload = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def status(self, code: int, reason: str) -> None:
            self.answer(
                code, {"kind": "Status", "status": "Failure", "reason": reason, "code": code}
            )

        def body(self) -> Any:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            return json.loads(raw) if raw else {}

        def admitted(self) -> bool:
            given = (self.headers.get("Authorization") or "").removeprefix("Bearer ")
            if given not in state.tokens:
                self.status(401, "Unauthorized")
                return False
            return True

        def do_GET(self) -> None:
            url = urlparse(self.path)
            if url.path == "/_fake/state":
                with state.lock:
                    self.answer(200, state.summary())
                return
            if not self.admitted():
                return
            with state.lock:
                state.requests += 1
                if m := re.fullmatch(base + r"/deployments/([a-z0-9-]+)(/scale)?", url.path):
                    made = state.deployments.get(m.group(1))
                    if made is None:
                        self.status(404, "NotFound")
                    elif m.group(2):
                        self.answer(200, scale_of(made))
                    else:
                        self.answer(200, made)
                    return
                if url.path == base + "/replicasets":
                    selector = unquote(parse_qs(url.query).get("labelSelector", [""])[0])
                    wanted = dict(p.split("=", 1) for p in selector.split(",") if "=" in p)
                    items = [
                        rs
                        for rs in state.replicasets
                        if all(rs["metadata"]["labels"].get(k) == v for k, v in wanted.items())
                    ]
                    self.answer(200, {"kind": "ReplicaSetList", "items": items})
                    return
                self.status(404, "NotFound")

        def do_POST(self) -> None:
            url = urlparse(self.path)
            body = self.body()
            with state.lock:
                if url.path == "/_fake/reset":
                    state.reset()
                    self.answer(200, {})
                    return
                if url.path == "/_fake/rollout":
                    state.stalled = bool(body.get("stalled"))
                    for made in state.deployments.values():
                        state._status(made)
                    self.answer(200, {"stalled": state.stalled})
                    return
            self.status(404, "NotFound")

        def do_PATCH(self) -> None:
            url = urlparse(self.path)
            body = self.body()
            if not self.admitted():
                return
            kind = self.headers.get("Content-Type", "")
            with state.lock:
                state.requests += 1
                m = re.fullmatch(base + r"/deployments/([a-z0-9-]+)(/scale)?", url.path)
                made = state.deployments.get(m.group(1)) if m else None
                if m is None or made is None:
                    self.status(404, "NotFound")
                    return
                before = copy.deepcopy(made)
                if m.group(2):
                    if kind != "application/merge-patch+json":
                        self.status(415, "UnsupportedMediaType")
                        return
                    replicas = body.get("spec", {}).get("replicas")
                    if not isinstance(replicas, int) or replicas < 0:
                        self.status(422, "Invalid")
                        return
                    made["spec"]["replicas"] = replicas
                    state.changed(made, before)
                    self.answer(200, scale_of(made))
                    return
                if kind == "application/strategic-merge-patch+json":
                    given = body.get("metadata", {}).get("resourceVersion")
                    if given is not None and given != made["metadata"]["resourceVersion"]:
                        self.status(409, "Conflict")
                        return
                    body.get("metadata", {}).pop("resourceVersion", None)
                    strategic(made, body)
                elif kind == "application/json-patch+json":
                    if not isinstance(body, list) or not json_patch(made, body):
                        self.status(422, "Invalid")
                        return
                else:
                    self.status(415, "UnsupportedMediaType")
                    return
                state.changed(made, before)
                self.answer(200, made)

    return Handler


def scale_of(made: Json) -> Json:
    return {
        "kind": "Scale",
        "metadata": {"name": made["metadata"]["name"], "namespace": "default"},
        "spec": {"replicas": made["spec"]["replicas"]},
        "status": {"replicas": made["status"].get("replicas", 0)},
    }


def make_server(host: str, port: int, tokens: set[str]) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), handler(State(tokens)))


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9230)
    args = parser.parse_args()
    tokens = {t for t in os.environ.get("FAKE_TOKENS", "").split(",") if t}
    server = make_server(args.host, args.port, tokens)
    sys.stderr.write(f"fake workload cluster at http://{args.host}:{args.port}\n")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
