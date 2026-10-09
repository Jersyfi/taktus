# NTC-0098 — A lack of an adapter is a block, booked to `wait.dependency`

**Mode entry:** M2.6
**Kind:** unlisted
**Decided:** 2026-10-09
**Raised in:** issue [#86](https://github.com/Jersyfi/taktus/issues/86), in the pull request that closes it
**How it follows:** UC-6.12 §2 requires a finding raised from "a block whose recorded cause is a lack of the product", with "the time waited, taken from the blocked-time accounts". NTC-0090 had decided that a failure is no block, because the work does not wait for anything that lets it continue unchanged. A failure for want of an adapter is the exception: the step is retried unchanged once the adapter exists (NTC-0002), so it matches the definition NTC-0090 applied — time in which the work waits for something that lets it continue as it is. Of the seven accounts of ADR-0015, `wait.dependency` is the one whose example is something else that must exist first; `wait.human` would put the time a lack lasts among the waits on people, which principle 14 keeps apart. Between leaving the lack out of the accounts, which makes the use case unmeetable, and booking it, the stricter in substance is to book it; booking it on the step run that already carries blocks adds no new record kind, which is the option with less ceremony.

## 1. What was decided

- A step that failed for want of an adapter — `no_worker`, `no_connector`,
  `operation_unsupported` — carries a block from the failure until it can start.
- It is booked to `wait.dependency`, with what was lacking as an identifier.
- Every other failure stays no block, as NTC-0090 decided.

## 2. The evidence

- UC-6.12 §2 and issue #86.
- NTC-0002: such a step fails retryable, and a resume after the configuration changed retries it.
- ADR-0015 §1 and `docs/architecture/throughput.md` §1: `wait.dependency` is "another step that
  must finish first"; an adapter that must exist first is the same kind of wait.

## 3. What was considered

- **Book it to `wait.human`.** Rejected for the reason above.
- **A separate record of lacks beside the accounts.** Rejected: a second store of the same facts
  beside the ledger, which is the single source of every metric (ADR-0006).

## 4. Which entry permits it

No entry of modes 3 and 4 names how a failure is booked to an account; it changes nothing a use
case requires (M3.15) and moves no limit or level. No entry of mode 2 names it. M2.6 applies.

## 5. The entry it proposes

**M1.16**, as NTC-0090 proposed it, extended: *a cause the engine meets is booked to the account of
ADR-0015 whose example it matches, with a cause token of its own; a failure the step is retried
unchanged from once something exists — an adapter — is a block on `wait.dependency`; any other
failure is not a block.*
