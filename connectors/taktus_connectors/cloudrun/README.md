# The serverless connector — the Cloud Run Admin API v2

`deployment.workloads` over the Cloud Run Admin API v2: a service of one project's location,
released as a new revision and put back on an earlier one. It serves the operations the cluster
connector (`kubernetes/`) serves, under the same names and with the same inputs, so that a
release process runs on either target. This directory, this file and the configuration that
points at it are the only places in the repository that name the product. Everywhere else it
is `deployment.workloads` (ADR-0211).

```
uv run python -m taktus_connectors.cloudrun --port 9146 \
    --project shop-prod --location europe-west1
```

serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`. `--target` is the
API's address, `https://run.googleapis.com` unless given. Point it at the fake under
`tests/fakes/serverless_service.py` to run without the service; the fake holds the project
`example` and the location `europe-west1`.

The documentation followed:
[`projects.locations.services`](https://cloud.google.com/run/docs/reference/rest/v2/projects.locations.services)
with its `get` and `patch`,
[`services.revisions`](https://cloud.google.com/run/docs/reference/rest/v2/projects.locations.services.revisions)
with its `list`, [`Condition`](https://cloud.google.com/run/docs/reference/rest/v2/Condition),
and [OAuth 2.0 for server to server applications](https://developers.google.com/identity/protocols/oauth2/service-account#httprest).

## What it declares

| Operation | Effect | Idempotency | What it does, and how a repeat is recognised |
|---|---|---|---|
| `deployment.workloads.read` | read | — | `GET services/<name>`: the containers with their images, the latest ready revision as `revision`, the `key` the template carries, and `rolled_out` — the service is not reconciling, its terminal condition succeeded, its latest ready revision is its latest created one, it observed its newest generation, and that revision takes all the traffic. `replicas`, `updated`, `ready` and `available` are null: the service has instances, not a number of replicas wanted |
| `deployment.workloads.release` | write | marked | one container's image set in the service's template, which makes the service create a revision, and the traffic set to the latest revision, 100 percent. The body carries the service's `etag` as read; a service changed in between is refused, `conflict`. The template carries the key as the annotation `taktus.eu/idempotency-key`, and every revision keeps the annotations of the template it was made from. Before writing, the service and its revisions are read: a template that carries the key is the original, replayed |
| `deployment.workloads.rollback` | write | marked | all traffic sent to an earlier ready revision: the one `revision` names, or the newest ready before the one serving. The template is left as it is, so that no revision is made. The key is put on the service's own annotations, where a repeat finds it. No earlier revision is `not_found` |
| `deployment.workloads.throttle` | write | marked | the most instances the service may run, its template's `scaling.maxInstanceCount`, set to `max_instances` (1 to 1000): the API makes a revision of the same containers, which takes all traffic, and the output names `max_instances` and `max_instances_before`, so that a person can put the limit back. The key is the template's annotation, as a release's. A service whose traffic is held on an earlier revision is a `conflict`: a revision from its template would roll it forward. B-1.03 throttles a runaway function with it (ADR-0310) |

**No `scale`.** The service starts and stops instances itself, by its requests; it has no number
of replicas wanted to set. B-8.04, which raises a canary's replicas, does not run on it.

A write answers a long-running operation; the connector does not wait for it, and a reading
says whether the rollout is complete. A release made while a rollback holds the traffic sends
it back to the latest revision. A rollback's mark is the service's one annotation: a repeat of a
rollback after another rollback replaced the annotation acts again. Consumption is counted in
`quota` units named `requests`, the exchange of the key for a token among them. A timed-out write
is `unknown` with effect `unknown`; a repeat with the same key finds what it wrote.

## Credentials

One, `WORKLOADS_TOKEN`, the same parameter as the cluster connector's, so that the release
processes run unchanged: here the key of a service account, as JSON as Google issues it. The
account needs the role Cloud Run Developer on the project, and Service Account User on the
service account the services run as — nothing else (`CREDENTIALS.md`). For every call the
connector signs a statement with the key and exchanges it for an access token of the scope
`https://www.googleapis.com/auth/cloud-platform` at the token endpoint (`--token-endpoint`; by default Google's
`https://oauth2.googleapis.com/token`, or `<target>/token` where `--target` names another
address) — never the key's own `token_uri`, which could send a signed statement elsewhere; nothing is kept
between calls. The key is referenced by name in the context of every call and read at the moment
of the call from the file `TAKTUS_CREDENTIAL_WORKLOADS_TOKEN_FILE` names. The connector has no
key of its own.

## Conformance

```
uv run taktusctl conformance run --contract connector/v1 \
    --endpoint http://127.0.0.1:9146/mcp --scenario connectors/taktus_connectors/cloudrun/scenario.json
```

[`scenario.json`](scenario.json) reads the service `web`, releases an image to it twice under one
key and once under another, and asks for a name the API cannot hold. Against the real API it
releases into the project and location the connector serves: point it at a sandbox.
