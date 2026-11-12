# The customer system connector — the HubSpot CRM API v3

The connector contract v1 ([`contracts/connector/v1`](../../../contracts/connector/v1/README.md))
over the contacts and notes of the HubSpot CRM API. This directory, this file and the
configuration that points at it are the only places that name the product. Everywhere else it
is the capability `crm.contacts` (ADR-0209). Taktus is not the customer system: it finds a
contact, creates one for a new address and notes a touchpoint, and nothing more.

It is proof and example, not a requirement: the control plane runs with it removed.

```
uv run python -m taktus_connectors.hubspot --port 9156
```

serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`. `--target` is the
API's address, `https://api.hubapi.com` by default; point it at the fake under
`tests/fakes/customer_system_service.py` to run without a network. Added to an instance by one
entry of `TAKTUS_CONNECTORS`: `crm.contacts=http://crm-connector:9156/mcp`.

## The documentation it follows

- [Contacts](https://developers.hubspot.com/docs/api-reference/crm-contacts-v3/guide) and
  [Create a contact](https://developers.hubspot.com/docs/api-reference/crm-contacts-v3/basic/post-crm-v3-objects-contacts):
  `POST /crm/v3/objects/contacts` with `properties`, answered 201 with `id`, `properties`,
  `createdAt`, `updatedAt`, `archived`; the address as the contact's unique identifier.
- [Search](https://developers.hubspot.com/docs/api-reference/search/guide): `filterGroups`
  OR-ed, `filters` AND-ed, the operators `EQ` and `CONTAINS_TOKEN`, one sort, `limit` up to
  200, `after` and `paging.next.after`; values compared without regard to case; the
  pseudo-property `associations.{objectType}`; five requests a second per account.
- [Notes](https://developers.hubspot.com/docs/api-reference/crm-notes-v3/guide):
  `POST /crm/v3/objects/notes`, `hs_timestamp` required, `hs_note_body`, `associations`.
- [Associations v4](https://developers.hubspot.com/docs/guides/api/crm/associations/associations-v4):
  type `202`, a note to a contact.

The guides now show the same endpoints under dated paths (`/crm/objects/2026-09/...`). The
connector uses the `v3` paths the reference for each endpoint still documents; moving to the
dated paths changes one constant per path and no shape.

## What it declares

`crm.contacts` is declared `scoped` (ADR-0130): every operation names one address, and a call
that serves a case answers only the case's subject; another address is refused as
`out_of_scope` before the system is asked. Conformance check C-11 proves it against the fake.

| Operation | Effect | Input | Output |
|---|---|---|---|
| `crm.contacts.find` | `read` | `email` | `email`, `contacts`, `count` |
| `crm.contacts.create` | `write`, `marked` by the address | `email` | one contact |
| `crm.contacts.note` | `write`, `marked` by the key | `email`, `text` (1 to 20000 characters) | `contact`, `note` |

`find` answers every contact that carries the address as its `email` or among its
`hs_additional_emails`, oldest first. Two or more are duplicates; **merging them is not
declared**, because the system cannot undo a merge, and B-5.05 proposes it to a person.

Each contact is reduced to `id`, `email` (lower-cased), `created_at`, `updated_at` and
`lifecycle_stage`. Its name, phone number, company, owner and every other property are never
asked. A contact is created with the address alone.

A create that finds a contact carrying the address creates none and answers the oldest one as
`replayed`. That mark is weaker than a key, and stated so: a contact somebody else created for
the address reports replayed too. A note goes on the oldest contact carrying the address; its
last line is `Taktus reference: <idempotency key>`, and a repeat that finds the line among the
contact's notes writes nothing. An address without a contact is `not_found` for a note.

400 is `invalid`, 401 `unauthenticated`, 403 `forbidden`, 404 `not_found`, 409 `conflict`,
429 and 5xx `unavailable` and retryable. Only an error's `category` is reported, never its
`message`.

## Credentials

| Name | Purpose | How it reaches the connector |
|---|---|---|
| `CRM_TOKEN` | actions: the **requesting identity's** private app token with the scopes the reference names for reading and writing contacts and notes, and nothing else | the file `TAKTUS_CREDENTIAL_CRM_TOKEN_FILE` names, read at the moment of each call, never stored |

A call that references no credential is refused (C-03). The token goes to the configured API
and nowhere else.

## Conformance

```
uv run taktusctl conformance run --contract connector/v1 \
    --endpoint http://127.0.0.1:9156/mcp --scenario connectors/taktus_connectors/hubspot/scenario.json
```

[`scenario.json`](scenario.json) finds the fake's first contact, notes a touchpoint on it twice
with one key (C-05), refuses a text that is no address, and answers a case only its own address
(C-11). `tests/conformance/test_connector_v1_business.py` runs every fault.
