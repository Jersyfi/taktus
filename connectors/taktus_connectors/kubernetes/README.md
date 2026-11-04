# The workload connector — a Kubernetes cluster's API

`deployment.workloads` over the API server of a Kubernetes cluster: the open-source,
vendor-neutral interface every conformant cluster serves alike, whoever runs it (ADR-0195). This
directory, this file and the configuration that points at it are the only places in the
repository that name the product. Everywhere else it is `deployment.workloads`.

```
uv run python -m taktus_connectors.kubernetes --port 9130 \
    --target https://cluster.example:6443 --namespace shop
```

serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`. It serves one
namespace, `default` unless `--namespace` names another. `--ca-file` names the cluster's
certificate authority where the API server's certificate is not one the system trusts. Point
`--target` at the fake under `tests/fakes/workload_cluster.py` to run without a cluster.

## What it declares

| Operation | Effect | Idempotency | What it does, and how a repeat is recognised |
|---|---|---|---|
| `deployment.workloads.read` | read | — | `GET deployments/<name>`: the containers with their images, the replicas wanted, `updated`, `ready` and `available`, the `revision`, the `key` the pod template carries, and `rolled_out` — the controller observed the newest generation and every wanted replica is updated and available, none unavailable: what `kubectl rollout status` waits for |
| `deployment.workloads.release` | write | marked | one container's image set by a strategic merge patch that carries the deployment's `resourceVersion` as read; a deployment changed in between is refused by the cluster, `conflict`. The pod template carries the key as the annotation `taktus.eu/idempotency-key`. Before writing, the deployment and its replica sets — the revisions the cluster keeps — are read: a template that carries the key is the original, replayed |
| `deployment.workloads.rollback` | write | marked | the pod template of an earlier revision put back by a JSON patch (RFC 6902): the replica set `revision` names, or the newest before the current one. The restored template carries the key, found again as for a release; it therefore differs from the earlier template, and the cluster records the rollback as its newest revision. No earlier revision is `not_found` |
| `deployment.workloads.scale` | write | marked | the replicas wanted set through the `scale` subresource. The number is its own mark: a repeat that finds it set changes nothing and reports `replayed`. **Weaker than a key, and stated so**: a repeat after somebody else set the same number reports replayed too |

How far back a rollback reaches is the deployment's revision history limit, the cluster's own.
Consumption is counted in `quota` units named `requests`. A timed-out write is `unknown` with
effect `unknown`; a repeat with the same key finds what it wrote.

## Credentials

One, `WORKLOADS_TOKEN`: the bearer token of a service account bound to a role in the served
namespace, with `get`, `list` and `patch` on `deployments`, `get` and `patch` on
`deployments/scale`, and `get` and `list` on `replicasets` — nothing else (`CREDENTIALS.md`). It
is referenced by name in the context of every call and read at the moment of the call from the
file `TAKTUS_CREDENTIAL_WORKLOADS_TOKEN_FILE` names. The connector has no token of its own.

## Conformance

```
uv run taktusctl conformance run --contract connector/v1 \
    --endpoint http://127.0.0.1:9130/mcp --scenario connectors/taktus_connectors/kubernetes/scenario.json
```

[`scenario.json`](scenario.json) reads the deployment `web`, releases an image to it twice under
one key and once under another, and asks for a name the API cannot hold. Against a real cluster
it releases into the namespace the connector serves: point it at a sandbox.
