# NTC-0251 — UC-04: from an incoming invoice to its payment, released by a person

**Mode entry:** M2.7
**Kind:** restoration
**Decided:** 2026-10-31
**Raised in:** branch `concept/package-c--invoice` (package C, concept mode, DEC-0222)
**How it follows:** the roadmap's `0.7.0` names the `invoice-to-payment` blueprint — an incoming invoice read, matched, its amount `exact`, a payment released by a person — and the owner accepted it with the Warp outlook (DEC-0195, W1). Issue #402 states its verification and says that where the domain needs more than UC-03's rows B-6.06 and B-10.03, a blueprint-level use case UC-04 is written first, under M2.7. UC-04 states the domain at that level: the processes, the autonomy per action, what stays with a person, what must hold and when the case holds. Every condition is one of #402, the roadmap's, UC-03's two rows, UC-15.2's or DEC-0029's.

## 1. What was decided

UC-04, *From an incoming invoice to its payment, released by a person*, blueprint
`invoice-to-payment`, `docs/usecases/AF-04-invoice-to-payment.md`, version `0.7.0`. Its
conditions:

- every amount `exact`, produced by a rule with machine checks (#402; CLAUDE.md §4);
- the payment release a legal anchor, never automatic (#402; UC-15.2 §2);
- the booking a proposal into the tenant's own system through a connector (#402; non-goals);
- every booking traced to its document and order (UC-15.2 §3, ADR-0021);
- every system named by capability (UC-15.2 §3, UC-8.9);
- not used before the catalogue's review (DEC-0029, Option A).

Two processes beyond B-10.03 are listed as the domain's, not built: the daily collection of the
inbox, which is B-6.06's incoming half, and the classification of an invoice that names no
order, which is #402's "maturation from a language model to ML to a rule". Listing them states
what the domain needs; it requires neither for `0.7.0`.

## 2. The evidence

- Issue #402, *How it is verified* and *Where the boundary lies*; DEC-0195 W1; DEC-0029.
- `docs/roadmap.md`, `0.7.0` and its completion condition.
- UC-03 B-6.06, B-10.03 and §6; UC-15.2 (`blueprints/finance/README.md`) §2 and §3.

## 3. What was considered

- **Only UC-03's two rows.** Rejected: they name neither the documents nor the systems nor the
  checks, and #402 asks for UC-04 where the domain needs more.
- **Requiring the classification for `0.7.0`.** Left out: the roadmap's condition is an invoice
  read, matched, `exact` and released by a person. A new requirement is the owner's (M3.15).

## 4. Which entry permits it

M2.7, *bringing a use case up to what the owner has already accepted*: here the roadmap's
`0.7.0` and issue #402. The owner may veto it within seven days of the pull request.
