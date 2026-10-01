# NTC-0009 — The removal test rehearses, and says untested

**Mode entry:** M2.4
**Kind:** behaviour-change
**Decided:** 2026-09-30
**Raised in:** PR_LINK

## 1. What was decided

- **Old:** the removal test resolved every process that writes outward statically and ran none.
  **New:** it runs them in rehearsal: an outward connector operation answers with the recorded
  response of its most recent real call and acts on nothing; every ledger entry of a rehearsal
  carries `rehearsal: true`; no egress entry is written (ADR-0030). A process is rehearsed once
  every outward operation it calls has a recording on that instance.
- **Old:** an integration no process uses got the verdict `changed`, which counted towards
  maturity. **New:** `untested`, which does not.
- **New:** every verdict carries the configuration it was taken under — the adapter, what it
  serves, its version.

## 2. The evidence

`docs/runs/first-run.md` §6: no real process was rehearsed, and the `worker.endpoint` row read
"changed — no registered process uses this integration", repeated by every weekly run (issue
#36). The tests: `tests/components/run/test_rehearsal.py`, `tests/components/catalog/
test_removal.py`, `tests/integration/test_removal_test.py`.

## 3. What was considered

- Rehearsing by asking connectors not to act: rejected, the removal test exists to doubt an
  adapter, so the core withholds the call itself.
- Recordings shipped in the repository: rejected, they would carry one deployment's records into
  a public repository; a recording is the instance's own.

## 4. Which entry permits it

M2.4: inside the agreed scope of the removal test (CLAUDE.md §6), breaking no contract — the
ledger field is optional — moving no limit or level, saying nothing public.
