# ADR-0208 — The product's accounts are read through a manifest, and a data protection request is prepared, never carried out

**Status:** accepted · extends ADR-0199 §2 (a manifest the blueprint ships) and ADR-0130 (a
scoped capability) · issue #401, UC-03 B-3.05, B-3.06, B-3.08

## Context

B-3.05 answers a question about cancelling or a charge with the subscription's state and the
self-service way. B-3.08 recognises a data protection request, checks the requester's identity,
prepares the export or erasure and watches the deadline; carrying it out and confirming it stay
with a person (UC-03 §4.3, §6). Both need the product's own accounts, which no open standard
describes, as ADR-0199 found for its entitlements. B-3.06 left two parts unbuilt: a report
added to an existing issue of the same defect, and the customer told when the fix is live.

## Decision

### 1. A second manifest

`blueprints/software-operations/connectors/accounts.manifest.json` is the manifest under which a
tenant serves its product's MCP server over its accounts with the vendor connector, in the shape
of the entitlements manifest. Credential `ACCOUNTS_TOKEN`. Every operation is scoped by the
payment provider's customer identifier.

| Operation | Capability | Effect | What the product's tool answers |
|---|---|---|---|
| `accounts.customers.read` | `accounts.customers` | read | `{id, customer, state, plan, created, manage_url}`: no name, no address |
| `accounts.customers.verify` | `accounts.customers` | read | whether an `address` is the account's verified address; the account's own address is never answered |
| `accounts.requests.prepare` | `accounts.requests` | write, `native` by `request_id` | an access, erasure or rectification request made ready for a person; nothing carried out |

### 2. B-3.05 and B-3.08

- **B-3.05**, level 2: the customer's subscriptions and account are read under the case's scope;
  a model drafts the reply with the self-service page; it is checked, held against money and
  promises, and sent after a person released it, as B-3.02 sends.
- **B-3.08**, level 2: a model reads the request, a rule holds its kind to three names; the
  sender's address is verified by the product, and only a verified request is prepared, after a
  person confirmed it. A `human` step follows: a person carries it out and confirms it to the
  customer. Its deadline is 28 days from the run's start, with a reminder at 21: the shortest
  month never runs past the one month of GDPR Art. 12(3).

### 3. B-3.06 in two flows of one process

A stage names each process by its bundle's identifier, one bundle per row of UC-03 (ADR-0191
§4). B-3.06 version 2 therefore carries both remaining parts:

- **The report added to an existing issue.** A model names the open issue of the same defect; a
  rule holds the number to one the open issues carry. Then the report is added as a comment
  carrying `support-case:<message>`, once, instead of a new issue. Either is confirmed by a
  person.
- **The customer told when the fix is live.** With the input `fixed`, the issue a release fixed,
  the process reads it and its comments, keeps by rule the marks of a closed issue, composes a
  fixed notice and sends it by mail under UC-7.6's frame after a person released it.

## Alternatives

- **A connector for one product's account interface.** It would be invented (ADR-0199 §2).
- **The erasure carried out by Taktus.** It is irreversible and legally binding; UC-03 §6 keeps
  it with a person.
- **A second bundle for the fix notice.** A stage could not name it.

## Consequences

- The manifest, `tests/fakes/account_server.py`, three bundles, and
  `tests/composition/test_software_operations_accounts.py`.

## Where this promise ends

- **The account shape is the blueprint's, not a standard.** A product that answers otherwise
  serves it through a server of its own in this shape.
- **Cancelling is not done for the customer.** The customer does it on the product's page.
- **The two-month extension of Art. 12(3) is not modelled.** A person who extends tells the
  customer and handles the deadline.
- **Nothing says which issues a release fixed.** The trigger names the issue; a second run for
  the same message sends a second notice.
- **The tie to an existing issue is a model's.** The confirming person checks it; a wrong tie
  adds a comment, it loses no report.
