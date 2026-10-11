# NTC-0164 — An instance runs several workers, and the removal test tests each

**Mode entry:** M2.4
**Kind:** behaviour-change
**Decided:** 2026-10-11
**Raised in:** issue #209

## 1. What was decided

Until now an instance read one worker, configured by `TAKTUS_EXECUTION` and `TAKTUS_WORKER`, under
the identifier `worker.<kind>`. Now `TAKTUS_WORKERS` names several workers, in the order a step is
resolved in, each under the identifier `worker.<name>` (ADR-0078). Three things about how they
are read were not fixed by any document, and were decided here:

1. **A named worker reads its own settings first, and the instance's where it sets none.** The
   namespace, the egress image and the default limits are set once. Its endpoint is its own
   alone: a named worker reached by endpoint without one is refused at startup.
2. **A named worker receives only its own credentials.** It reads
   `TAKTUS_WORKER_<NAME>_CREDENTIAL_<CREDENTIAL>_FILE` and never the instance's
   `TAKTUS_CREDENTIAL_<CREDENTIAL>_FILE`. Two workers that need the same value have two variables
   pointing at one file.
3. **The removal test puts the withheld integration first in its baseline.** Before, it
   exercised an integration only on the steps that integration served first, so a worker
   configured behind another read *untested*. Now the baseline runs with the integration first,
   and the withheld run without it, as before. An integration that served first is tested
   exactly as before.

An instance that names no workers behaves as before, under the same identifier.

## 2. The evidence

- Issue #209, "How it is verified": several workers, each with its identifier, its kind and what
  it needs to start; one worker configured as today keeps working; each launched worker receives
  only its own credentials; S-01 says *changed* for each coding worker with the other as its
  alternative; the conformance half is recorded per worker.
- `tests/integration/test_two_coding_workers.py`: an instance configured with both coding workers
  in one order; S-01 for each gives *changed* with the other named, and the removal half of each
  passes. Without point 3, the worker configured second reads *untested*: this test was run
  without it and failed on that.
- `tests/integration/test_launched_process.py`: two launched workers that reference
  `AGENT_KEY` each receive their own value; neither receives the instance's.
- `tests/conformance/test_taktusctl.py`: `taktusctl conformance record` passes for each of two
  configured workers and records each under its own identifier.
- `tests/composition/test_settings.py` and `tests/governance/test_chart.py`: the settings and the
  chart read, render and refuse the same things.

## 3. What was considered

- **A named worker falls back to the instance's credentials.** Rejected: a worker would receive a
  value meant for another whenever a worker-specific one was forgotten, which is what the issue
  forbids. Where two options are both consistent with the sources, the stricter in substance
  (DEC-0040).
- **The operator reorders the workers to test the second.** Rejected: the weekly removal test
  runs on the configuration as it is, and must be automatic (CLAUDE.md §6).
- **Count the second worker as tested when the first is withheld.** Rejected: the verdict for
  the first is about the first. The second's removal half would be asserted, not measured.

## 4. Which entry permits it

M2.4 of `docs/decisions/anchors.taktus.md`: "A change of what the software does, made inside an
agreed scope, that breaks no contract, moves no limit or autonomy level and says nothing public."
The scope is issue #209, roadmap `0.4.0`. No contract under `contracts/` changes: the worker
contract and the removal result's shape stay as they are. No limit moves: admission reserves the
largest memory among the launched units, which is what one unit reserved before when there was
one. No autonomy level moves, and nothing is said publicly.
