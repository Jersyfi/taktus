# NTC-0140 — The `api` role serves the overview

**Mode entry:** M2.4
**Kind:** behaviour-change
**Decided:** 2026-10-10
**Raised in:** issue [#191](https://github.com/Jersyfi/taktus/issues/191), in the pull request that closes it

## 1. What was decided

The overview of UC-6.10 is built as ADR-0067 decides. What the software does differently:

- The `api` role serves `GET /levels/overview`, with an account key. It holds the areas the reader
  may look into — today the reader's tenant, the one area — and every process in each the reader
  may see. For each process it gives its name, active version and autonomy level, how many of its
  runs work and how many wait right now, and the steps running right now. Each running step
  carries its glyph with motion and without. Every element has a text with the same figures.
- The run component defines `WORKING` (`planned`, `admitted`, `running`) and `WAITING`
  (`waiting_human`, `halted`, `escalated`). They are the one definition of how busy a process is.
- A run of a process that is not registered is shown under its process's identifier.
- The web app starts at the overview, live from the tenant's stream. Each process leads down to
  its process level, each running step to its run. The list of runs it showed before, kept in the
  browser from the stream, is gone.

## 2. The evidence

- Issue #191, its sections "How it is verified" and "Where the boundary lies"; UC-6.10 §1 and §2;
  ADR-0029; ADR-0067; DEC-0055.
- `tests/integration/test_overview.py`: a process registered and a run of it started on a daemon.
  The overview counts the run as working while it runs. Its end reaches a reader of the tenant's
  stream within 5 seconds. The overview read after it shows the process idle, equal to what the
  read API's runs give by the same definition.
- `tests/adapters/rest/test_overview.py`, `tests/components/reporting/test_overview.py`,
  `web/src/lib/overview.test.ts`.

## 3. What was considered

- **The activator's organisational path as an area.** Rejected: it would place a process by a
  person (ADR-0067).
- **One figure of open runs.** Rejected: it hides whether the work moves or waits.
- **The sets in `reporting`.** Rejected: `reporting` owns no figure (ADR-0029).

## 4. Which entry permits it

M2.4, *"A change of what the software does, made inside an agreed scope, that breaks no
contract, moves no limit or autonomy level and says nothing public."* The scope is issue #191
under UC-6.10, accepted in DEC-0055, and ADR-0067. No contract under `contracts/` changes;
`api/openapi.yaml` is regenerated. No limit or level moves.
