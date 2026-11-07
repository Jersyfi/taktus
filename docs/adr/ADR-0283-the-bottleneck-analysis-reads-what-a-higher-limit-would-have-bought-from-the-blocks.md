# ADR-0283 — The bottleneck analysis reads what a higher limit would have bought from the blocks

**Status:** accepted · builds what ADR-0015 §2 to §4 and ADR-0043 left to the analysis · serves
UC-9.5

## Context

The `run` component keeps the blocked-time accounts (ADR-0043). Every block that ended has a
record with its account, its cause, the run and step it held up, and how long it lasted. Sums
per account, process and period are read from them, and a sum of waits on a person that fewer
than two persons answered is withheld (NTC-0168).

ADR-0015 asks for more, and UC-9.5 states it as verification conditions:

1. What would a higher limit have bought? Admission control runs before every step, so Taktus
   knows what it refused and why. The answer is an analysis of those refusals, not a model.
2. Every recommendation names its expected effect, its cost and its value. A raise is proposed
   only after a change of method (ADR-0004) was checked, and the check is named.
3. Waits on people are summed by role or department, never by person, and never ranked.
4. Four ways to wait less on people are offered: carry on with unblocked work, a deadline with
   a deputy, batching requests that are not urgent, and a rule made from recurring decisions.

A refusal's record did not say by how much the step's reservation exceeded what was left.
That amount is known only at the moment of the refusal: admission compares the reservation with
the remaining budget and then forgets both. Without it, "how much higher" cannot be read back.

The analysis is filed in `accounting`, which owns marginal value (ADR-0029). The records are
`run`'s. Who decided a recurring decision is `decision`'s. Whether another method would do a
step's work is `run`'s maturation (ADR-0084). Components never import each other.

## Decision

### 1. A refusal records its shortfall

`Admission` gains `short`: for each quantity that did not fit, the amount the reservation
exceeded what was left. The keys are `currency.<code>`, `quota_units`, `tokens_in`,
`tokens_out` and `compute_seconds`. A reservation in a resource class the budget does not cover
is short by all of its compute seconds.

The engine opens the block of a step refused by admission with that shortfall
(`OpenBlock.short`). The block's record carries it, and `Block.short` reads it back. A step
refused again while it is still blocked keeps the shortfall of its first refusal. That is the
moment the block began, so it is the raise that would have let the step start then. No other
cause carries a shortfall.

The step run is a document, so the field needs no migration. A record written before this
decision has no shortfall, and the analysis says so for it.

### 2. Marginal value per account and process

The handler `Bottlenecks` of `accounting` reads every ended block of the four `limit.*`
accounts. It reads them through its port `BlockAccounts` (`accounting/ports`), which the
composition answers from `run`'s `BlockedTime`. Per account and process it computes:

- **What would have started.** The steps and runs the blocks held up.
- **When.** Each step would have started when it was refused, at the block's beginning, not
  when it was admitted. The seconds earlier are the blocks' durations added up.
- **How much higher.** The raise is computed per quantity:
  - for an admission refusal, each run's shortfalls are added up, because a run's steps run
    one after another against one budget. The raise is the largest such sum over the runs;
  - for `limit.compute` at capacity (`at_capacity`, `rejected_by_capacity`), the raise is in
    `places`: the most blocks of the account and process that were open at the same moment.
- **Exact or estimate.** Tokens, quota units, compute seconds and places are exact: they are
  the quantities admission compared. Money is marked an estimate. The money a step uses is
  known only when its assignment reports it (ADR-0005, ADR-0010).
- **Unmeasured.** A provider's rate limit, a unit's quota or budget, the tenant's monthly
  budget, a halt at a worker's own ceiling, and a refusal recorded before this decision carry
  no shortfall. Each such cause is named with the reason. Nothing is guessed for it.

The order is by account and process, never by a figure.

### 3. A recommendation checks a change of method first

For every marginal value the handler asks its port `MethodCheck` about each step that was held
up. The composition answers it from `run`'s step measures and the maturation candidacy
(ADR-0084). A step on a language model whose cases meet the candidacy is a step where a change
of method may remove the bottleneck at no extra cost. A move is proposed only on evidence of a
lower cost per case. Every other step's check is named with what it found.

Each recommendation names:

- **its action**: `change_method` where any held-up step is a candidate; otherwise
  `raise_limit` where a raise was measured; otherwise `none`;
- **its expected effect**: how many steps of how many runs would have started, and how many
  seconds earlier in total;
- **its cost**: the raise per quantity, in the limit's own units, each marked exact or
  estimate. A change of method costs no raise of the limit;
