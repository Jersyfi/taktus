# The reference connector — a repository hosting service

The connector contract v1 ([`contracts/connector/v1`](../../../../../../contracts/connector/v1/README.md))
implemented against GitHub's REST API and webhooks. This directory, this file and the
configuration that points at it are the only places in the repository that name the product.
Everywhere else — processes, blueprints, documents — it is `repository.issues`,
`repository.pullrequests`, `repository.pipelines`, `repository.comments`,
`repository.branches`, `repository.refs`, `repository.labels` and `repository.files`.

It is proof and example, not a requirement: the control plane runs with it removed.

```
uv run python -m taktus_connectors.github --port 9100 --repository owner/name
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
| `repository.issues.list` | read | — | the issues in one state, `open` unless `state` says `closed` or `all`, without pull requests, each in the shape of `repository.issues.read`; page by page, at most twenty pages of 100, and `complete` says whether every page was read, so that a reader that must see every open issue can refuse a reading that stopped short. Each issue carries `idle_hours`, whole hours since its last update at the moment of the reading (ADR-0193 §3) |
| `repository.issues.create` | write | marked | the key in the issue body, among the 100 most recently created issues and, above the newest number that list shows, among the issues read one by one by their number, up to twenty, until a number does not exist. **The issue list lags**: on 2026-10-12 an issue created a second earlier was not in it, and a repeat that looked there alone opened a second issue (issue #300). One issue read by its number is answered as written. A repeat is not recognised after 100 other issues and pull requests were opened in between, nor when more than twenty were opened while the list lagged |
| `repository.issues.close` | write | marked | the key in the comment that says why, among all comments of the item, as `repository.comments.create` finds one; the comment is written first and the item closed as not planned after it, so a repeat that finds the comment closes an item still open and does nothing to one closed. A pull request is closed through the issue interface, which cannot merge it (UC-1.9, ADR-0088) |
| `repository.issues.milestone` | write | marked | the milestone itself, on the item, as a label is for `repository.labels.set`: a repeat that finds it set changes nothing and reports `replayed`. The milestone is found by its title among the open ones; a title no open milestone has is `not_found` (ADR-0088) |
| `repository.pullrequests.read` | read | — | |
| `repository.pullrequests.open` | write | marked | the key in the body of the pull request for that head branch — exact, because the service keeps at most one open pull request per head |
| `repository.pullrequests.list` | read | — | the pull requests in one state, `open` unless `state` says `closed` or `all`, each with its head and the commit at it (`head_sha`), its base, `draft`, its labels, and whole hours `idle_hours` since its last update and `open_hours` since it was opened, at the moment of the reading, and whether it was merged with `merged_hours` since, `null` for one not merged (the service's list gives `merged_at`, never `merged`). With `with_state: true`, the first `limit` of them (at most 30) also carry `behind` and `ahead` — commits, from the service's comparison of base and head — the word of `repository.pipelines.status` for the head, and `head_key`, the key the head commit carries as a trailer, or `null`: three requests each. At most twenty pages of 100; `complete` says whether every one was read (ADR-0193) |
| `repository.pullrequests.files` | read | — | the paths one pull request changes at the head commit the service names when it is read, `head_sha`: each with its status, lines added and removed, the old path of a rename and, with `patches: true`, its patch, cut at 20 000 characters and said so; the sums and `count`. `complete` is false where the service lists more than its 3000 files (ADR-0194) |
| `repository.pullrequests.merge` | write | marked | the pull request itself: merged, with the key as a trailer in its merge commit, is the original, replayed; merged without it is somebody else's merge, `conflict`. It is merged by `merge` or `squash` at the head `sha` names and no other: the service refuses another head (409) and the connector answers `conflict`, as for a pull request the service will not merge (405). A rebase is refused: it writes no commit that could carry the key (ADR-0194) |
| `repository.pipelines.read` | read | — | |
| `repository.pipelines.status` | read | — | the runs for the head of a branch (or a commit), and one word for their state: `none`, `pending`, `success`, `failure` — the pipeline's verdict, never the connector's |
| `repository.pipelines.list` | read | — | the runs in one status — `queued`, `in_progress` (the default) or `completed` — newest first, at most `limit` (100), each with its head commit and its whole minutes since it was created, `age_minutes`, at the moment of the reading (ADR-0193) |
| `repository.pipelines.rerun` | write | marked | the run's own attempt: the call names the attempt it read, and a run whose attempt is higher was rerun since — the repeat changes nothing and reports `replayed`. Otherwise the failed jobs of the completed run are rerun ([Re-run failed jobs](https://docs.github.com/en/rest/actions/workflow-runs#re-run-failed-jobs-from-a-workflow-run)). A run not completed is `conflict` and nothing is written. **Weaker than a key, and stated so:** a rerun by somebody else reads the same (ADR-0201) |
| `repository.pipelines.cancel` | write | marked | the run's own state: a completed run is the repeat's answer, `replayed`, and nothing is sent. Otherwise the run is cancelled ([Cancel a workflow run](https://docs.github.com/en/rest/actions/workflow-runs#cancel-a-workflow-run)); a 409 is read again, and a run completed meanwhile is `replayed`. Force-cancel is never sent (ADR-0201) |
| `repository.pipelines.trigger` | write | **none** | not at all: a workflow dispatch answers 204 with no run identifier |
| `repository.comments.list` | read | — | |
| `repository.runners.list` | read | — | the repository's self-hosted runners ([List self-hosted runners for a repository](https://docs.github.com/en/rest/actions/self-hosted-runners)), each with its id, name, operating system, `status` (`online`, `offline`), `busy` and labels by name; `offline` counts those not online. At most ten pages of 100 (ADR-0201) |
| `repository.ratelimit.read` | read | — | the requesting identity's limits ([Get rate limit status](https://docs.github.com/en/rest/rate-limit/rate-limit)), one entry per resource the service names, the fullest first: `limit`, `used`, `remaining`, `used_share` — used over limit, rounded down to four places, as decimal text — and `reset_minutes`. The service does not count this request (ADR-0201) |
| `repository.advisories.list` | read | — | the dependency alerts ([List Dependabot alerts for a repository](https://docs.github.com/en/rest/dependabot/alerts)) in `state` (default `open`) and optionally of `severity`, newest first: number, severity, `ghsa_id`, `cve_id`, summary, ecosystem, package, manifest, scope, the vulnerable range, `patched` — the first patched version or `null` — its link and `age_days`. The dismisser, the assignees and a dismissal's requester are never copied (principle 14). At most ten pages of 100; the token needs the permission to read the alerts (ADR-0201) |
| `repository.comments.create` | write | marked | the key in a comment of that issue, all pages |
| `channel.repo.reply` | write | marked | as `repository.comments.create`, on the issue or pull request the reply address `<repository>#<number>` names; an address without a number, or of another repository, is refused (contract §7, ADR-0040) |
| `repository.branches.list` | read | — | the branches ([List branches](https://docs.github.com/en/rest/branches/branches#list-branches)), each with its name, `head_sha` and `protected`; with `protected` only those or the others. At most ten pages of 100; `complete` says whether every page was read (ADR-0201) |
| `repository.branches.read` | read | — | a branch by its name, as `repository.branches.create` looks it up, without acting: `exists`, the `sha` at its head, and the `key` that head commit carries as a trailer, or `null`. Given a `key`, `free` says whether a `repository.branches.create` under that key would create the branch or find it as its own — none exists, or its head carries exactly that key; without one, `free` says only that none exists. A run reads it before it spends, so that a branch an earlier attempt left stops the run before its coding step and not after it (ADR-0099) |
| `repository.branches.create` | write | marked | the branch by its name, which the service keeps unique; the key as a trailer `Taktus-Idempotency-Key:` in the message of the commit at its head. The base is a branch by its name or a commit by its full sha — the coding worker's changeset names the commit its workspace was cloned from, and a branch made from it reverts nothing its base branch gained meanwhile (#496). The branch carries one commit on top of its base with the given files (or none: an empty commit, so that a bare branch is findable too), made through the object interface — blobs, a tree, a commit, the reference. A branch of that name whose head carries another key, or none, is somebody else's: `conflict`. **A file keeps the mode it has in the base**: an executable stays executable and a link stays a link, read from the base tree before the new tree is written (DEC-0020). **A file entry may say `executable: true`** — the coding worker's changeset does for a file its index records as `100755` — and is then written with mode `100755`, whether the base has the path or not; `executable: false` writes it plain. Without the flag, a file the base does not have is a plain file (issue #28) |
| `repository.branches.update` | write | marked | the head of the branch: a head that carries the key as a trailer is the original, replayed. Otherwise the base — a branch or a commit — is merged into the branch by the service's merge interface, in one commit whose message carries the key. A branch that contains its base already gets no commit and `updated: false`; a merge with a conflict is `conflict` and writes nothing; with `expected`, a head that is another commit is `conflict` before anything is written (ADR-0193) |
| `repository.branches.commit` | write | marked | the branch's first parents from its head, at most twenty: a commit carrying the key is the original, replayed. Otherwise one commit with the given files and deletions goes on top of the branch through the object interface, each file keeping its mode as for `repository.branches.create`, and the reference is moved forward to it, never forced. `expected` is required: the commit the change was made against — the coding worker's changeset names it as `source` — and a head that is another commit, or one that moves while the commit is written, is `conflict` (ADR-0193) |
| `repository.refs.create` | write | marked | each reference by its exact name, which the service keeps unique; the key as a trailer `Taktus-Idempotency-Key:` in the message of the commit it points at. Up to ten fully qualified names, `refs/<namespace>/<name>`, in one call, each on a commit of its own: a child of `target` (a branch or a commit) with the target's tree, so that it changes nothing and a reference is never mistaken for somebody else's. A reference of that name that carries another key, or none, is somebody else's: `conflict`, naming it; those created before it stay, and a repeat with the same key finds them. Creating a reference is atomic on the service: of two callers that create the same name, exactly one gets it. What a reference means is the caller's — P-03 reserves the numbers of the records its change adds with it (ADR-0095); the connector knows no namespace |
| `repository.files.read` | read | — | one file at a ref — a branch name or a 40-character commit — with its content (text when it decodes as UTF-8, base64 otherwise) and **the commit it was read at**: a branch is resolved to its commit first and the file read at that commit, so that the two agree when the branch moves in between. A directory, a link or a submodule is `invalid`; a file above the contents interface's size limit is read as a blob. One request for a commit, two for a branch |
| `repository.files.read_many` | read | — | up to 100 files at one ref, **all at the same commit**: the ref is resolved once and every path read at the commit it resolved to, so that a reader that puts them together — the run of the guides (ADR-0066) — has the repository as it was at one moment even when the branch moves while it reads. A path that names no file at the commit is answered with content `null`, in its place, never left out; the reader decides what that means. One request for the ref, one per path |
| `repository.files.list` | read | — | the immediate entries of one directory at a ref, each with its name, path and type — `file`, `dir`, `symlink` or `submodule` — sorted by name, with the commit the ref resolved to, as `repository.files.read` resolves it. A path that names a file is `invalid`. P-03 reads the directory of open records with it (issue #70) |
| `repository.code.search` | read | — | the files of the default branch whose text contains `text` (1 to 128 characters, one line, no double quote), through the service's code search `"<text>" repo:<owner>/<name>`: each file's `path` and `sha`, sorted by path, with the service's `total`. At most ten pages of 100, the service's own limit of 1000; `complete` says whether the service searched everything and every result was read. The service searches only the default branch and only what it has indexed: a file too large or too new is not found (ADR-0310). B-2.04 finds a retiring model's identifier with it |
| `repository.members.list` | read | — | the repository's collaborators, each as `account` (its number, as the intake names a sender), `kind`, `name` (the login) and `role` — the service names no address there. It needs only read access to the repository's metadata. At most twenty pages of 100; `complete` says whether every page was read. Nothing calls it yet: it is the proof DEC-0127 rests on (NTC-0107) |
| `repository.labels.set` | write | marked | the label itself, on the issue: the operation reads the issue's labels before adding any, and a repeat that finds every requested label present adds nothing and reports `replayed`. **Weaker than a key in a body, and stated so:** the lookup is by label, not by key, so a repeat with a *new* key that sets a label already present is reported replayed as well — it acts on nothing either way |
| `repository.labels.remove` | write | marked | the label's absence, on the issue: the operation reads the issue's labels before removing any, and a repeat that finds none of the requested labels present removes nothing and reports `replayed`. A label somebody else removed between the reading and the removal is gone either way, and no error. At most five labels in one call, one request each. Weaker than a key in a body, as `repository.labels.set` is (ADR-0097) |

The mark is an HTML comment at the end of the body, `<!-- taktus-idempotency-key … -->`,
invisible when rendered, or a git trailer in a commit message. Every `marked` operation looks
for it **before** acting ([`operations.py`](operations.py)); the connector keeps no memory of
what it did, the service does, and that memory survives a restart of the connector. **A lookup
reads only what the service answers as written** (ADR-0024, amendment of 2026-10-12): a pull
request by its head, the comments of one issue, a reference, one issue by its number. A list
the service fills later — its issue list, its search — is not a lookup on its own. The key the
run derives is `taktus:<run id>:<step id>:<attempt>`. The test that tries to open a pull request
twice for the same step across a restart is `tests/adapters/connectors/test_repository_actions.py`
against the fake service, and `test_repository_live.py` against the real one — a branch, a pull
request, a comment, a label and an issue, each twice across two connectors, with one record
each, the issue's repeat at once; it runs
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

**Its own secrets are never a call's credential.** A call that names the app's key or the webhook
secret, by name or by the file that holds it, acts with nothing and ends `unauthenticated`; a
transport fault is named by its type, never by its text, which can quote a header (issue #267).

**The infrastructure reads and writes need permissions of their own** (ADR-0201): rerunning
and cancelling a run need *Actions: write*; the runners need *Administration: read*, the
service's rule for a repository's self-hosted runners; the alerts need *Dependabot alerts:
read*. The rate limit needs none. A process that does not use them leaves them out of the app's
or the token's permissions, and a call without them is `forbidden`.

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
webhook secret) before the body is read ([`intake.py`](intake.py)). Events normalised, as the
kinds of the events contract (`contracts/events/v1` §2): `issue.opened`, `issue.labelled` (one
per label added, with the label's name), `issue_comment.created`, `pull_request.opened`,
`pipeline_run.completed` (from `workflow_run`) and `branch.pushed` (from `push`, with the branch,
the head commit and every path the pushed commits changed, as the service lists them; a push of
a tag or a deleted branch is refused as `unsupported_event`). A comment that carries the
connector's own mark is refused as `own_action`. A comment, an issue opened and a pull request
opened carry the text their sender wrote. A label added, a pipeline run and a push do not: their
`intent.authored` is `false`, because the text they carry — the issue's, the run's name, a commit
message — is not what the sender wrote in this event.
The recorded payloads under [`payloads/`](payloads/) are real deliveries with every identifier,
name and URL replaced by a placeholder.

## Faults

`--fault NAME` makes the connector break exactly one conformance check, so that the suite can be
shown to catch it ([`faults.py`](faults.py)); `--list-faults` prints them. `make gate-conformance`
runs the suite against every fault and expects exactly that check to fail.

## Conformance

```
uv run taktusctl conformance run --contract connector/v1 \
    --endpoint http://127.0.0.1:9100/mcp --scenario connectors/taktus_connectors/github/scenario.json
```

[`scenario.json`](scenario.json) runs against the fake and against the real service alike: the
branch write comes before the pull request, and both name the branch through `{{shared}}`, so
that every pull request comes from a branch the scenario made (CONFORMANCE.md §2). Like the
real service, the fake refuses a pull request whose head branch does not exist, and the
conformance gate starts it with an issue list that lags. Against the real service the suite
writes into the repository the connector serves: point it at a sandbox, never at a repository
that matters, and expect what it leaves there — an issue, two branches, two references under
`refs/conformance/`, two pull requests and two comments per run, besides the issue it reads and comments on, number 1. The scenario names
the app's key as `credentials.app`, so that C-04 searches for it where the suite has it.

On 2026-10-12 the suite passed C-01 to C-09 against a private sandbox repository, the connector
acting as the app; C-10 stays pending.
