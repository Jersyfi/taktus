# NTC-0099 — A broken interface reaches the owner

**Mode entry:** M2.4
**Kind:** behaviour-change
**Decided:** 2026-10-09
**Raised in:** issue [#100](https://github.com/Jersyfi/taktus/issues/100), in the pull request that closes it

## 1. What was decided

Taktus now notices on its own when an interface it depends on stops behaving as its adapter
expects, and tells the owner (ADR-0047, DEC-0058). What the software does differently:

- The connector contract has a cause `unexpected`: the target answered with a status or a body the
  connector does not foresee. The reference repository connector reports it for every status
  outside its table and for a success it cannot read on a read. A success it cannot read on a
  write is `unknown`. Before, the first was `invalid` and the second `unavailable` or an
  unclassified error.
- The core's connector port tells a connector that answered outside its contract
  (`ContractBroken`) from one that did not answer.
- A connector step whose call fails as unforeseen — `contract`, `unauthenticated`, `unexpected` —
  or transiently — `unavailable`, `unknown`, `unreachable` — writes `interface.failed` to the
  ledger beside its `step.finished`.
- While the scheduler leads, it looks once a minute. A rule makes one broken interface per
  interface and cause. A transient failure counts only when a retry of the same step failed too.
  Each broken interface raises one report of kind `failure` through the owner-facing channel, with
  the first and the last failed call, their runs and steps, and the count.
- `taktusctl interfaces` shows every broken interface and what became of its report — delivered,
  not delivered and why, or closed.

## 2. The evidence

- Issue #100, which states how it is verified, and DEC-0058, the owner's preference it records.
- `tests/adapters/connectors/test_broken_interfaces.py` runs the reference connector in front of
  the fake repository service. An unexpected shape and a status that should not occur make one
  broken interface; an authentication refused makes another. Each reaches the configured channel
  once, with its runs, its step and its first and last call. An outage a resume resolved raises
  nothing; one a resume did not resolve is reported. Without a channel it is recorded and shown as
  not delivered.
- `tests/components/run/test_interface_failures.py` holds the rule over every cause of the
  contract; `tests/components/reporting/test_broken_interfaces.py` holds the rule that groups and
  counts; `tests/integration/test_interfaces_command.py` runs `taktusctl interfaces`.

## 3. What was considered

- **Count the connector's `detail` text.** Rejected: a decision that reads words is not a rule over
  a recorded cause (ADR-0023).
- **Send the report from the run, at the step boundary.** Rejected: a delivery would sit in the
  run's path.
- **Keep a table of broken interfaces.** Rejected: the ledger entries are the record, and the
  report is what was said.

## 4. Which entry permits it

M2.4, *"A change of what the software does, made inside an agreed scope, that breaks no published
contract, moves no limit or autonomy level and says nothing public."* The scope is issue #100. The
connector contract gains a cause; no version of Taktus that uses it is released, so it is not yet
published and `v1` may still move (ADR-0019), and no field an existing message carries changes. No
limit and no level moves. What is said goes to the tenant's own owner, through the channel the
tenant configured, and nothing is said under the project's name.
