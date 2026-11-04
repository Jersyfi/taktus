# ADR-0199 — Two lists are matched by a rule, and the product's entitlements are read through a manifest the blueprint ships

**Status:** accepted · extends ADR-0192 (the rule `filter`), ADR-0117 (the vendor connector's
manifest) and ADR-0130 (a scoped capability) · issues #437, #401, UC-03 B-6.01, B-3.04, B-5.06

## Context

UC-03 asks three processes of a software business to compare what the payment provider holds
with what the product grants. B-6.01 matches every active payment against the product's
entitlements, every day, and makes every mismatch an incident. B-3.04 finds, for one customer
who wrote in, why a payment did not unlock the product, and repairs a clear case. B-5.06 checks
the seats a business customer pays for against the seats it holds. Each match is `exact`
(UC-03 §4.3, §4.5, §4.6).

ADR-0192 bounded its rule `filter` here: it reads one list at a time, and "B-6.01 is not built
until a rule or a statistic for it is". A model could pair the entries, but a pairing of money
against access must be reproducible (CLAUDE.md §3, §4).

The payment side has a connector: `payments.subscriptions` and the scoped `payments.customers`
(ADR-0150). The entitlement side does not. What a customer may use is held in the product
itself, in a shape the product's team chose. No open standard describes it. A connector written
here for one product's interface would be an invented interface, and would serve no other
tenant.

## Decision

### 1. The rule `match`

The rule kind `match` pairs the entries of two lists by a key:

| Field | Meaning |
|---|---|
| `left`, `right` | each a side: `items`, the list, usually a reference to a reading; `key`, the dotted paths whose texts make an entry's key; `each`, a field holding a list, so that the item stands for one entry per element |
| `compare` | pairs of paths, `left` and `right`, whose values must be equal in a matched pair: numbers in decimal arithmetic |

Both keys name the same number of fields; registration refuses another shape. The result names
every entry that is not a clean match:

| Result | Meaning |
|---|---|
| `matched` | how many pairs matched, every compared field equal |
| `left_only`, `right_only` | the entries without a partner on the other side |
| `differing` | the pairs whose compared fields differ, each with the fields and both values |
| `unkeyed` | the entries that lack a key field |
| `duplicates` | each key that occurs twice on one side, with the side and the count |
| `mismatches` | the number of all of these; `first` the first of them, absent when there is none |

An entry without a key, or with a key seen twice, cannot be paired with certainty, so it is a
mismatch and never a match. Every list that is not a list of objects fails the step. The same
lists give the same result: the rule is admissible for `exact`, and a step that uses it
declares the check by recomputation (DEC-0173).

### 2. The entitlements are the tenant's connector, under a manifest the blueprint ships

The vendor connector puts any MCP server behind the contract under a manifest that names each
tool's operation and effect (ADR-0117). A product's team can expose its entitlements as such a
server; many products already ship one. The blueprint therefore names the capability and ships
the manifest, and the tenant runs the vendor connector with it in front of its own product:
`blueprints/software-operations/connectors/entitlements.manifest.json`.

| Operation | Capability | Effect | What the product's tool answers |
|---|---|---|---|
| `entitlements.grants.list` | `entitlements.grants` | read | every entitlement in force, `{entitlements, complete}` |
| `entitlements.customers.list` | `entitlements.customers`, scoped | read | one `customer`'s entitlements, in the same shape |
| `entitlements.customers.grant` | `entitlements.customers`, scoped | write, `native` by `request_id` | the entitlement granted, with `replayed` |

An entitlement is `{id, customer, product, quantity}`. The customer is named by the payment
provider's identifier, which a product keeps from its checkout. Nothing else of the customer is
read. A tenant whose tools carry other names changes `tool` in its copy of the manifest. A tenant
whose product answers in another shape serves it through a server of its own in this shape.

This is a shape the blueprint states, not a protocol. It is the narrowest the three processes
need, and it is stated in one file that a tenant reads.

The test that every operation a bundle calls is declared by a connector of this repository
(ADR-0192 §2) counts the operations of a manifest the blueprint ships beside those of a
connector's declaration.

### 3. A manifest can declare a capability scoped

