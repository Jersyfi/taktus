# The directory connector — SCIM 2.0

The connector contract v1 ([`contracts/connector/v1`](../../../../../../contracts/connector/v1/README.md))
over SCIM 2.0, the open standard for an organisation's account directory: the schemas of
[RFC 7643](https://www.rfc-editor.org/rfc/rfc7643) and the protocol of
[RFC 7644](https://www.rfc-editor.org/rfc/rfc7644). Everywhere else it is the capabilities
`directory.accounts` and `directory.groups` (ADR-0209). It serves any directory or identity provider that offers a SCIM
service provider endpoint for reading.

It is proof and example, not a requirement: the control plane runs with it removed.

```
uv run python -m taktus_connectors.scim --port 9151 --target https://idp.example/scim/v2
```

serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`. `--target` is the
service's base address, under which `/Users` and `/Groups` are found; it has no default, because
SCIM has no address of its own. Added to an instance by one entry of `TAKTUS_CONNECTORS`:
`directory.accounts=http://directory-connector:9151/mcp`, and `directory.groups` at the same
address.

## What it declares

Two operations of effect `read`, one request per page each. Revoking access stays a person's
(UC-03 B-5.03): nothing here writes.

`directory.accounts.list`:

| Input | Meaning |
|---|---|
| `group` | a group's display name, optional: only the accounts that are its members |
| `limit` | at most this many accounts, 1 to 10000 (default 1000) |

Each account is reduced to these fields (RFC 7643 §4.1):

| Field | Meaning |
|---|---|
| `id` | the service's identifier of the account |
| `user_name` | `userName`, the name the account signs in with |
| `user_type` | `userType`, where the service gives it: a person's or a service account |
| `active` | `false` only where the service says `active: false` |
| `groups` | the display names of the groups it is in |
| `roles`, `entitlements` | the values of those attributes, where the service gives them |
| `last_modified` | `meta.lastModified` |

**Not copied:** the account's name, display name, e-mail addresses, phone numbers, addresses and
photos. No review needs them, and what is not read cannot leak.

**What SCIM does not say.** The core schema has no last sign-in. Whether an account is still in
use can be read only from `active` and from when the account last changed. A review that needs
the last sign-in needs the directory's own interface, which this connector does not read.

`directory.groups.list` takes `name`, a display name, optional, and `limit`; each group is `id`,
`display_name`, `members` (the members' identifiers) and `member_count`.

The output of both carries `complete`: whether every resource was read. Pages are of 100
(`startIndex`, `count`, RFC 7644 §3.4.2.4), at most 100 pages. A group is found by the filter
`displayName eq "<name>"` (§3.4.2.2); a name with a quotation mark or a backslash is refused
before the service is asked. `attributes` (§3.4.2.5) asks only for what is read.

| The service's answer (§3.12) | Cause |
|---|---|
| 400 (`invalidFilter`, `tooMany`, …), 404, 501; a group name nobody holds | `invalid` |
| 401 | `unauthenticated` |
| 403 | `forbidden` |
| 429, 5xx but 501, no answer in time, no connection | `unavailable`, retryable |
| anything else, a body that is not a `ListResponse` | `unexpected` |

## Credentials

| Name | Purpose | How it reaches the connector |
|---|---|---|
| `DIRECTORY_TOKEN` | actions: the **requesting identity's** bearer token for the SCIM endpoint, with read access to users and groups and nothing else | the file `TAKTUS_CREDENTIAL_DIRECTORY_TOKEN_FILE` names, read at the moment of each call, never stored |

The contract has no connector without the requesting identity's credential (C-03). The token
goes to the configured address and nowhere else. `CREDENTIALS.md` describes it.

## Conformance

```
uv run taktusctl conformance run --contract connector/v1 \
    --endpoint http://127.0.0.1:9151/mcp --scenario connectors/taktus_connectors/scim/scenario.json
```

[`scenario.json`](scenario.json) lists the accounts of the fake under
`tests/fakes/directory_service.py`, and asks for the members of a group the fake does not hold as
the invalid call. It names no write, and C-05 passes as not applicable. `--fault NAME` breaks
exactly one check (`connectors/serving.py`); `tests/conformance/test_connector_v1_business.py`
runs every fault.
