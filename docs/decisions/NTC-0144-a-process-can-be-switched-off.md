# NTC-0144 — A process can be switched off

**Mode entry:** M2.4
**Kind:** behaviour-change
**Decided:** 2026-10-10
**Raised in:** issue #198

## 1. What was decided

A process can be switched off: `taktusctl deactivate --process <id>`. Before, a registered
process stayed active until another version replaced it, and its triggers kept starting runs.
UC-13.6 §2 asks that switching the guides' process off leaves the repository's documentation
complete, and issue #198 verifies it by switching the process off. What the software does now:

- The process loses its active version. Its schedule triggers no longer fire and its event
  triggers start nothing, because both read the active version.
- Its versions stay. Registering one again switches the process back on.
- The act is the ledger entry `process.deactivated`, with the version that was active and the
  identity that switched it off. Switching off a process that is off already records nothing.
- A run already started is not stopped; it ends as it would have.

## 2. The evidence

- `tests/integration/test_time_triggers.py`: S-05 started once a day by the elected scheduler,
  and not at the next midnight after it was switched off.
- `tests/adapters/connectors/test_guides_process.py`: switching S-05 off leaves every file under
  `docs/` and the repository's head as they were, and records `process.deactivated` once.

## 3. What was considered

- **Delete the process and its versions.** Rejected: nothing is deleted without asking
  (CLAUDE.md §9), and the versions are the process's history.
- **Stop the runs in progress as well.** Rejected: a run stops at a step boundary by a person's
  act on that run. Switching a process off says nothing about one run.

## 4. Which entry permits it

M2.4, *"A change of what the software does, made inside an agreed scope, that breaks no contract,
moves no limit or autonomy level and says nothing public."* The scope is issue #198, whose
verification switches the process off. The ledger kind is new and the entry's shape is the
shared kernel's; no schema changes. No limit or level moves.
