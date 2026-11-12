# The functions connector — the Cloud Functions API v2

`deployment.sites` over the Cloud Functions API v2: a function of one project's location, whose
source is an archive the business's own build uploaded, deployed by a release and put back on an
earlier archive by a rollback. A function has no container image and no number of replicas; the
platform builds it from the archive. That is a hosted version, the shape of `deployment.sites`,
not of `deployment.workloads` (ADR-0211 §2, ADR-0269). It serves the operations the site
connectors serve, under the same names and with the same inputs, so that the site version of
B-8.05 runs on it unchanged, and so does the hosted version of B-8.06
(`B-8.06-hosted-deployment.yaml`). This directory, this file and the configuration that points at it
are the only places in the repository that name the product. Everywhere else it is
`deployment.sites`.

```
uv run python -m taktus_connectors.cloudfunctions --port 9184 \
    --project shop-prod --location europe-west1
```

serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`. `--target` is the
API's address, `https://cloudfunctions.googleapis.com` unless given. Point it at the fake under
`tests/fakes/functions_service.py` to run without the service; the fake holds the project
`example`, the location `europe-west1` and the function `web`.

The documentation followed:
[`projects.locations.functions`](https://docs.cloud.google.com/functions/docs/reference/rest/v2/projects.locations.functions)
for the `Function` resource, its `BuildConfig`, `StorageSource`, `SourceProvenance` and `State`;
its [`get`](https://docs.cloud.google.com/functions/docs/reference/rest/v2/projects.locations.functions/get)
and [`patch`](https://docs.cloud.google.com/functions/docs/reference/rest/v2/projects.locations.functions/patch)
with its `updateMask`;
[`projects.locations.operations`](https://docs.cloud.google.com/functions/docs/reference/rest/v2/projects.locations.operations)
for the `Operation` a patch answers;
[the requirements of labels](https://docs.cloud.google.com/resource-manager/docs/labels-overview);
[the roles of Cloud Functions](https://docs.cloud.google.com/functions/docs/reference/iam/roles);
and [OAuth 2.0 for server to server applications](https://developers.google.com/identity/protocols/oauth2/service-account#httprest).

## A version

A version is one source archive in Cloud Storage, written `<bucket>/<object>#<generation>`, for
example `example-sources/web/1.1.0.tar.gz#1730000000000002`. The generation is required: without
it the API takes the object's latest generation, and a version would not name one archive for
good. The version a function serves, `live`, is the archive its last successful build was made
from (`buildConfig.sourceProvenance.resolvedStorageSource`), or its source where no provenance
is given. Uploading the archive is the build's; the connector deploys what was uploaded.

## What it declares

| Operation | Effect | Idempotency | What it does, and how a repeat is recognised |
|---|---|---|---|
| `deployment.sites.read` | read | — | `GET functions/<name>`: `live`, the archive the function serves. With `version`, that version as `{id, state, ready}`: `state` is the function's own (`ACTIVE`, `DEPLOYING`, `FAILED` and the others the API names), `ready` when the version is live and the function `ACTIVE`; `rolled_out` is `ready` |
| `deployment.sites.release` | write | marked | `PATCH functions/<name>?updateMask=buildConfig.source,labels`: the source set to the archive `version` names, which makes the platform build and deploy it. The function's labels are kept, and the label `taktus-key` set to the first 40 hexadecimal digits of the SHA-256 of the idempotency key. Before writing, the function is read: a function whose label is the mark is the original, replayed. A function `DEPLOYING` or `DELETING` is `conflict`, before anything is written. The output names the version put `live`, the one live before as `previous` (null on a repeat), and the `release`, the operation's name (null on a repeat) |
| `deployment.sites.rollback` | write | marked | the same patch, to the earlier version `version` names, which is required: the process reads the live version before the release and names it. The mark is the release's; `to_version` names the version put back |

A write answers a long-running operation; the connector does not wait for it, and a reading says
whether the version is live. An archive the platform cannot build never becomes live: the
reading's `rolled_out` stays false, and the process's wait hands the run to a person.

**The mark is one label.** The function keeps one label `taktus-key`, so a repeat of a write
after another write under another key replaced it acts again. The patch replaces the function's
labels with the ones read and the mark: a label somebody set between the reading and the write
is lost. The API's `Function` carries no `etag` that would refuse such a write.

Consumption is counted in `quota` units named `requests`, the exchange of the key for a token
among them. A timed-out write is `unknown` with effect `unknown`; a repeat with the same key
finds what it wrote.

## Credentials

One, `SITES_TOKEN`, the same parameter as the other site connectors', so that the site version
of B-8.05 runs unchanged: here the key of a service account, as JSON as Google issues it. The
account needs the role Cloud Functions Developer (`roles/cloudfunctions.developer`) on the
project, and Service Account User (`roles/iam.serviceAccountUser`) on the service account the
functions run as and on the one their builds run as — nothing else (`CREDENTIALS.md`). For every
call the connector signs a statement with the key and exchanges it for an access token of the
scope `https://www.googleapis.com/auth/cloud-platform` at the token endpoint (`--token-endpoint`;
by default Google's `https://oauth2.googleapis.com/token`, or `<target>/token` where `--target`
names another address) — never the key's own `token_uri`, which could send a signed statement
elsewhere; nothing is kept between calls. The key is referenced by name in the context of every
call and read at the moment of the call from the file `TAKTUS_CREDENTIAL_SITES_TOKEN_FILE`
names. The connector has no key of its own.

## Conformance

```
uv run taktusctl conformance run --contract connector/v1 \
    --endpoint http://127.0.0.1:9184/mcp --scenario connectors/taktus_connectors/cloudfunctions/scenario.json
```

[`scenario.json`](scenario.json) reads the function `web`, releases the fake's second archive to
it twice under one key and once under another — each new key a deployment of its own — and asks
for a name the API cannot hold. Against the real API it deploys to the function the scenario
names: point it at a sandbox project, and at an archive its build uploaded.
