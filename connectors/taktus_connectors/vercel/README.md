# The site connector — Vercel's REST API

`deployment.sites` over the Vercel REST API: a project's production deployment read, a
deployment the platform already built promoted to production, and production pointed back at
an earlier deployment. This directory, this file and the configuration that points at it are
the only places in the repository that name the product. Everywhere else it is
`deployment.sites`.

It follows the API's reference, <https://vercel.com/docs/rest-api>: *Find a project by id or
name* (`GET /v9/projects/{idOrName}`), *Get a deployment by ID or URL*
(`GET /v13/deployments/{idOrUrl}`), *Point production traffic to a given deployment*
(`POST /v10/projects/{projectId}/promote/{deploymentId}`) and *Point production traffic to a
previous production deployment by ID* (`POST /v1/projects/{projectId}/rollback/{deploymentId}`),
and the machine-readable specification at <https://vercel.com/openapi.json> for the project's
`targets.production` and `lastAliasRequest`.

```
uv run python -m taktus_connectors.vercel --port 9134 --team team_example
```

serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`. `--target` is the API's
address, `https://api.vercel.com` unless given. `--team` names the team every request is made on
behalf of, as the API's `teamId`; without it, the token's own account. Point `--target` at the
fake under `tests/fakes/site_deployments_service.py` to run without the platform.

The connector promotes; it never builds. A deployment is built by the platform for production
with the automatic assignment of production domains switched off, or by the business's own
pipeline, and the connector promotes it on the process's word.

## What it declares

| Operation | Effect | Idempotency | What it does, and how a repeat is recognised |
|---|---|---|---|
| `deployment.sites.read` | read | — | the project: `live`, the identifier of `targets.production`. With `version`, the deployment: its `readyState` as `state`, `ready` when it is `READY`, and `rolled_out` when it is ready and production serves it. A deployment of another project is `not_found` |
| `deployment.sites.release` | write | none | the promotion of the deployment `version` names. Before writing, the project is read: production serving it already, or a newest promotion or rollback to it (`lastAliasRequest`) that is `pending`, `in-progress` or `succeeded`, is the original, replayed. Not a mark of the key, so declared `none`: a repeat after somebody else promoted the same deployment reports replayed too. A deployment that is not `READY` is `conflict`, and nothing is written |
| `deployment.sites.rollback` | write | none | the rollback to the earlier production deployment `version` names, which is required; recognised as a release is |

`name` is the project's identifier or its name. Both writes read the project again after the
write and answer `{name, live, previous}`: what production serves at that moment, and what it
served before; `previous` is null on a replay. The platform may carry a promotion out after it
answered (202): `live` is then still the earlier deployment, and `deployment.sites.read` with the
version says when it is `rolled_out`. The record a write names is `<project>@<version>`, the same
on a repeat.

| The platform's answer | Cause |
|---|---|
| 400, 422 | `invalid` |
| 401 | `unauthenticated` |
| 402, 403: the token or the plan may not do this | `forbidden` |
| 404, 410: no such project or deployment, or one removed | `not_found` |
| 409 | `conflict` |
| 429, 5xx, a refused connection | `unavailable`, retryable |
| a timeout on a write, or no reading after it | `unknown`, effect `unknown`: a repeat finds the promotion |
| anything else | `unexpected` |

Consumption is counted in `quota` units named `requests`.

## Credentials

One, `SITES_TOKEN`: the requesting identity's access token, sent as a bearer token. The platform
scopes a token to an account or a team and an expiry, not to operations: it is created for the
one team that holds the project, with an expiry, by an account whose team role may promote and
roll back production deployments (`CREDENTIALS.md`). It is referenced by name in the context of
every call and read at the moment of the call from the file `TAKTUS_CREDENTIAL_SITES_TOKEN_FILE`
names. The connector has no token of its own.

## Conformance

```
uv run taktusctl conformance run --contract connector/v1 \
    --endpoint http://127.0.0.1:9134/mcp --scenario connectors/taktus_connectors/vercel/scenario.json
```

[`scenario.json`](scenario.json) reads the project `web` and asks for a name the API cannot hold.
It names no write. The host's API gives the idempotency key no place: the request that publishes
takes no body. Both writes are therefore declared `none` (ADR-0024 §3, ADR-0211): the engine never
repeats them on its own, and a run that stopped inside one goes to a person. The connector still
reads the state before it writes, so a repeat a person starts for a version already live changes
nothing and reports `replayed`. C-05 passes as not applicable, and the connector offers no fault
for it. The
repeat is proven by `tests/adapters/connectors/test_site_deployments_connector.py`, against the
fake, with a fresh connector for every call and a promotion the platform carries out later.
