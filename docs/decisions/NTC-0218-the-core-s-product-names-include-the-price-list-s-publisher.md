# NTC-0218 — The core's product names include the price list's publisher

**Mode entry:** M2.2
**Kind:** test-strategy
**Decided:** 2026-10-20
**Raised in:** [#540](https://github.com/Jersyfi/taktus/pull/540), Taktus's pull request for #327

## 1. What was decided

`tests/architecture/test_core_is_technology_free.py` refuses the name of the project that
publishes the open model price list #327 imports, as it refuses every other product's. The core
module that maps such a list names the list's shape, not its publisher.

## 2. The evidence

P-03's change for #327 named the publisher in the docstring of
`components/accounting/domain/service/price_import.py`. The architecture test passed, because the
name was not on its list. CLAUDE.md §6 forbids a product name in the core, and §11 point 11 makes a
hole in a gate met on the way a finding.

## 3. What was considered

- **Leave the name, since it is only a docstring.** Rejected: ADR-0003 makes even a comment a
  finding, and the list is what holds that.
- **Move the mapping into an adapter.** Not needed: the mapping reads an open shape that several
  lists share, and imports only the ports and the shared kernel.

## 4. Which entry permits it

M2.2: how a check is tested is the session's, and this one is made stricter, not weaker.
