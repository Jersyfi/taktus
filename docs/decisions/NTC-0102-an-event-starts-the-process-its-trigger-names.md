# NTC-0102 — An event starts the process its trigger names

**Mode entry:** M2.4
**Kind:** behaviour-change
**Decided:** 2026-10-10
**Raised in:** issue [#76](https://github.com/Jersyfi/taktus/issues/76), in the pull request that closes it

## 1. What was decided

Taktus now reacts to events as ADR-0048 decides and UC-4.14 requires. What the software does
differently:

- The intake writes the outbox entry `intake.accepted` in the transaction that keeps an intake
  event. Before, nothing wrote the outbox.
- A redelivery — a delivery whose identifier the tenant already holds — changes nothing and
  writes no entry. Before, it replaced the kept event, which reset one already completed to
  *awaiting identity*.
- The `automation` role leads through the leadership port and, while it leads, reacts to the
  entries: it completes the intake into one command, acting for the sender as placed, and starts
  one run of each process whose active version has a matching event trigger. Before, it started
  and waited.
- A process version records when it became active. An event received before that starts nothing.
- Registration checks event triggers against `contracts/events/v1`: a kind outside the
  catalogue, a filter field the kind does not carry, an unknown condition, an input taken from a
  field the kind does not require, or an input left without a value refuses the version. Before,
  an event trigger was carried unchecked, and its `filter` was free text.
- The reference repository connector emits the catalogue's kinds: `issue.opened` instead of
  `issues.opened`, and in addition `issue.labelled` (one per label added) and `branch.pushed`
  (from a push to a branch, with every path its commits changed).

## 2. The evidence

- Issue #76, its sections "How it is verified" and "Where the boundary lies", UC-4.14 §2, and
  ADR-0048.
- `tests/composition/test_reactions.py`: a labelled issue starts its process without a person,
  with the declared inputs, acting for the sender; a redelivery and an entry left unpublished
  start nothing twice and complete the intake once; a filter that does not hold starts nothing
  and leaves the intake to a person; one event starts each process once; a condition makes it
  wait; an event older than the version and an unplaced sender start nothing; a refused run is
  recorded as `trigger.refused`.
- `tests/integration/test_event_reactions.py`: the same against PostgreSQL with two automation
  roles, one of them stopped between two events.
- `tests/components/process/test_event_triggers.py`, `tests/contract/test_events_binding.py`,
  `tests/adapters/persistence/test_outbox.py`, `tests/adapters/connectors/test_repository_intake.py`.

## 3. What was considered

- **Keep `issues.opened` beside `issue.opened`.** Rejected: two names for one kind, and the
  catalogue would no longer say what the connector sends.
- **Coerce every identifier from an event to a number.** Rejected: an identifier is a string in
  the contract; only where the process declares its input an integer is a digit string given as
  one (`contracts/events/v1` §3).
- **Check an event's sender again only when the run starts.** Rejected: the command is completed
  before the runs start, and an unplaced sender gets no command (UC-1.7).

## 4. Which entry permits it

M2.4, *"A change of what the software does, made inside an agreed scope, that breaks no published
contract, moves no limit or autonomy level and says nothing public."* The scope is issue #76. The
events contract and the connector contract are `v1` and not yet published by a release
(ADR-0019); the connector's kind name changes, no field of a message does. No limit and no level
moves, and nothing is said under the project's name.
