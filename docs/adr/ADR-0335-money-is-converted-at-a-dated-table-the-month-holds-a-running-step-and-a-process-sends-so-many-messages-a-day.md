# ADR-0335 — Money is converted at a dated table, the month holds a running step, and a process sends so many messages a day

**Status:** accepted · extends ADR-0005, ADR-0010, ADR-0260, ADR-0142 · UC-8.5, UC-7.6 · DEC-0239

## Context

Three gaps in how a budget holds were found against a business's conditions for going live.

1. **Currencies are matched by key, never converted.** A run's budget, a unit's quota and a
   tenant's monthly budget name amounts by currency. Money a step reports in another currency
   counts against none of them. A coding worker that reports US dollars is not counted against a
   budget in euros. Worse, the coding worker refuses an assignment whose limits carry no amount in
   its own currency.
2. **The tenant's monthly budget acts only at a boundary.** ADR-0260 holds every run of the
   tenant at its next step boundary once the month's runs cost the budget. A step already
   running goes on to its end, however long and dear.
3. **Money, tokens and compute are limited; messages are not.** A process may send any number of
   messages a day. Each one is held by the frame of ADR-0142, one at a time; nothing counts them.

## Decision

### 1. A dated exchange-rate table

The operator may configure an **exchange-rate table**: a JSON file `TAKTUS_EXCHANGE_RATES` names.
It has a `version`, the moment `valid_from`, a `source` — such as a central bank's reference
rates of one day — and `rates`: for each currency, in lowercase ISO 4217 code, how many units of
each other currency one unit is worth. Every rate is positive. A file that does not hold this is
refused when the instance starts. Without a table nothing changes.

### 2. Money a budget does not limit is counted in one it does

Where a quantity of money is compared with a budget, money in a currency the budget does not
limit is converted at the table into the first currency of the budget, in code order, that the
table has a rate for, and added there. The money in its own currency stays in the record; the
conversion is recomputed from the record and the table each time, never stored. Money no rate
reaches counts against nothing, as before.

This holds for the run's own budget — what the run used and reserved, and each step's demand at
admission — and for the tenant's monthly budget (ADR-0260). The conversion is a `rule`: the same
record and table give the same amounts. No model produces a rate.

### 3. A worker's ceiling is stated in every currency the table reaches

A worker step is handed a ceiling: what is left of the run's money (ADR-0005, seventh
amendment). The ceiling is now also stated in each currency the table converts into one of the
budget's, at the same rate. A worker that measures its money in that currency halts at the same
line during its step, and keeps its work.

### 4. What is left of the tenant's month is a running step's ceiling too

Before a worker step is handed over, the engine computes what is left of the tenant's monthly
budget, with the step's own reservation released, converted as in §2. Each currency of the month
is a ceiling of the step, the lower of it and the run's own. A worker that reports money per inner
step halts at it during the step, keeps its checkpoint, and the run halts with cause `limit`.
A person raises the budget, or the month turns, and the run is resumed from the checkpoint.

### 5. A process sends at most so many messages a day without a person

A tenant's message rules may name a **daily limit**: the most deliveries a process makes within
24 hours. A process may have its own, in place of the tenant's. `taktusctl messages set
--daily-limit N [--process P]` sets it; 0 removes it. A delivery beyond the limit is an anchor,
`anc-daily-messages`, at every level: it waits for a person's decision, as a message to more
recipients than the tenant's limit does (ADR-0142). The count is the process's
`egress.delivery` entries in the ledger within the last 24 hours; a rehearsal delivers none. A
count of messages names no person (principle 14).

## Alternatives

- **Convert at the provider's own rate, reported with its usage.** Rejected. Rates would differ
  per provider and per call, and could not be recomputed from one table.
- **Fetch the rates from a public source at run time.** Rejected. A run's figures would depend
  on when it ran and on an outside service being reachable. The operator loads the table, as the
  price table.
- **Stop a running step from outside when the month is reached.** Rejected for this step. A
  worker that halts at its own ceiling keeps its work; a stop from outside reaches it only at its
  next inner step anyway (ADR-0005), and the ceiling says the same earlier.
- **A daily limit that pauses the process until the next day.** Rejected. A pause hides that the
  process wants to send more than was agreed; a person who sees the request decides whether the
  day is unusual.

## Consequences

- `components/run/domain/service/exchange.py`: `ExchangeRates`, `converted`, `ceiling_in`.
- `composition/settings.py`: `TAKTUS_EXCHANGE_RATES`; `EngineOptions.exchange_rates`.
- `components/run/application/service/execute_run.py`: the conversion in `_spent`, `_priced` and
  the tenant's month; the ceiling of §3 and §4; the daily limit in the message gate.
- `components/governance`: `MessageRules.daily_limit`, `processes`; written as before where none
  is set (ADR-0093). No migration: both are documents.
- Tests: `tests/components/run/test_tenant_budget.py`, `tests/components/run/test_money_ceiling.py`,
  `tests/components/run/test_outward_messages.py`, `tests/components/governance/test_messages.py`.

## Where this promise ends

- **One table at a time.** The instance holds the table its operator loaded. A run is not pinned
  to a version of it; a check uses the table in force when it runs. A rate is as good as its
  source and its date.
- **A unit's quota is not converted.** An organisational unit's monthly quota (ADR-0166) is
  committed by currency key when a run starts; a run whose budget names no amount in the quota's
  currency still waits, as before.
- **The price table's currency.** Compute money under a budget in another currency than the
  price table's is still not held (ADR-0005, fourth amendment); this ADR converts money that was
  measured, not prices.
- **Only a worker that reports money per inner step halts during its step.** A worker that
  reports its money only at its end, a single model call and a connector call cannot be stopped
  in the middle: they are held at their boundary. Their overrun is the one step's, recorded
  (ADR-0005, third amendment).
- **The month's ceiling is computed when the step is handed over.** Money other runs of the
  tenant spend while the step runs is not taken from its ceiling; the next boundary of every run
  sees it (ADR-0260).
- **The daily limit counts deliveries.** A write that is not a delivery — a record in a customer
  system, a comment — is not a message and is not counted. Deliveries the business makes outside
  Taktus are not seen.
