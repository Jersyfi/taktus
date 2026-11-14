# ADR-0333 — A count of corrections lowers a level beside the rate

**Status:** accepted · extends ADR-0110, ADR-0215 §4 · UC-7.5 · DEC-0239

## Context

UC-7.5 lowers a process or an action of it one level when its correction rate over the tenant's
window rises above the tenant's limit (ADR-0110). A *correction* is a proposal a person changed
or rejected. The rate is the share of a unit's decisions that were corrections. A rate needs a
minimum of decisions before it lowers anything, four by default.

A process that is decided rarely never reaches that minimum. Two corrections in a week then
lower nothing, however telling they are. A business can state its rule for falling back as a
count: "two corrections in a week". ADR-0215 §4 already lowers a *class of request* by such a
count, from the numbers its process states. A tenant could not set a count for a process or
for itself.

## Decision

### 1. A count beside the rate

A tenant's correction limits may name a **count rule**: a number of corrections and a span of
days, 7 by default and 28 at most. When a unit's corrections since its last change of level,
within the span, reach the number, the unit falls one level. The rate's own rule still applies.
Whichever is met first lowers the unit.

The fall is the one of ADR-0110: at the decision that met the count, before the run's next step;
an incident of kind `corrections.rate` naming the count, the span, the decisions and the
corrections; `autonomy.lowered` with the new level. Its facts name `corrections_limit` and
`window_days` in place of `rate` and `limit`.

### 2. Per tenant and per process

The tenant's count applies to every process and every action of it. A process may have a count
of its own, which takes the tenant's place for that process. Both are set with
`taktusctl corrections configure --lower-count N [--lower-count-days D] [--process P]`. A count
of 0 removes the rule. A class of request keeps the count its process states (ADR-0215 §4).

### 3. The count is shown

`taktusctl corrections list` shows, beside each window's rate, its count of corrections. The
limits printed by `configure` name the tenant's count and every process's.

### 4. Never per person

A count rule counts the decisions of a process or an action, never who decided them. No field
of it names a person (principle 14, ADR-0015).

## Alternatives

- **Lower the rate's minimum of decisions.** Rejected. A minimum of two with a rate of 25 % lowers
  a process after one correction in two decisions; the count asks for a number of corrections,
  however many decisions there were.
- **A count in place of the rate for the tenant.** Rejected. A tenant that sets a count would lose
  the rate for every busy process. Beside the rate, both protect.
- **The count in the process version's statement.** Rejected for this step. A version's numbers
  are the blueprint's proposal; the tenant's own rule for falling back is configuration and
  changes without a new version.

## Consequences

- `CorrectionLimits` gains `lower_count` and `processes`. Limits without a count are written as
  before, so the release before reads them (ADR-0093). No migration: the limits are a document.
- `components/governance/application/service/corrections.py`: the count after the rate.
- Tests: `tests/governance/test_corrections.py`.

## Where this promise ends

- **One level per decision.** A count met again after a fall lowers again only by a new count
  since the fall, because counting starts from the unit's last change of level.
- **A breach of an anchor** lowers at once by ADR-0110 §3; the count does not change that.
- **A level lowered rises again only through UC-7.1.** The count proposes no raise.
- **The span is at most 28 days**, the longest window the projection keeps.