- **its value**: the seconds earlier per unit of each quantity raised;
- **its check**: every method check, by step, with what it found.

A raise is recommended only where every check found no change of method.

### 4. Waits on people by role and by department, in `run`

`BlockedTime.grouped` sums the waits of `wait.human` by role or by department, per period. A
wait on an anchor's decision carries the role its requests are addressed to. A wait without a
role is grouped as `unaddressed`. A wait's department is the department of the person who
answered it, through the port `Departments` of `run`. The composition answers that port from
the identity directory, as it does for the decision component (ADR-0042). A department that is
not known is grouped as `unplaced`.

The person is counted, never kept. A group that fewer than two persons answered is withheld,
count and all, as the sums are (NTC-0168). The order is by grouping, group and period, never by
a figure. The join of a wait to a person stays in `run`, where `own` already makes it. The
accounting component never reads a wait on a person one by one. Its port hands it the limits
and the work held back, and the waits on people only as these groups.

### 5. The four ways to wait less on people are offered

The handler offers each way where the records show a reason for it, with its evidence and the
mechanism that carries it out:

- **Carry on with unblocked work**, per process with steps held back behind a wait on a person
  (`held_back`). A waiting step holds back only the steps that depend on it (ADR-0039). A step
  that does not need the awaited result can drop the dependency and carry on.
- **A deadline with a deputy**, per role whose waits are shown. A deadline on the step with
  `at_limit: {escalate: <deputy role>}` hands the wait to a deputy when it falls due
  (ADR-0133).
- **Batching requests that are not urgent**, per role with more than one wait in a period. The
  decider answers them together at a time they choose. Taktus offers this; it does not hold a
  request back on its own.
- **A rule from recurring decisions**, per rule the decision component proposed or a person
  adopted (ADR-0161). The handler reads these through its port `RecurringDecisions`. The rule
  is the deciding role's. It takes effect only on a person's acceptance. Retiring it is the
  decider's, at any time.

No offer names a person. An offer is a recommendation; carrying it out stays with whoever owns
the process, the deadline or the decision.

### 6. A command line

`taktusctl bottlenecks` prints the marginal values, the recommendations, the waits by role or
department (`--by`), and the offers; `--json` prints one document.

## Alternatives

- **Recomputing the shortfall from the ledger.** The run's budget statement and the
  consumption before the refusal are in the ledger. The margin, the calibration scale and the
  conversion at that moment would all have to be recomputed outside the engine. A second
  implementation of admission would drift from the first.
- **The analysis in `run`.** `run` owns the records, not marginal value (ADR-0029). The
  analysis also reads the decision component's rules, which `run` has no port for.
- **Handing accounting each wait on a person with a pseudonym for who answered.** Accounting
  could then sum by pseudonym, which is a sum per person. The rule would hold in policy, not in
  the data model (ADR-0015, protective rule).
- **A model that estimates the marginal value.** ADR-0015 §2 asks for an analysis. The refusals
  are counted exactly.

## Consequences

- `run`: `Admission.short`, `OpenBlock.short`, `Block.short`; the record carries `short`;
  `GroupedWait`, `grouped()`; `BlockedTime.grouped`; port `run/ports/departments.py`.
- `accounting`: `accounting/ports/` with `BlockAccounts`, `MethodCheck`, `RecurringDecisions`;
  `domain/service/bottleneck.py`; `application/service/bottlenecks.py`.
- `composition/bottlenecks.py` answers the three ports; `taktusctl bottlenecks`.
- `tests/components/accounting/test_bottlenecks.py`.

## Where this promise ends

The marginal value covers what admission control refused at a step's boundary. A wait inside a
worker's assignment is not seen (ADR-0043). The raise for an admission refusal is per run's
budget, not per tenant. Where a person raised a run's budget between two refusals, the second
shortfall is measured against the raised line. The run's sum is then less than the raise both
steps needed, by what the person added beyond the first shortfall. Places at capacity are counted per process, not per worker: two processes
waiting on one worker each count their own blocks. A provider's rate limit, a unit's quota or
budget and the tenant's monthly budget carry no shortfall; their blocks count as effect, with no
raise. The cost of a raise is stated in the limit's own units. It is priced in money only where
the limit is money, and then as an estimate. A change of method is checked only by the
maturation candidacy of a step on a language model; another method's fit for a worker step or a
rule is not checked, and the check says so. Batching is an offer: Taktus does not hold back a
request that is not urgent. Which request is urgent is not recorded either. A deadline with a
deputy is offered for a role; whether the process already declares one is not read. Departments
come from the identity directory as it is when the analysis runs, not as it was when the wait
was answered.
