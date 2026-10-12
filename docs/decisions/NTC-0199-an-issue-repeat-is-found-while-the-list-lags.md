# NTC-0199 — An issue repeat is found while the list lags

**Mode entry:** M2.4
**Kind:** behaviour-change
**Decided:** 2026-10-12
**Raised in:** the pull request for issue #300

## 1. What was decided

The repository connector is the reference connector for a repository hosting service. The
conformance suite is the program that checks a connector against its contract. Both now pass
against the real service. ADR-0024, amended on 2026-10-12, is the decision; this notice records
the change of behaviour.

1. **An issue's repeat is found at once.** `repository.issues.create` looks for its key in the
   100 most recently created issues, as before. It then reads every issue above the newest
   number that list shows, one by one, until a number does not exist, at most twenty. A
   number the service answers as deleted or moved is passed over. A pull request is never the
   issue sought. A create costs one request more than before: the number that does not exist.
2. **A scenario can name what an earlier write created.** `{{shared}}` in a write's input is
   one token in every call made with a first key and another in every call made with a new
   key, the same across the writes of a run. `{{unique}}` is unchanged.
3. **A scenario may name further credentials.** `credentials` accepts names beside `actions`
   and `intake`. The suite only searches for their values (C-04); it never sends them.
4. **The connector's scenario runs against the real service.** Its branch write comes before
   its pull request, and both name the branch through `{{shared}}`. It names the app's key as
   `credentials.app`.
5. **The fake service behaves as the real one did.** It refuses a pull request whose head
   branch does not exist. Started with `--issue-list-lag`, its issue list leaves out what was
   created in that many seconds; the conformance gate starts it so.

## 2. The evidence

- 2026-10-12, the installed instance: the suite against the sandbox repository failed C-05
  (sandbox issues #9/#10 and #11/#12, two seconds apart) and C-02 (`Validation Failed` on the
  pull request). Issue #300 states it.
- 2026-10-12, from a workstation, four issues created in the sandbox and read back at once:
  none was in the issue list (newest listed number below the new one each time); each was
  answered by its number with 200, and the number above it with 404.
- `tests/adapters/connectors/test_repository_actions.py`
  `test_an_issue_repeated_at_once_is_found_while_the_list_lags` passes, and fails with the
  numbers above the list not read.
- `tests/adapters/connectors/test_repository_live.py`, against the sandbox: three tests pass,
  the new one repeating an issue create at once on a second connector.
- The suite against the sandbox with the connector acting as the app and the shipped scenario:
  C-01 to C-09 passed, C-10 pending, exit code 0.

## 3. What was considered

- **Remembering in the connector process the keys it acted on.** Covers a repeat within one
  process and nothing after a restart, which is the case ADR-0005 is about. Not taken.
- **The service's search, by the mark.** It lags by minutes, longer than the list. Not taken.
- **Waiting before the lookup.** A guess at the service's lag, and every create pays it. Not
  taken.
- **A second scenario only for the real service.** Two scenarios that must agree on every
  other part. One scenario that runs against both is the smaller thing to keep. Not taken.
- **Setup writes in the scenario**, made once before the writes. A new part of the format with
  its own rules for failure and output. One placeholder does what was needed. Not taken.

## 4. Which entry permits it

M2.4 of `docs/decisions/anchors.taktus.md`: "A change of what the software does, made inside an
agreed scope, that breaks no contract, moves no limit or autonomy level and says nothing
public." The scope is issue #300. The contract change is additive: a scenario valid before is
valid now and runs as before, and `v1` is not yet released (ADR-0019), so M3.5 is not touched.
No limit or level moves, and nothing public is said. The amendment of ADR-0024 is M1.9.
