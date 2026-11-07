# The site connector — the Firebase Hosting REST API

`deployment.sites` over the Firebase Hosting REST API v1beta1: a site whose content is a version
its own build uploaded and finalized, put live by a release, and put back on an earlier version
by another release. This directory, this file and the configuration that points at it are the
only places in the repository that name the product. Everywhere else it is
`deployment.sites` (ADR-0211).

```
uv run python -m taktus_connectors.firebase --port 9132
```

serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`. `--target` is the
API's address, `https://firebasehosting.googleapis.com` unless given. Point it at the fake under
`tests/fakes/hosting_releases_service.py` to run without the service.

The documentation followed:
[`sites.releases`](https://firebase.google.com/docs/reference/hosting/rest/v1beta1/sites.releases)
with its `create` and `list`,
[`sites.channels.releases`](https://firebase.google.com/docs/reference/hosting/rest/v1beta1/sites.channels.releases)
for the `Release` resource,
[`sites.channels`](https://firebase.google.com/docs/reference/hosting/rest/v1beta1/sites.channels)
for the live channel's current release,
[`sites.versions`](https://firebase.google.com/docs/reference/hosting/rest/v1beta1/sites.versions)
with its `get`, and
[OAuth 2.0 for server to server applications](https://developers.google.com/identity/protocols/oauth2/service-account#httprest).

## What it declares

| Operation | Effect | Idempotency | What it does, and how a repeat is recognised |
|---|---|---|---|
| `deployment.sites.read` | read | — | `GET sites/<site>/channels/live`: `live`, the version the live channel's current release serves, the last segment of its name. With `version`, `GET sites/<site>/versions/<version>` too: its `state` as the API names it, `ready` when it is `FINALIZED`, and `rolled_out` when it is ready and live |
| `deployment.sites.release` | write | marked | `POST sites/<site>/releases?versionName=sites/<site>/versions/<version>`: the version put live. The release's `message` is the caller's `message`, if any, followed by `taktus:` and the first 16 hexadecimal digits of the SHA-256 of the idempotency key. Before writing, the site's releases are listed page by page: a release whose message carries the mark is the original, replayed. A version that is not finalized is `conflict`, before anything is written. The output names the version `live`, the one live before as `previous` (null on a repeat) and the `release` |
| `deployment.sites.rollback` | write | marked | the same release, of the earlier version `version` names, which is required: the version live before a release is read before it, and the process names it. The mark is the release's. The API records the release's `type` itself |

A message the caller gives is at most 400 characters; the API keeps 512, and the mark takes the
rest. How far back a rollback reaches is the versions the site keeps; a version the API has
deleted or let expire is not finalized, `conflict`. Consumption is counted in `quota` units
named `requests`, the exchange of the key for a token among them. A timed-out write is `unknown`
with effect `unknown`; a repeat with the same key finds what it wrote.

## Credentials

One, `SITES_TOKEN`: the key of a service account, as JSON as Google issues it, with the role
Firebase Hosting Admin on the project — nothing else (`CREDENTIALS.md`). For every call the
connector signs a statement with the key and exchanges it at the key's own `token_uri` for an
access token of the scope `https://www.googleapis.com/auth/firebase.hosting`; nothing is kept
between calls. The key is referenced by name in the context of every call and read at the moment
of the call from the file `TAKTUS_CREDENTIAL_SITES_TOKEN_FILE` names. The connector has no key of
its own.

## Conformance

```
uv run taktusctl conformance run --contract connector/v1 \
    --endpoint http://127.0.0.1:9132/mcp --scenario connectors/taktus_connectors/firebase/scenario.json
```

[`scenario.json`](scenario.json) reads the site `web`, releases the fake's second version to it
twice under one key and once under another — each new key a release of its own — and asks for a
name the API cannot hold. Against the real API it releases to the site's live channel: point it
at a sandbox site, and at a version its build finalized.
