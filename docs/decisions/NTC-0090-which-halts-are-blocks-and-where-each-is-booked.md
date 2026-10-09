# NTC-0090 — Which halts are blocks, booked where

**Mode entry:** M2.6
**Kind:** unlisted
**Decided:** 2026-10-09
**Raised in:** [#157](https://github.com/Jersyfi/taktus/pull/157), for issue #80
**How it follows:** ADR-0015 §1 names seven accounts and `docs/architecture/throughput.md` §1 gives each its example: a provider's rate limit, an exhausted subscription window, a configured budget that would be exceeded, no free GPU or worker slot, an open decision or approval, CI or a partner system, another step that must finish first. Each example is something the work waits for and then continues unchanged; each booking below follows the example it matches. A halt that matches none — no estimate, an adapter below verified, a failure, a stop — is something the work does not wait for: it needs a change, is an incident (ADR-0021), or is a person's choice. Between counting those as blocks too and leaving them to their own records, the stricter in substance is to keep the seven accounts exact, so that a sum per account says what ADR-0015 means by it; leaving them out adds no record, which is the option with less ceremony.

## 1. What was decided

Where the engine meets a halt or a wait, it books it like this (ADR-0043 §1 and §4):

- **A refusal or a halt at the run's own limits** books to `limit.quota` when quota alone did not
  fit, and to `limit.budget` otherwise. Quota is what a connector or a worker counts against a
  provider's window or a subscription; currency, tokens and compute seconds are the budget a
  person set for the run.
- **A platform that cannot hold the job** books to `limit.compute`, like a worker at capacity.
- **A `wait` step** books to `wait.external`, whether it waits for an external state or for time
  to pass. The cause token — `waiting_on_state` or `waiting_on_clock` — tells the two apart.
- **A step held back** behind a step that waits for a person books to `wait.dependency`, from the
  moment its dependency began to wait until it can start. A step that is already blocked is not
  held back as well.
- **Not a block:** a refusal for want of an estimate, a refusal of an adapter below *verified*, a
  failure, and a stop. Each stays in the ledger as what it is.
- **The share of the work blocked** is the share of a process's runs active in the period that a
  block of the account held up.

## 2. The evidence

- ADR-0015 §1 and `docs/architecture/throughput.md` §1, the table of accounts and examples.
- ADR-0005, first amendment's table: quota (`quota_units`) is counted per step by workers and per
  call by connectors; the connectors' declarations give quota a window (`window_seconds`).
- `docs/architecture/throughput.md` §5: "Only the dependent branch blocks, never the whole run";
  ADR-0039 holds back only the steps that depend on a waiting step.
- Issue #80 asks for the share "from those records alone"; the runs active in a period are the
  runs with a ledger entry in it, which the same ledger holds.

## 3. What was considered

- **Every halt a block, the four that match no example booked to the nearest account.** Rejected:
  a refusal for want of an estimate under `limit.budget` would tell the analysis that a higher
  budget would have bought something, which it would not.
- **Quota always under `limit.budget`, because the run's budget sets it.** Rejected: the analysis
  asks what a higher limit would buy, and a provider's window is raised elsewhere than a budget.
- **A deliberate pause not booked.** Rejected: the engine cannot tell a pause the process means
  from one it would rather not take; the cause token keeps them apart for the analysis.
- **The share as blocked time over lead time.** Left to the analysis (`0.5.0`): it needs every
  run's lead time, and overlapping blocks would be counted twice in a total.

## 4. Which entry permits it

None of modes 3 and 4 names how a cause the engine meets is booked to ADR-0015's accounts; it is
not what a use case requires (M3.15), and no limit or level moves (M3.9, M3.10). No entry of mode
2 names it either. M2.6 applies: decided in the direction of ADR-0015 and its examples.

## 5. The entry it proposes

**M1.16** — *Booking a cause to an account*: a new cause the engine meets is booked to the account
of ADR-0015 whose example it matches, with a cause token of its own; a halt that matches none is
not a block. Mode 1, because it follows the table of `docs/architecture/throughput.md` §1 without
judgement and changes nothing a use case requires.
