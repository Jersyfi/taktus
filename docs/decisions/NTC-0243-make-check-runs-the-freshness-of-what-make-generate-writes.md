# NTC-0243 — `make check` runs the freshness of what `make generate` writes

**Mode entry:** M2.2
**Kind:** test-strategy
**Decided:** 2026-10-29
**Raised in:** the session that installed rc.33, for the run of P-03 on issue #335

## 1. What was decided

`make check` always runs the three tests that hold a file `make generate` writes to the one
committed: `api/openapi.yaml`, `src/taktus/composition/shipped.json` and
`web/src/lib/generated/fixtures.json`. They take under a second. Before, `make check` ran only
the unit tests that `tools/lanes.py` selected under `tests/components`, `tests/tools` and
`tests/contract`.

## 2. The evidence

- Run `run_db8790e57656249548c6` of `p03-implementation@22` added the route
  `GET /levels/runs/{run_id}/stages` for #335 and passed `make check` in its workspace.
- Its branch failed CI twice on
  `tests/adapters/rest/test_openapi.py::test_the_committed_document_is_what_make_generate_writes`:
  the committed document lacked the route. The run gave the issue back at `read-pipeline`.
- P-03 asks its worker to run `make check` before it ends (P-03 v23, step `implement`). The test
  sits under `tests/adapters/rest`, which `make check` never selects, so the worker could not
  have seen the failure.
- The repeat of the same CI run also met a port already in use for a test container; that is
  recorded on the flake register #520 and is not what this notice mends.

## 3. What was considered

- **Select `tests/adapters/rest` in `make check`.** Rejected: it adds several hundred tests to
  a check meant to stay under a minute, and still misses `shipped.json`.
- **Have P-03 run `make generate` before its check.** Not instead: a person forgets it as
  easily, and the check is the place both meet.

## 4. Which entry permits it

M2.2: how a check is tested is the session's, and this one is made stricter, not weaker.
