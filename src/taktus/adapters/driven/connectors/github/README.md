# The reference connector — a repository hosting service

The connector contract v1 ([`contracts/connector/v1`](../../../../../../contracts/connector/v1/README.md))
implemented against GitHub's REST API and webhooks. This directory, this file and the
configuration that points at it are the only places in the repository that name the product.
Everywhere else — processes, blueprints, documents — it is `repository.issues`,
`repository.pullrequests`, `repository.pipelines` and `repository.comments`.

It is proof and example, not a requirement: the control plane runs with it removed.

```
uv run python -m taktus.adapters.driven.connectors.github --port 9100 --repository owner/name
```

(The package lives in the project environment and not on the machine's path, hence `uv run`.)

serves MCP over streamable HTTP at `http://127.0.0.1:9100/mcp` and readiness at `GET /health`.
`--target` is the API's base URL (default `https://api.github.com`); point it at the fake under
`tests/fakes/repository_service.py` to run without a network.

## What it declares

The resource `taktus://connector/v1/capabilities` ([`declaration.py`](declaration.py)):

| Operation | Effect | Idempotency | How a repeat is recognised |
|---|---|---|---|
| `repository.issues.read` | read | — | |
| `repository.issues.create` | write | marked | the key in the issue body, among the 100 most recently created issues |
| `repository.pullrequests.read` | read | — | |
| `repository.pullrequests.open` | write | marked | the key in the body of the pull request for that head branch — exact, because the service keeps at most one open pull request per head |
| `repository.pipelines.read` | read | — | |
| `repository.pipelines.trigger` | write | **none** | not at all: a workflow dispatch answers 204 with no run identifier |
| `repository.comments.list` | read | — | |
| `repository.comments.create` | write | marked | the key in a comment of that issue, all pages |

The mark is an HTML comment at the end of the body, `<!-- taktus-idempotency-key … -->`,
invisible when rendered. Every `marked` operation looks for it **before** acting
([`operations.py`](operations.py)); the connector keeps no memory of what it did, the service
does, and that memory survives a restart of the connector. The test that tries to open a pull
request twice for the same step across a restart is
`tests/adapters/connectors/test_repository_actions.py`.

`repository.pipelines.trigger` is the honest case of the contract's §4: the connector acts every
time and says so; Taktus never repeats it on its own.

Consumption is counted in `quota` units named `requests`: every result reports how many API
requests the call made.

## Credentials

Two, referenced by the names below, created and mapped by the operator; `CREDENTIALS.md`
describes both as parameters:

| Name | Purpose | How it reaches the connector |
|---|---|---|
| `REPOSITORY_TOKEN` | actions: the **requesting identity's** token, with that identity's scopes | referenced in the call's context; read from the environment or a file at the moment of the call, never stored |
| `REPOSITORY_WEBHOOK_SECRET` | intake: the secret the webhook signs with | read from the environment at the moment of the intake call |

The connector has no token of its own. A call that references no credential, or one that is not
available, ends `unauthenticated` without a request. A token the service refuses for a write ends
`forbidden`. Whoever cannot do something on the service cannot do it through Taktus either.

## Errors

The service's answers map to the contract's causes ([`api.py`](api.py)): 401 `unauthenticated`,
403 `forbidden` (or `unavailable` when the rate limit is exhausted), 404 `not_found`, 422
`invalid` (or `conflict` when the message says a record already exists), 409 `conflict`, 429 and
5xx `unavailable`. A connection that could not be made is `unavailable` with no effect; a request
that was sent and never answered is `unknown` with effect `unknown` — the only case in which the
connector does not know whether it acted.

## Intake

Webhook deliveries, verified by `X-Hub-Signature-256` (HMAC-SHA256 over the raw body with the
webhook secret) before the body is read ([`intake.py`](intake.py)). Events normalised:
`issues.opened`, `issue_comment.created`, `pull_request.opened`, `pipeline_run.completed`
(from `workflow_run`). A comment that carries the connector's own mark is refused as `own_action`.
The recorded payloads under [`payloads/`](payloads/) are real deliveries with every identifier,
name and URL replaced by a placeholder.

## Faults

`--fault NAME` makes the connector break exactly one conformance check, so that the suite can be
shown to catch it ([`faults.py`](faults.py)); `--list-faults` prints them. `make gate-conformance`
runs the suite against every fault and expects exactly that check to fail.

## Conformance

```
uv run taktusctl conformance run --contract connector/v1 \
    --endpoint http://127.0.0.1:9100/mcp --scenario src/taktus/adapters/driven/connectors/github/scenario.json
```

[`scenario.json`](scenario.json) is written for the fake service: its writes open pull requests
from branches that the fake accepts without their existing. Against the real service, the same
scenario needs the head branches to exist.
