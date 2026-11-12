# ADR-0270 — Taktus proposes processes from recurring work, ordered by how often it recurs

**Status:** accepted · extends ADR-0251, ADR-0254 · UC-4.4, UC-4.6 · DEC-0228

## Context

UC-4.4 requires that Taktus notices, unasked, where work could be automated and says so. A
proposal states the work it would take over, what it would cost to run, and why it is proposed
now, and nothing else. Proposals come as a list ordered by priority, with the reason for the
order shown. Each is accepted or declined on its own; accepting one starts building a process
from it (UC-4.1), and nothing runs for real before a person commissions it. A proposal drawn
from a person's own work is shown to that person only (principle 14).

UC-4.6 requires that the same failure healed three times raises an improvement proposal. Since
ADR-0254 it is recorded as `heal.recurred` and said to the owner as a report; no list of
proposals existed.

## Decision

### 1. Two kinds of recurring work, found by rule

The process component's rule (`domain/service/proposing.py`) reads two kinds of fact from the
ledger. Both are rules over records; no model guesses what recurs (ADR-0004).

- **Started by hand.** A run created without a trigger (`run.created` without `run.triggered`,
  no rehearsal) was started by the identity that `run.created` names. The same identity starting
  the same process at least three times in the last 90 days, at a regular cadence — every gap
  between two starts within half of the median gap from it — is work that person does by hand.
  The proposal takes over the starting, on a schedule of that cadence.
- **Healed again and again.** Each `heal.recurred` is a process that fails the same way. The
  proposal takes over the fault's removal: a change of the process that removes the failure.

### 2. What a proposal says

A proposal has an identifier derived from what it is about, the work it would take over, its
cost, why now, and the words a person's acceptance hands on. The **cost** is what the runs it
draws on consumed, as the run component recorded it (ADR-0029): the mean per run of each
quantity, and that times how often it recurs in 30 days. **Why now** names the evidence: how
many times, at which cadence, the newest at which date. Nothing else is in it.

### 3. The order and its reason

The list is ordered by how often the work recurs per 30 days, most often first; ties by
identifier. Each proposal carries the order's reason in words: `recurs 4.3 times per 30 days`.
It is the one measure both kinds have in common and a person can check from the ledger.

### 4. Who sees it

A proposal drawn from runs a person started is that person's: the list shows it to the identity
the runs name, and to nobody else — not the owner, not an operator. A proposal drawn from a
process's heals concerns no person and is shown to every identity of the tenant. Nothing about a
person is stored to make the list: it is computed from the ledger when it is asked for.

### 5. Accepted or declined, one by one

Accepting a proposal records `proposal.accepted`, declining it `proposal.declined`, each with
the person as actor and the proposal's identifier by digest. A decided proposal is not listed
again. Accepting hands the proposal's words to the request path of ADR-0251 §1, acting for the
person: a run of the process the operator names builds a proposal of a version, which is
rehearsed and which only a person commissions (UC-4.1, UC-4.15). Declining costs nothing and
changes nothing. Only the person a proposal is shown to may decide it.

## Alternatives

- **Proposals as records of their own, in a table.** They would store, for every person, what
  that person does by hand. Computing them from the ledger keeps the person's work where it
  already is, under the ledger's rules.
- **Order by money saved.** A run that consumed nothing measurable would never rise, and a
  person's time is not measured (principle 14).
- **A model that reads the ledger and suggests.** It would guess; recurrence is a rule.

## Consequences

- `proposal.accepted` and `proposal.declined` are new ledger kinds.
- `heal.recurred` now also appears as an improvement proposal in the list.

## Where this promise ends

- **Two kinds only.** Work Taktus has no record of — done in a system it does not read — is not
  found; that is process discovery (UC-9.4).
- **The cadence is a rule.** Starts at an irregular rhythm are not proposed, however often.
- **Accepting does not build by itself.** Without the operator's describe and change processes
  (ADR-0251), accepting is refused and says so; the decision is not recorded.
- **Not a surface of its own.** The list and its acts are the composition's service; the web app
  page and the channel's command for it are not built here.
