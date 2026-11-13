# ADR-0298 — A unit limit admits one step at a time, and may continue on a cheaper model

**Status:** accepted · supersedes two bounds of ADR-0282 (*Concurrent runners*, *The cheaper
model*) · extends ADR-0116 · serves UC-8.5, UC-8.10

## Context

ADR-0282 holds a run to every limit of the units on its path. Before a step is admitted, the
engine reads what the limit's runs of the period cost and checks that the step's reservation
fits what remains. It left two things open, each named where its promise ends.

- **Two runners at once.** Two runners that admit a step against the same limit at the same
  instant both read the same cost. Both steps may fit what each saw, and the limit is crossed
  by one step per runner. UC-8.5 and UC-8.10 allow a crossing only by the one inner step during
  which a running total crossed the line.
- **The cheaper model.** UC-8.5 offers three policies at the line: halt for a person, wait for
  the next period, or continue on a cheaper model the process allows for the same purpose. Only
  the first two were built.

ADR-0116 already gives a step on a model the chain of members that serve its purpose, and the
route that admits a member for a step: its residency, its exactness class, a trial on the
process's cases (ADR-0249), a share (ADR-0246), no cool-down.

## Decision

### 1. A claim per limit serialises the admissions against it

The persistence port gains `Claims`: a named claim of a tenant, held inside the open unit of
work until it ends. Two transactions that claim the same name run one after the other. In
PostgreSQL it is a transaction-level advisory lock in a namespace of its own, keyed by the hash
of the tenant and the name. In memory it is one lock per tenant and name.

The engine checks a step against the unit limits as before. It then commits the admission. In
the transaction that commits it, before anything else is read, it claims `unit_limit:<name>`
for every limit on the run's path, in the order of their names. Under the claims it reads the
tenant's runs again and makes the same check. A runner that admitted against one of the limits
meanwhile has committed, and its reservation is counted. Where the step no longer fits, the
transaction writes nothing. The step is then held as if it had been refused at once:
`unit_limit.held` is recorded, and the run halts or waits as the limit's policy says.

A claim is taken only where a unit limit applies. A run that no unit limit holds takes none and
stays parallel.

### 2. The policy `cheaper`

A limit's policy at the line is `halt`, `wait` or `cheaper`. Where several limits refuse a step,
the strictest wins: `halt`, then `wait`, then `cheaper`.

Under `cheaper`, a step on a language model that the limit refuses is tried on the other
members of its purpose's chain. A member counts only where the route of ADR-0116 admits it for
this step now. Its demand is estimated as the step's own is: the input it counts and the output
limit the step sets, priced at the instance's price table. Its reservation is scaled as
admission scales it. It is taken only where:

- its money is less than the money of the refused reservation;
- it fits the run's own budget (ADR-0005);
- it fits every unit limit on the run's path.

Of the members that qualify, the one with the least money is taken; the first by name where two
cost the same. The step is admitted on it. `unit_limit.cheaper` is recorded before
`step.admitted`. It names the limit, and its digest holds the member refused, the member taken,
the purpose and both amounts. The call then goes to the member admission reserved for, while
that member still fits the route. The provenance record names it as the step's route.

Where no member qualifies, or the step is not on a language model, the run halts for a person,
as `halt` does. The step's reason says that no cheaper model fits. No policy admits a step
beyond the line. This is a rule over the price table and the stored runs, never a model.

## Alternatives

- **Serialise every admission of the tenant on its ledger claim.** The ledger already has a claim
  per tenant (ADR-0164). It would order every admission of every run, also of runs no limit
  holds. A claim per limit orders only those that compete for one line.
- **Lock the limit's row with `SELECT … FOR UPDATE`.** It needs a row per limit in the same
  database transaction, and the memory adapter would need its own form of it. The claims port is
  one small promise both adapters keep, and a test holds them to it.
- **Check again after the admission and withdraw the step.** That is the open-work cap's
  recount (ADR-0132). Here a withdrawn admission would already be in the ledger and on the run.
  A check under the claim, before the commit, writes nothing that has to be taken back.
- **Move the step to the cheapest member at once, before the limit refuses.** It would change
  what every step runs on whenever a limit exists. The policy acts only at the line, as the use
  case asks.
- **A cheaper model chosen by a model.** A choice of method is never made by a probabilistic
  method where a rule over prices answers it (ADR-0023).

## Consequences

- `ports/persistence.py`: `Claims`. `adapters/driven/memory/claims.py`: `MemoryClaims`.
  `adapters/driven/postgres/claims.py`: `PostgresClaims`, in the namespace `CLAIMS` of
  `_locks.py`.
- `run/application/service/execute_run.py`: the recheck under the claims (`_rechecked`,
  `_UnitRace`), the policy `cheaper` (`_cheaper`, `_members`), the route that tries the admitted
  member first, and the ledger kind `unit_limit.cheaper`.
- `governance/domain/model/unit_limits.py` and `run/ports/unit_limits.py`: the policy `cheaper`.
  `taktusctl units limit set --policy cheaper`.
- The composition wires the claims of its persistence into the engine.
- `tests/adapters/persistence/test_claims.py`, `tests/components/run/test_unit_limits.py`,
  `tests/components/run/test_cheaper_model.py`.

## Where this promise ends

- **One instance of the database.** The claim is an advisory lock of the database the runners
  share. Runners on two databases share no claim, and share no runs either.
- **A wait for the claim.** A runner waits while another holds the claim of the same limit. The
  connection's lock timeout bounds the wait; a wait beyond it fails the admission, and the step
  is admitted again at the next boundary.
- **The inner step's overrun stays.** The claim keeps two admissions from both fitting. It does
  not keep a step from using more than it reserved. That overrun stays the one ADR-0005 allows,
  and it is recorded.
- **Only steps on a language model move.** A worker, a connector or a rule step has no chain of
  members. Under `cheaper` it halts, as `halt` does.
- **Cheaper is money.** A member is cheaper only by the money of its reservation at the price
  table. A table without a price for a member leaves that member out. Tokens or compute seconds
  are not weighed against each other.
- **The quality of the cheaper member.** The member is one the route admits for the step, so its
  exactness class, its trial and its residency hold. Whether its answer is as good is what the
  trial measured, not this policy (ADR-0249).
- **The member at the call.** The call goes to the member admitted while it still fits the route.
  A member that began to cool down between admission and call is passed over as ADR-0116 says,
  and the step may then run on another member than the one reserved for.
- **The recorded route of a moved step.** The route of a step moved to a cheaper member is
  recorded as a route that tried that member first. It names the members before it in the chain
  only where they did not fit; the dearer one the limit refused is named by
  `unit_limit.cheaper`, not by the route.
