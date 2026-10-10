# The reference connector — a repository hosting service

The connector contract v1 ([`contracts/connector/v1`](../../../../../../contracts/connector/v1/README.md))
implemented against GitHub's REST API and webhooks. This directory, this file and the
configuration that points at it are the only places in the repository that name the product.
Everywhere else — processes, blueprints, documents — it is `repository.issues`,
`repository.pullrequests`, `repository.pipelines`, `repository.comments`,
`repository.branches`, `repository.labels` and `repository.files`.

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
| `repository.issues.read` | read | — | one issue, with its labels by name and its milestone by title (`null` without one) — what a backlog's ready standard reads besides the body (issue #70) |
| `repository.issues.list` | read | — | the issues in one state, `open` unless `state` says `closed` or `all`, without pull requests, each in the shape of `repository.issues.read`; page by page, at most twenty pages of 100, and `complete` says whether every page was read, so that a reader that must see every open issue can refuse a reading that stopped short |
| `repository.issues.create` | write | marked | the key in the issue body, among the 100 most recently created issues |
| `repository.pullrequests.read` | read | — | |
| `repository.pullrequests.open` | write | marked | the key in the body of the pull request for that head branch — exact, because the service keeps at most one open pull request per head |
| `repository.pipelines.read` | read | — | |
| `repository.pipelines.status` | read | — | the runs for the head of a branch (or a commit), and one word for their state: `none`, `pending`, `success`, `failure` — the pipeline's verdict, never the connector's |
| `repository.pipelines.trigger` | write | **none** | not at all: a workflow dispatch answers 204 with no run identifier |
| `repository.comments.list` | read | — | |
| `repository.comments.create` | write | marked | the key in a comment of that issue, all pages |
| `channel.repo.reply` | write | marked | as `repository.comments.create`, on the issue or pull request the reply address `<repository>#<number>` names; an address without a number, or of another repository, is refused (contract §7, ADR-0040) |
| `repository.branches.create` | write | marked | the branch by its name, which the service keeps unique; the key as a trailer `Taktus-Idempotency-Key:` in the message of the commit at its head. The branch carries one commit on top of its base with the given files (or none: an empty commit, so that a bare branch is findable too), made through the object interface — blobs, a tree, a commit, the reference. A branch of that name whose head carries another key, or none, is somebody else's: `conflict`. **A file keeps the mode it has in the base**: an executable stays executable and a link stays a link, read from the base tree before the new tree is written (DEC-0020). **A file entry may say `executable: true`** — the coding worker's changeset does for a file its index records as `100755` — and is then written with mode `100755`, whether the base has the path or not; `executable: false` writes it plain. Without the flag, a file the base does not have is a plain file (issue #28) |
| `repository.files.read` | read | — | one file at a ref — a branch name or a 40-character commit — with its content (text when it decodes as UTF-8, base64 otherwise) and **the commit it was read at**: a branch is resolved to its commit first and the file read at that commit, so that the two agree when the branch moves in between. A directory, a link or a submodule is `invalid`; a file above the contents interface's size limit is read as a blob. One request for a commit, two for a branch |
| `repository.files.list` | read | — | the immediate entries of one directory at a ref, each with its name, path and type — `file`, `dir`, `symlink` or `submodule` — sorted by name, with the commit the ref resolved to, as `repository.files.read` resolves it. A path that names a file is `invalid`. P-03 reads the directory of open records with it (issue #70) |
| `repository.labels.set` | write | marked | the label itself, on the issue: the operation reads the issue's labels before adding any, and a repeat that finds every requested label present adds nothing and reports `replayed`. **Weaker than a key in a body, and stated so:** the lookup is by label, not by key, so a repeat with a *new* key that sets a label already present is reported replayed as well — it acts on nothing either way |

The mark is an HTML comment at the end of the body, `<!-- taktus-idempotency-key … -->`,
invisible when rendered, or a git trailer in a commit message. Every `marked` operation looks
for it **before** acting ([`operations.py`](operations.py)); the connector keeps no memory of
what it did, the service does, and that memory survives a restart of the connector. The key the
run derives is `taktus:<run id>:<step id>:<attempt>`. The test that tries to open a pull request
twice for the same step across a restart is `tests/adapters/connectors/test_repository_actions.py`
against the fake service, and `test_repository_live.py` against the real one — a branch, a pull
request, a comment and a label, each twice across two connectors, with one record each; it runs
when `TAKTUS_LIVE_REPOSITORY` and an identity — the app's two variables, or `REPOSITORY_TOKEN` —
are set, and skips otherwise.

**What it does when the target offers nothing to recognise a repeat by.**
`repository.pipelines.trigger` is the honest case of the contract's §4: a workflow dispatch
answers with no identifier and takes no key, so the connector declares `idempotency: none`,
acts every time, and reports `replayed: false` always. Taktus never repeats it on its own: a
call whose outcome is unknown ends the step failed, and the person who resumes the run has
checked the service first (`docs/architecture/contracts.md` §2.2). The connector does not
pretend — it does not, for example, look for a recent run of that workflow and call it ours.

Consumption is counted in `quota` units named `requests`: every result reports how many API
requests the call made.

## Credentials

Two, referenced by the names below, created and mapped by the operator; `CREDENTIALS.md`
describes both as parameters:

| Name | Purpose | How it reaches the connector |
|---|---|---|
| `REPOSITORY_TOKEN` | actions: the **requesting identity's** token, with that identity's scopes — Taktus's own app's installation token when the app is configured | as the app: minted by the connector from the app's key ([`app.py`](app.py)); otherwise referenced in the call's context and read at the moment of the call from a file — the one the reference names, or `TAKTUS_CREDENTIAL_<NAME>_FILE` — or from the variable of its name. Never stored |
| `REPOSITORY_WEBHOOK_SECRET` | intake: the secret the webhook signs with — the app's webhook secret when the app delivers the events | read at the moment of the intake call from the file `TAKTUS_CREDENTIAL_REPOSITORY_WEBHOOK_SECRET_FILE` names, or from the variable of that name when no file is named |

The connector has no token of its own to fall back on. A call that references no credential, or
one that is not available, ends `unauthenticated` without a request. A token the service refuses
for a write ends `forbidden`. Whoever cannot do something on the service cannot do it through
Taktus either.

### As Taktus's own app (the default) or with a token

An **app** is an identity of its own on the service, not a person, installed on chosen
repositories with chosen permissions (ADR-0033, DEC-0058). The connector acts as the app when
both of these are set, and refuses to start when one is set without the other:

| Variable | What it holds |
|---|---|
| `TAKTUS_REPOSITORY_APP_ID` | the app's identifier, configuration key `repository.app_id`; not a secret, and not logged |
| `TAKTUS_CREDENTIAL_REPOSITORY_APP_KEY_FILE` | the path of the file that holds the app's private key, credential `repository_app_key` |

The app is then the identity behind the name `REPOSITORY_TOKEN`, and behind that name alone. For
a call that references it, the connector signs a statement with the key (a JWT, RS256, valid nine
minutes), asks the service for the app's installation on the repository and exchanges the
statement for an installation token **for this one repository**. The token lives an hour. It is
held in memory, used for every call while more than five minutes are left, and replaced before
that; it is never written anywhere. The key is read from its file at each minting, so a key
replaced in the file takes effect at the next one. The two minting requests count as the
consumption of the call that needed them.

A refusal while minting ends the call `unauthenticated`, with no effect, not retryable, and says
why: the key was not accepted, the app is not installed on the repository (or its installation
was removed), or the installation is suspended. A held token the service refuses is dropped; the
call ends `unauthenticated`, and the next call mints anew and gives the reason. What the app writes
appears under the app's name, as an automation.

Without the two variables the connector acts with the value the runtime puts under the
referenced name — a personal token, for a tenant that has no app.

## Errors

The service's answers map to the contract's causes ([`api.py`](api.py)): 401 `unauthenticated`,
403 `forbidden` (or `unavailable` when the rate limit is exhausted), 404 `not_found`, 400 and 422
`invalid` (or `conflict` when the message says a record already exists), 409 `conflict`, 429 and
5xx `unavailable`. Every other status — a redirect, 405, 410 — is one the connector was not written
for, and is `unexpected`: the service's interface may have changed (ADR-0047). A connection that
could not be made is `unavailable` with no effect; a request that was sent and never answered is
`unknown` with effect `unknown`. A success the connector cannot read — a body that is not JSON, a
shape an operation does not foresee — is `unexpected` for a read, which acted on nothing, and
`unknown` with effect `unknown` for a write, which may have acted. Those are the only cases in
which the connector does not know whether it acted.

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
