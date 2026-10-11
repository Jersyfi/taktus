# DEC-0177 — Taktus rents execution capacity within a budget

**Category:** NON-BLOCKING
**Raised in:** the pull request that records the owner's answers of 2026-10-11, evening; from the owner's idea of the same evening
**Issue:** [#253](https://github.com/Jersyfi/taktus/issues/253)
**Needed by:** 2026-11-15
**Provisional answer:** none is needed: no work waits on it. Until it is answered, nothing of it is built, and the idea stays where the vision places it.

## 1. What this is about

The owner's idea: Taktus should be able to use computing resources at providers — a European
hosting provider, or the large clouds — and add or remove them on its own when work needs them,
inside a budget and a frame the user sets. It should decide from evidence, not guess: rent by the
hour what runs rarely, keep a fixed base where work runs steadily, and shrink when less is needed.
Costs and resources are to be visible in reports and graphs. Whether Taktus may do this at all,
and with which provider, is the user's. For Taktus's own development the owner would allow it at
that provider with a fixed budget, and wants to be informed and see the costs and the hardware in
a graph.

Some of it exists. Taktus measures the capacity of the machine it runs on and warns before it
runs out. It refuses to start a step whose cost does not fit the budget. It records every step,
with what it consumed, in a chain that cannot be changed afterwards. The vision names "Taktus
managing its own infrastructure" as a capability for after version 1.0, and the operations
blueprint of version 0.7 has "capacity and cost: utilisation, forecast, recommendation".

One rule shapes it. **No Taktus installation may administer the machines it runs on itself.** A
faulty change there could cut off the very path by which Taktus would be repaired. Renting
**additional machines for the work**, on which only the units that execute steps run, is not
that: if they fail, the work waits, and Taktus and its repair path stay untouched.

## 2. Why you are being asked

Entry M3.15 of `docs/decisions/anchors.taktus.md`: what a requirement requires is the owner's,
and no requirement says this today. Entry M3.3: which version it belongs to is the owner's. The
budget itself is a limit (M3.10).

**Sources checked:** both anchor pages, `anchors.md` and `anchors.taktus.md` (M3.3, M3.10 and M3.15 make it the owner's; no entry of mode 1 or 2 covers a new requirement); the register (DEC-0133, DEC-0058); `docs/vision/beyond-1.0.md` (the capability, after 1.0, with admission and a
ledger entry — direction, but no requirement and no version); principles 3 (hardware-agnostic),
8 (cost control), 11 (European sovereignty), 13 (no lock-in); ADR-0025 (no installation
administers its own ground) and DEC-0133 (planning refuses a credential that administers the
installation's own platform); ADR-0031 (capacity watched), ADR-0005 (budgets and admission),
ADR-0010 (cost and the Takt); UC-10.1 (runs anywhere, the infrastructure run by its operator);
the operations blueprint AF-02 (O-07, capacity and cost, version 0.7). None says that Taktus
rents capacity for its work, or when.

## 3. What you must decide

Does Taktus get a requirement to rent execution capacity within a budget, and in which version?

## 4. What you need to know to decide

- **Execution capacity**: the machines on which the units run that execute a step — a coding
  agent, a training run. Not the machines the control plane and its database run on.
- **Base and burst**: a base is rented continuously and costs the same whether used or not; burst
  capacity is rented by the hour when work waits and returned afterwards. Which is cheaper is
  decided from the measured waiting time and utilisation of the last weeks — a statistic over
  recorded numbers, reproducible, not a language model's estimate.
- **Proven, not guessed**: every machine rented or returned is a step with a reason, a budget
  check before it starts, and an entry in the ledger; its cost comes from the provider's bill
  and is compared with the estimate.
- **Today's limit**: the owner's node runs one unit at a time; a second waits (#244 shares the
  processor better, but does not add machines).
- **What it commits to**: a new kind of adapter (a provider of machines), credentials that can
  spend money, and a new anchor question: who may raise the base.

## 5. Options

### Option A — a requirement of its own, in version 0.5.0 (recommended)

- **Meaning:** a new use case: *Taktus rents execution capacity within a budget*. Taktus may add
  and return machines for execution units at a provider the user configured, only where the user
  allows it, only within a budget and a frame (which sizes, how many at most); never the ground
  it runs on. It decides base or burst from measured waiting time and utilisation, by a
  reproducible method, and proposes raising the base as a decision request rather than doing it
  (a limit, M3.10); renting burst within the budget it does on its own. Every change is a ledger
  entry with its reason and its cost from the provider's bill. Reports and graphs show machines,
  utilisation, waiting time and cost over time. For Taktus's own development: the owner's
  provider, a fixed budget the owner sets, a report to the owner on every change.
- **Consequence:** built with the value ledger of 0.5.0, where cost graphs are built anyway; the
  provider is reached through an adapter by capability, never by name.
- **Effort:** the use case in a day; the building, one to two weeks of sessions in 0.5.0.
- **Reversibility:** cheap until built; afterwards switching it off is configuration.
- **Why recommended:** it serves principles 3, 8 and 13, it respects ADR-0025 by renting only
  for execution, and in 0.5.0 the cost evidence it must decide from exists.

### Option B — the same requirement, in version 0.4.0

- **Meaning:** as A, earlier, beside the ML bench, which is the first worker that needs larger
  machines.
- **Consequence:** the cost graphs are built before the value ledger; 0.4.0 grows.
- **Effort:** as A, plus the graphs without the value ledger.
- **Reversibility:** as A.

### Option C — leave it where the vision places it, after 1.0

- **Meaning:** nothing now; the operations blueprint (0.7) brings recommendations, not acts.
- **Consequence:** the single node stays the limit for Taktus's own work until then.

## 6. What is blocked

Nothing.

## 7. How to answer

"DEC-0177: Option A.", "Option B.", "Option C." or your own wording — in the issue.