A step that serves a case reads only its subject's data (ADR-0130). The manifest had no way to
say which argument of a tool names that subject. An operation of a manifest may now name it,
`subject` (`Connector.json#/$defs/ManifestOperation`). A capability whose every operation names
one is declared `scoped`. A capability where only some do is refused, since the others would be
a way round the scope. A call that serves a case and names another subject in that argument is
refused as `out_of_scope`, and the vendor's server is not asked. The suite's check C-11 runs
against the vendor connector wherever a capability is scoped, and its fault `C-11` breaks it.

The payment connector splits its capabilities the same way: the unscoped read every
reconciliation needs, and the scoped reads of one customer's case (ADR-0150). A step without a
scope that called a scoped capability would read personal data outside a case, and the frame's
anchor would hold it (ADR-0130 §6).

### 4. The processes

B-6.01, B-3.04 and B-5.06 are bundles of the blueprint `software-operations`
(`blueprints/software-operations/processes/`).

- **B-6.01** reads every active subscription and every entitlement, each held to `complete`,
  and matches them by customer and product, one entry per item of a subscription. It starts at
  level 1. The tenant's corridor on `mismatches` makes one mismatch an incident.
- **B-3.04** serves one customer's case: both reads and the repair carry the customer as the
  scope. The subscriptions still paid are kept by `filter`, and the match compares the seats
  too. Exactly one mismatch, a paid product without its entitlement, is a clear case: it is
  granted with the seats paid for, after a person confirmed it at level 2. Every other case is
  left to a person with the cause the match named.
- **B-5.06** is B-3.04's reading and match without the repair, at level 1, judged by a corridor.

## Alternatives

- **A connector for one product's interface.** It would invent an interface no tenant shares,
  and would be dead code for every other tenant.
- **A model pairs the lists.** The pairing would differ between two runs and could invent a
  pair; a match of money against access is exact.
- **Two filters and a template.** A filter cannot see the other list; a pair needs both.
- **A scope read from the input by name in the core.** The core does not know which argument of
  a vendor's tool names a customer. The manifest is where the tool is described.
- **The reconciliation reads each customer in turn, scoped.** One run would ask the product once
  per customer, and the frame's scope is one subject per step.

## Consequences

- The run's rules gain `match` (`MatchRule`, `MatchSide`, `Compared`, `rules.match`).
- The connector contract's manifest gains `subject`; the vendor connector declares a scoped
  capability and refuses another subject; its faults include C-11 where a capability is scoped.
- `blueprints/software-operations/` gains B-6.01, B-3.04, B-5.06 and its manifest.
- `tests/fakes/entitlement_server.py` stands in for a product's MCP server over its
  entitlements; the conformance suite passes against it behind the vendor connector.

## Where this promise ends

- **The match pairs by equal keys.** A customer known under two identifiers, or a product
  renamed between the two systems, is a mismatch on both sides. The tenant maps them in its
  product's tool, not here.
- **One entry stands for one key.** Two subscriptions of one customer for one product are a
  duplicate and a mismatch, even where the product grants both together.
- **The entitlement shape is the blueprint's, not a standard.** A product that answers in
  another shape needs a server of its own in front of it. No connector here reads a product's
  own interface.
- **The vendor connector refuses another subject by the argument alone.** It does not check
  the product's answer. A product's tool that answers more customers than the one asked would
  hand them over; the tenant's review of its own tool is where that is checked.
- **B-3.04 repairs one case only.** Unlocked and unpaid, the wrong number of seats, or two
  mismatches at once, are left to a person. Withdrawing access is never done here.
- **B-3.04 does not find the customer.** A support message carries no payment identifier; the
  tenant's intake or a person gives it.
- **B-5.06 checks the seats only.** Setting up access is B-3.04's repair. Preparing a renewal
  needs a contract's end date, which no capability serves; the contract and the price stay with
  a person (UC-03 §6).
- **Nothing here moves money.** A refund is anchored by `anc-money` at every level (ADR-0192
  §3).
- **Proven against fakes.** The payment provider's fake and the stand-in for a product are run
  in `tests/composition/test_software_operations.py`; whether the business runs these
  processes is the business's (DEC-0201, DEC-0225).
