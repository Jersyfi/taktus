# NTC-0088 — The open readings of anchors and requests are the strict ones

**Mode entry:** M2.6
**Kind:** unlisted
**Decided:** 2026-10-09
**Raised in:** [#79](https://github.com/Jersyfi/taktus/issues/79)
**How it follows:** The contracts and ADRs leave four points open, and each has two readings consistent with them. CLAUDE.md §8 settles such a tie as "strict in substance, sparing in ceremony" (DEC-0040). Strict in substance: a selector the contract's own example reads as narrowing narrows; an anchor scoped to what Taktus cannot evaluate yet holds everywhere rather than nowhere; an aggregate that is one person's number is withheld, because ADR-0015 forbids it "by person" and an average over one person is that; every answer is confirmed, because ADR-0008 prices "one extra confirmation message" into each decision. Sparing in ceremony: no new record, step or notification is added for any of them.

## 1. What was decided

Four readings were needed to build ADR-0042:

- **An anchor's selectors combine all-of, each selector any-of.** `payment.release:*` with the risk
  class `financial.high` anchors a payment release of high risk, as `Anchor.json`'s example
  `payment-release.json` reads ("release a payment above 10,000 EUR").
- **An anchor scoped to a domain or a jurisdiction holds everywhere in the tenant** until domains
  exist (UC-15.5): never less than configured.
- **An aggregate of response times over fewer than two deciders is withheld**, count and median
  alike.
- **Every answer is reflected back and confirmed**, a chosen option as much as free text.

## 2. The evidence

- `contracts/shared/v1/examples/anchor/valid/payment-release.json` and `release.json`: each pairs an
  action selector with a second one that narrows it.
- `contracts/shared/v1/Anchor.json`, `scope`: "Absent means everywhere in the tenant." Nothing in
  a step carries a domain or a jurisdiction today.
- ADR-0015, *Protective rule*: "Aggregation by role or department only, never by person, and no
  ranking."
- ADR-0008, *Consequences*: "Each decision costs one extra confirmation message. Worth it."

## 3. What was considered

- **Selectors any-of.** More halts, but the examples would anchor every payment release and
  everything of high risk, which is not what they say.
- **A scoped anchor holding nowhere until scopes are evaluated.** It would silently not apply.
- **Aggregates over any group.** A role held by one person would show that person's times to
  everyone.
- **A chosen option applied at once.** One message fewer, and a misclick takes effect.

## 4. Which entry permits it

No entry of `anchors.taktus.md` names how an open point of a contract or an ADR is read where a
change builds it. M1.9 lets the session change an ADR's substance while the vision holds; these
readings change none and settle what was open. Mode 3 and 4 are not touched: what UC-7.4 requires
is unchanged (M3.15), and no contract breaks (M3.5). M2.6 applies.

## 5. The entry it proposes

**M1.15** — *How an open point of a contract or an ADR is read where a change builds it*: the
reading that holds more, and that the contract's own examples support, recorded in the ADR that
builds it.
