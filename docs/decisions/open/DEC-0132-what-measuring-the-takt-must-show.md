# DEC-0132 — What measuring the Takt must show

**Category:** NON-BLOCKING
**Raised in:** the pull request that raises the requests issue #81 needs, while checking #81 again as P-02 would
**Issue:** [#177](https://github.com/Jersyfi/taktus/issues/177)
**Needed by:** before #81 is built; the roadmap places it in `0.2.0`
**Provisional answer:** Option A, which binds any session that builds #81 before the answer. It takes effect only with a weighting table from DEC-0131; under its Option C this request lapses.

## 1. What this is about

The roadmap says the **Takt** — the unit Taktus is meant to be paid in one day — is measured from
`0.2.0`, not yet charged. A weighting table turns what each step used into Takte; which table is
your own question (DEC-0131). This request is about something else: what "measured" must show, so
that a session can build it and a test can prove it.

No requirement says so today. UC-8.5, cost control, excludes charging and says nothing about the
Takt. UC-9.1 and UC-9.3 show cost in Takte, but only from `0.5.0`. The design gives the shape: the
table is public, versioned and recomputable from the ledger (ADR-0010).

## 2. Why you are being asked

Entry M3.15 of `docs/decisions/anchors.taktus.md`: what a use case requires is yours.

**Sources checked:** the vision (principle 8, repeatability and cost control; principle 13, no
lock-in — a bill a customer cannot recompute is lock-in by opacity), ADR-0010 and its amendment,
ADR-0005 (budgets), UC-8.5, UC-9.1 and UC-9.3, `docs/architecture/accounting.md`, both anchor
pages and the register (DEC-0030 to DEC-0087 accepted the conditions added to the use cases; none
concerns the Takt). The ADR gives the shape of a condition but not the requirement itself.

## 3. What you must decide

Does UC-8.5 gain the condition below, so that "the Takt is measured" has a test?

## 4. What you need to know to decide

**The proposed condition**, added to UC-8.5 §2:

> - The Takt consumption of every completed run is computed from its consumption breakdown at the
>   weighting table in force when the run started, named by the digest of its document. The table
>   is in the repository, versioned, and never changed once used. `taktusctl cost <run>` prints
>   the Takte beside the money, and recomputes them from the ledger at another table on request.
>   A quantity the table does not weigh is named, never counted as zero. A table marked
>   uncalibrated says so beside every figure.
> - The Takt rate of a tenant — Takte per hour over the table's window — is shown beside its
>   consumption.

and to §3: **Not a price.** A Takt figure charges no one until a price exists (M4.2).

- It is the money's condition (already built) applied to a second table, so most of the work
  exists: the breakdown and the price-table mechanism.
- It requires nothing of the numbers; DEC-0131 decides those.

## 5. Options

### Option A — UC-8.5 gains the condition (recommended)

- **Meaning:** as quoted above.
- **Consequence:** #81 can be made ready once DEC-0131 gives a table, and built against this
  condition.
- **Effort:** a weighting-table document beside the price tables, the meter applying it, the
  command printing it, the rate per tenant; roughly as large as the price table was.
- **Reversibility:** cheap until a figure is shown to a customer.
- **Why recommended:** it is ADR-0010's condition, made testable, at the place cost is already
  required; nothing in it is new in substance.

### Option B — a use case of its own

- **Meaning:** the same condition as a new use case under E8, cost and consumption.
- **Consequence:** the same work; one more file to keep current, and the Takt read apart from the
  money it sits beside.

## 6. What is blocked

Nothing waits on this answer alone: #81 waits on DEC-0131 too. If no answer arrives before #81 is
built, Option A binds it.

## 7. How to answer

"DEC-0132: Option A." or "DEC-0132: Option B." in the issue. A free-text answer is read back as an
interpretation and confirmed before it is acted on.
