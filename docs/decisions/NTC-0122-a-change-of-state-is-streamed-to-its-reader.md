# NTC-0122 — A change of state is streamed to its reader

**Mode entry:** M2.4
**Kind:** behaviour-change
**Decided:** 2026-10-10
**Raised in:** issue [#183](https://github.com/Jersyfi/taktus/issues/183), in the pull request that closes it

## 1. What was decided

The control plane now sends a change of state to its reader as it happens, as ADR-0055 decides
and UC-6.10 §2 *Live* requires. Before, the HTTP surface answered only when asked. What the
software does differently:

- The `api` role serves `GET /changes`, a long-lived response in the Server-Sent Events format.
  Its scope is the tenant of the reader's identity, one process (`?process=`) or one run
  (`?run=`). It sends a `snapshot` first, then a `change` for every ledger entry of a run's, a
  step's or a decision request's state, each with the entry's hash as its position, and a
  heartbeat comment every 15 seconds. The shapes are the new contract `contracts/changes/v1`.
- Every insert into `ledger_entry` notifies the tenant it wrote, from a trigger added by
  migration 0027, when its transaction commits. Each `api` process listens on one connection,
  reads a woken tenant's new entries once after a batch window of 250 milliseconds, and reads a
  tenant with open streams every 2 seconds without a signal.
- A reader that reconnects with `Last-Event-ID`, to any process, receives every change after it;
  with an unknown position or more than 1,000 entries behind, a fresh snapshot.
- Which state an entry's kind and outcome lead to is published beside each state machine: the
  run's and the step's in `components/run/domain/model/recorded.py`, a decision request's in
  `components/decision/domain/model/recorded.py`. A test holds the run's table against every
  kind the engine records.
- Whether a reader may see a run is one predicate of `reporting`, asked for each change when it
  is sent with the roles the key proves then. Until UC-6.4 it is the tenant boundary. A key that
  no longer proves an identity ends the stream.
- One process holds at most `TAKTUS_LIVE_STREAMS` streams, 500 by default; one more is answered
  `503` with `Retry-After: 1`.
- The ledger store answers three new reads — `head`, `after`, `position` — without claiming the
  chain, and a unit of work may be opened `consistent`: every read in it sees one state. The
  snapshot and its position are read that way.

Three choices the ADR left open were made here. A change carries `state`, the state the entry
led to, so that a representation reads it from the change and never derives it a second time;
the ADR requires the state to be read from one place, and the change is how it reaches the
reader. A snapshot's step carries its method kind beside its state, because a change does and a
representation draws both from the first event on. The decision request's statuses are
published by the decision component, which owns that state machine, beside the run's table.

## 2. The evidence

- Issue #183, its sections "How it is verified" and "Where the boundary lies"; ADR-0055;
  UC-6.10 §2 *Live*; DEC-0055.
- `tests/integration/test_live_changes.py`: two `api` processes on one database; a stream opened
  on the first receives a step started, completed and failed, a run halted and a decision
  awaited, recorded through the second, each within 5 seconds of its record; the same with the
  notification's trigger disabled; a reader that reconnects to the other process receives every
  change after its position, once.
- `tests/composition/test_live.py`: the snapshot first; every kind UC-6.10 names; an entry that
  changes no state is not sent; no actor, consumption, model, adapter or digest in a change; the
  interval read without any signal; a resume, an unknown position and one more than 1,000
  behind; another tenant's runs send nothing and the heartbeat keeps its interval; the scope; a
  revoked key ends the stream; the maximum; the histogram; a stopping process ends its streams.
- `tests/adapters/persistence/test_ledger_signal.py`: a commit notifies its tenant once, a
  rollback nothing; a lost listening connection is opened again; a consistent read sees one
  state. `tests/adapters/persistence/test_ledger_store.py`: the three reads, in both stores.
- `tests/adapters/rest/test_changes.py`: the key only in the header, `503` with `Retry-After`,
  the event format, the stream ending with its key.
- `tests/contract/test_changes_binding.py`, `tests/components/run/test_recorded_states.py`,
  `tests/components/reporting/test_live.py`.

## 3. What was considered

- **Leave the state out of the change, as the ADR's list of fields reads.** Rejected: every
  representation would then hold a copy of the table, which ADR-0055 §4 rules out.
- **Keep the stream's machinery in the reporting component.** Rejected: it holds tasks, timers
  and the signal, which belong to the composition root as the roles do (`composition/roles.py`);
  the rules — projection, scope, predicate, when to snapshot — stay in `reporting`, without time.
- **Read the snapshot in two ordinary transactions.** Rejected: an entry committed between the
  runs and the position would appear in the snapshot and again as a change.
- **Add a setting for the 2-second interval and the 15-second heartbeat.** Rejected: ADR-0055
  fixes both, and a setting would let an operator move the 5-second bound unknowingly.

## 4. Which entry permits it

M2.4, *"A change of what the software does, made inside an agreed scope, that breaks no
contract, moves no limit or autonomy level and says nothing public."* The scope is issue #183
under ADR-0055. The changes contract is new and not published by a release (ADR-0019); no other
contract changes. No limit or level moves; `TAKTUS_LIVE_STREAMS` is the bound ADR-0055 §7 asks
for. Nothing is said under the project's name.
