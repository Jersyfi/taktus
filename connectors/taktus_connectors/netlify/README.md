# The site connector — Netlify's API

`deployment.sites` over the Netlify API: a site's published deploy read, a deploy the service
already built published, and an earlier deploy put back. This directory, this file and the
configuration that points at it are the only places in the repository that name the product.
Everywhere else it is `deployment.sites`.

It follows the API's reference, <https://open-api.netlify.com/> (`getSite`, `getSiteDeploy`,
`restoreSiteDeploy`), and its authentication, <https://docs.netlify.com/api/get-started/>.

```
uv run python -m taktus_connectors.netlify --port 9133
```

serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`. `--target` is the API's
address, `https://api.netlify.com` unless given. Point it at the fake under
`tests/fakes/site_deploys_service.py` to run without the service.

The connector publishes; it never builds. A deploy is built by the business's own pipeline or
the service's build, with automatic publishing locked or as a deploy not yet published, and the
connector publishes it on the process's word.

## What it declares

| Operation | Effect | Idempotency | What it does, and how a repeat is recognised |
|---|---|---|---|
| `deployment.sites.read` | read | — | `GET /api/v1/sites/<site_id>`: `live`, the identifier of the `published_deploy`. With `version`, `GET /api/v1/sites/<site_id>/deploys/<version>`: its `state` as the service words it, `ready` when the state is `ready`, and `rolled_out` when it is ready and the site publishes it |
| `deployment.sites.release` | write | none | `POST /api/v1/sites/<site_id>/deploys/<version>/restore`, which publishes the deploy. Before writing, the site is read: a site that already publishes the deploy is the original, replayed. Not a mark of the key, so declared `none`: a repeat after somebody else published the same deploy reports replayed too. A deploy whose state is not `ready` is `conflict`, and nothing is written |
| `deployment.sites.rollback` | write | none | the same request for an earlier deploy, the one `version` names, which is required; recognised as a release is |

`name` is the site's identifier, or its name, which the API takes in its place. Both writes
answer `{name, live, previous}`: the deploy published, and the one published before; `previous`
is null on a replay. The record a write names is `<site>@<version>`, the same on a repeat.

| The service's answer | Cause |
|---|---|
| 400, 422 | `invalid` |
| 401 | `unauthenticated` |
| 403 | `forbidden` |
| 404: no such site or deploy | `not_found` |
| 409 | `conflict` |
| 429, 5xx, a refused connection | `unavailable`, retryable |
| a timeout on a write | `unknown`, effect `unknown`: a repeat finds the deploy published |
| anything else | `unexpected` |

Consumption is counted in `quota` units named `requests`.

## Credentials

One, `SITES_TOKEN`: the requesting identity's personal access token, or an OAuth token, sent as
a bearer token. The service grants no narrower scope: the token acts as the account it belongs
to, so it belongs to an account that is a member of the site's team with the rights to publish
deploys and no more than the team role allows (`CREDENTIALS.md`). It is referenced by name in
the context of every call and read at the moment of the call from the file
`TAKTUS_CREDENTIAL_SITES_TOKEN_FILE` names. The connector has no token of its own.

## Conformance

```
uv run taktusctl conformance run --contract connector/v1 \
    --endpoint http://127.0.0.1:9133/mcp --scenario connectors/taktus_connectors/netlify/scenario.json
```

[`scenario.json`](scenario.json) reads the site `web` and asks for a name the API cannot hold.
It names no write. The host's API gives the idempotency key no place: the request that publishes
takes no body. Both writes are therefore declared `none` (ADR-0024 §3, ADR-0211): the engine never
repeats them on its own, and a run that stopped inside one goes to a person. The connector still
reads the state before it writes, so a repeat a person starts for a version already live changes
nothing and reports `replayed`. C-05 passes as not applicable, and the connector offers no fault
for it. The
repeat is proven by `tests/adapters/connectors/test_site_deploys_connector.py`, against the
fake, with a fresh connector for every call.
