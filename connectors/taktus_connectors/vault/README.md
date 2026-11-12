# The secret store connector — HashiCorp Vault, KV version 2

The connector contract v1 ([`contracts/connector/v1`](../../../../../../contracts/connector/v1/README.md))
over the metadata of HashiCorp Vault's KV secrets engine version 2: which secrets a store
holds under a folder, when each was created and when its current value was set. Everywhere
else it is the capability `secrets.metadata`. **It never reads a secret's value.**

It is proof and example, not a requirement: the control plane runs with it removed.

```
uv run python -m taktus_connectors.vault --port 9124 --target https://vault.example:8200
```

serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`.

| Argument | Meaning |
|---|---|
| `--target` | the store's address; required, no default |
| `--mount` | the mount of the KV version 2 engine (default `secret`) |
| `--folder` | the folder under the mount the walk starts in (default the mount's root) |
| `--namespace` | the namespace every request names as `X-Vault-Namespace`, where the store has namespaces (none by default) |
| `--timeout` | the longest one request may take, in seconds (default 30) |

The folder is `--folder` and not `--path`: `--path` is where MCP is served, as for every
connector here.

## What it declares

One operation of effect `read`, `secrets.metadata.list`. Every request to the store is one unit.

| Input | Meaning |
|---|---|
| `prefix` | only the secrets whose name starts with it, optional; a folder that cannot hold such a name is not listed |
| `limit` | at most this many secrets, 1 to 500 (default 100) |

The output is `secrets`, the oldest change first, `complete` and `read_at`. A secret's `name`
is its path under the mount, `app/db`. The other fields, as the store states them:

| Field | From |
|---|---|
| `created_at` | the metadata's `created_time`: the first version |
| `changed_at` | the `created_time` of the version `current_version` names: when the current value was written |
| `age_days` | whole days from `changed_at` to the reading, rounded down |
| `rotation` | `{"automatic": null, "period_days": null, "next_at": null}`: the engine keeps the versions a writer creates and has no rotation of its own |
| `expires_at` | null: `delete_version_after` sets when a version is deleted, and that delete can be undone (`undelete`); a secret does not expire |
| `last_accessed_at` | null: the engine records no read |

The API does not define `updated_time`. Its example shows it equal to the newest version's
`created_time`, but it is not used, because a change of the metadata alone may move it.

A secret whose change the store does not state comes last. **No person is ever copied**: each
version's `created_by` names who wrote it, and the connector drops it (principle 14).

The walk is bounded: folders at most 10 deep, at most 100 lists and 1000 metadata reads.
A walk cut by a bound reports `complete: false`.

## What it asks, and what it never asks

| Request | What for |
|---|---|
| `GET /v1/<mount>/metadata/<folder>?list=true` | the keys of a folder; a key ending in `/` is a folder below it |
| `GET /v1/<mount>/metadata/<name>` | one secret's metadata |

The API documents the list as the verb `LIST` and says a `GET` with `list=true` is the same
request. The `GET` is used because a proxy on the way may refuse a verb it does not know.

**Never asked:** `/v1/<mount>/data/<name>`, the one endpoint of the engine that answers a
value; nor `subkeys`, `delete`, `undelete`, `destroy` or `config`. The token needs only the
capability `list` and `read` on `<mount>/metadata/*`.

| The store's answer | Cause |
|---|---|
| 404 on a list with `{"errors": []}` | an empty folder: no error, the API documents it for a list without results |
| 404 on a list otherwise: an unknown mount | `invalid` |
| 404 on a metadata read | the secret was removed after it was listed; it is skipped |
| 400 | `invalid` |
| 401 | `unauthenticated` |
| 403 | `forbidden`: the API answers it for a token it does not admit as for one without the permission, and the two cannot be told apart |
| 429, 5xx, no answer in time, no connection | `unavailable`, retryable |
| anything else | `unexpected` |

## Credentials

| Name | Purpose | How it reaches the connector |
|---|---|---|
| `SECRETS_TOKEN` | actions: the **requesting identity's** token, sent as `X-Vault-Token`, under a policy with `list` and `read` on `<mount>/metadata/*` and nothing on `<mount>/data/*` | the file `TAKTUS_CREDENTIAL_SECRETS_TOKEN_FILE` names, read at the moment of each call, never stored |

The contract has no connector without the requesting identity's credential (C-03): a call
that references none is refused. The token goes to the configured address and nowhere else.

## Documentation it follows

- KV secrets engine version 2 API: https://developer.hashicorp.com/vault/api-docs/secret/kv/kv-v2
  (list secrets, read secret metadata, `delete_version_after`, undelete)
- HTTP API overview: https://developer.hashicorp.com/vault/api-docs
  (`LIST` and `GET ?list=true`, `X-Vault-Token`, `X-Vault-Namespace`, status codes, a 404 for a
  list without results)

## Conformance

```
uv run taktusctl conformance run --contract connector/v1 \
    --endpoint http://127.0.0.1:9124/mcp --scenario connectors/taktus_connectors/vault/scenario.json
```

[`scenario.json`](scenario.json) lists the secrets of the fake under
`tests/fakes/secret_store_service.py`, and a `limit` of 0 as the invalid call. It names no
write, and C-05 passes as not applicable.
