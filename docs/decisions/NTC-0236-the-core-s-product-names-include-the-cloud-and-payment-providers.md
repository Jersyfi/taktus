# NTC-0236 — The core's product names include the cloud and payment providers

**Mode entry:** M2.2
**Kind:** test-strategy
**Decided:** 2026-10-28
**Raised in:** the branch `concept/package-a` (package A, DEC-0222), for issue #447

## 1. What was decided

`tests/architecture/test_core_is_technology_free.py` refuses the names `aws`, `amazon` and
`stripe` in the core and in the contracts, as it refuses every other product's. The core names
the capabilities these products serve, `billing.costs` and `payments.subscriptions`, never the
products.

## 2. The evidence

Package A adds connectors for a cloud provider's billing, a model provider's costs, error
tracking and a payment provider (ADR-0150). The names of the model provider and of the error
tracking product were on the list already; the cloud provider's and the payment provider's were
not. A later change could have named them in the core, and the gate would have passed.
CLAUDE.md §6 forbids a product name in the core, and §11 point 11 makes a hole in a gate met on
the way a finding.

## 3. What was considered

- **Leave the list as it was, since the core names neither today.** Rejected: the list is what
  holds the rule for the next change, not for this one. NTC-0218 closed the same hole for the
  price list's publisher.
- **Add every product a connector of this repository names, from the adapters' directory
  names.** Not now: a directory name such as `httpcheck` is no product, and the list stays one
  a person reads.

## 4. Which entry permits it

M2.2: how a check is tested is the session's, and this one is made stricter, not weaker.
